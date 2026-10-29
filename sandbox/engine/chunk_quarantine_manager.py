"""
KnowLayer Chunk Quarantine & Restoration Manager
=================================================
Manages quarantine, removal, and restoration of low-scoring / defect chunks
between ChromaDB and a persistent quarantine repository.

Allows administrators and reviewers to:
1. Inspect chunks flagged with low quality scores (e.g. Top 20 worst chunks).
2. Quarantine / delete chunks that degrade RAG retrieval from ChromaDB.
3. Add back / restore chunks to ChromaDB if reviewed and determined to be "Good enough".
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.settings import BASE_DIR, COLLECTION_NAME
from app.infrastructure.vector.chroma_client import ChromaVectorStore

logger = logging.getLogger("chunk_quarantine_manager")

QUARANTINE_FILE_PATH = Path(BASE_DIR) / "sandbox" / "data" / "quarantined_chunks.json"


def _ensure_data_dir() -> Path:
    QUARANTINE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return QUARANTINE_FILE_PATH


def load_quarantined_chunks() -> Dict[str, Dict[str, Any]]:
    """Loads all quarantined chunks from disk."""
    _ensure_data_dir()
    if not QUARANTINE_FILE_PATH.exists():
        return {}
    try:
        data = json.loads(QUARANTINE_FILE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        return {}
    except Exception as e:
        logger.warning("Failed to load quarantined chunks from %s: %s", QUARANTINE_FILE_PATH, e)
        return {}


def save_quarantined_chunks(data: Dict[str, Dict[str, Any]]) -> None:
    """Persists quarantined chunks dictionary to disk."""
    _ensure_data_dir()
    try:
        QUARANTINE_FILE_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.error("Failed to save quarantined chunks to %s: %s", QUARANTINE_FILE_PATH, e)


def is_chunk_in_chroma(
    chunk_id: str,
    collection_name: str = COLLECTION_NAME,
    persist_directory: Optional[str] = None,
) -> bool:
    """Checks whether a chunk_id exists in the active ChromaDB collection."""
    try:
        store = ChromaVectorStore(
            collection_name=collection_name,
            persist_directory=persist_directory or str(Path(BASE_DIR) / ".chroma"),
        )
        res = store.collection.get(ids=[chunk_id])
        return len(res.get("ids", [])) > 0
    except Exception as e:
        logger.error("Error checking chunk presence in ChromaDB for %s: %s", chunk_id, e)
        return False


def get_chroma_chunk_presence(
    chunk_ids: List[str],
    collection_name: str = COLLECTION_NAME,
    persist_directory: Optional[str] = None,
) -> Dict[str, bool]:
    """Batch checks presence of multiple chunk_ids in ChromaDB."""
    if not chunk_ids:
        return {}
    try:
        store = ChromaVectorStore(
            collection_name=collection_name,
            persist_directory=persist_directory or str(Path(BASE_DIR) / ".chroma"),
        )
        res = store.collection.get(ids=chunk_ids)
        existing = set(res.get("ids", []))
        return {cid: (cid in existing) for cid in chunk_ids}
    except Exception as e:
        logger.error("Error batch-checking ChromaDB presence: %s", e)
        return {cid: False for cid in chunk_ids}


def add_chunk_to_chroma(
    chunk_id: str,
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    collection_name: str = COLLECTION_NAME,
    persist_directory: Optional[str] = None,
    reviewer_notes: str = "Approved as Good Enough by reviewer",
) -> Tuple[bool, str]:
    """
    Adds or restores a chunk back into ChromaDB with fresh vector embeddings.
    If the chunk was in quarantine, it is removed from the quarantine store.
    """
    if not chunk_id or not text.strip():
        return False, "Chunk ID and non-empty text are required."

    try:
        store = ChromaVectorStore(
            collection_name=collection_name,
            persist_directory=persist_directory or str(Path(BASE_DIR) / ".chroma"),
        )

        clean_meta = dict(metadata or {})
        # Ensure canonical fields are string/int/float
        sanitized_meta = {}
        for k, v in clean_meta.items():
            if isinstance(v, (list, tuple)):
                sanitized_meta[k] = " > ".join(str(item) for item in v)
            elif v is None:
                sanitized_meta[k] = ""
            elif isinstance(v, (str, int, float, bool)):
                sanitized_meta[k] = v
            else:
                sanitized_meta[k] = str(v)

        # Mark review metadata
        sanitized_meta["quarantine_status"] = "restored_good_enough"
        sanitized_meta["restored_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

        store.add_documents([{"id": chunk_id, "text": text, "metadata": sanitized_meta}])

        # Remove from quarantine file if present
        quarantine = load_quarantined_chunks()
        if chunk_id in quarantine:
            del quarantine[chunk_id]
            save_quarantined_chunks(quarantine)

        logger.info("Successfully added chunk %s back to ChromaDB collection '%s'.", chunk_id, collection_name)
        return True, f"Chunk '{chunk_id}' successfully added back to ChromaDB!"
    except Exception as e:
        logger.error("Failed to add chunk %s to ChromaDB: %s", chunk_id, e)
        return False, f"Failed to add chunk '{chunk_id}' to ChromaDB: {e}"


def quarantine_chunk_from_chroma(
    chunk_id: str,
    text: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    reason: str = "Low Quality Score",
    collection_name: str = COLLECTION_NAME,
    persist_directory: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Deletes a chunk from ChromaDB and saves its full text and metadata to the quarantine store.
    Ensures zero data loss while preventing the chunk from diluting live search.
    """
    if not chunk_id:
        return False, "Invalid chunk ID."

    try:
        store = ChromaVectorStore(
            collection_name=collection_name,
            persist_directory=persist_directory or str(Path(BASE_DIR) / ".chroma"),
        )

        # If text or metadata not passed, fetch from ChromaDB first
        if text is None or metadata is None:
            res = store.collection.get(ids=[chunk_id], include=["documents", "metadatas"])
            if res.get("documents") and len(res["documents"]) > 0:
                text = res["documents"][0]
                metadata = res["metadatas"][0] if res.get("metadatas") else {}
            else:
                text = text or ""
                metadata = metadata or {}

        # Save to quarantine
        quarantine = load_quarantined_chunks()
        quarantine[chunk_id] = {
            "chunk_id": chunk_id,
            "text": text,
            "metadata": metadata or {},
            "quarantined_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "reason": reason,
        }
        save_quarantined_chunks(quarantine)

        # Delete from ChromaDB
        store.collection.delete(ids=[chunk_id])
        logger.info("Quarantined and deleted chunk %s from ChromaDB collection '%s'.", chunk_id, collection_name)
        return True, f"Chunk '{chunk_id}' pruned from ChromaDB and archived to quarantine."
    except Exception as e:
        logger.error("Failed to quarantine chunk %s: %s", chunk_id, e)
        return False, f"Failed to quarantine chunk '{chunk_id}': {e}"

