"""
KnowLayer Chunk Editor & Pre-Ingestion Remediation Engine
=========================================================
Provides tools to inspect, validate, edit, and re-score document chunks
BEFORE they are ingested into ChromaDB (or to repair low-quality / quarantined chunks).

Key Capabilities:
1. Live Token & Boundary Validation: Checks token ceiling (200-245 max), micro-fragments (<55), and punctuation.
2. Auto-Normalization: Applies the 5-Pass Chunk Normalizer to repair formatting, tables, and breadcrumbs.
3. Pre-Ingestion Staging Queue: Diverts low-quality chunks to a staging review store rather than polluting ChromaDB.
4. Clean Ingestion: Computes vector embeddings and atomically commits the curated chunk into ChromaDB.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.settings import BASE_DIR, COLLECTION_NAME
from app.infrastructure.document.chunk_normalizer import (
    ChunkNormalizer,
    NormalizedChunk,
    LONE_HEADING_REGEX,
    TRAILING_HEADING_REGEX,
    EXISTING_PREFIX_REGEX,
)
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from sandbox.engine.chunk_quarantine_manager import (
    load_quarantined_chunks,
    save_quarantined_chunks,
)

logger = logging.getLogger("chunk_editor")

STAGED_REVIEW_FILE_PATH = Path(BASE_DIR) / "sandbox" / "data" / "staged_chunks_for_review.json"


def _ensure_staged_file() -> Path:
    STAGED_REVIEW_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return STAGED_REVIEW_FILE_PATH


def load_staged_chunks_for_review() -> Dict[str, Dict[str, Any]]:
    """Loads all chunks staged for pre-ingestion human review."""
    _ensure_staged_file()
    if not STAGED_REVIEW_FILE_PATH.exists():
        return {}
    try:
        data = json.loads(STAGED_REVIEW_FILE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Failed to load staged chunks from %s: %s", STAGED_REVIEW_FILE_PATH, exc)
        return {}


def save_staged_chunks_for_review(data: Dict[str, Dict[str, Any]]) -> None:
    """Persists staged chunks awaiting review to disk."""
    _ensure_staged_file()
    try:
        STAGED_REVIEW_FILE_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to save staged chunks to %s: %s", STAGED_REVIEW_FILE_PATH, exc)


def stage_chunk_for_review(
    chunk_id: str,
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    quality_issues: Optional[List[str]] = None,
    document_id: Optional[str] = None,
) -> None:
    """Stages a questionable chunk into the review queue before ChromaDB ingestion."""
    staged = load_staged_chunks_for_review()
    meta = dict(metadata or {})
    if document_id:
        meta["document_id"] = document_id
    staged[chunk_id] = {
        "chunk_id": chunk_id,
        "text": text,
        "metadata": meta,
        "quality_issues": quality_issues or [],
        "staged_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "pending_review",
    }
    save_staged_chunks_for_review(staged)
    logger.info("Chunk %s staged for pre-ingestion review (Issues: %s)", chunk_id, quality_issues)


def remove_from_staged_review(chunk_id: str) -> bool:
    """Removes a chunk from the pre-ingestion staging store once approved or discarded."""
    staged = load_staged_chunks_for_review()
    if chunk_id in staged:
        del staged[chunk_id]
        save_staged_chunks_for_review(staged)
        return True
    return False


def validate_chunk_content(text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Live validates chunk content and metadata:
    - Counts tokens with WordPiece guard
    - Flags truncation (>245), warnings (201-245), micro-fragments (<55)
    - Checks sentence boundaries and Markdown table syntax
    - Returns diagnostic metrics and suggested fixes
    """
    normalizer = ChunkNormalizer()
    token_count = normalizer.count_tokens(text)
    clean_text = text.strip()

    issues: List[str] = []
    suggestions: List[str] = []

    # 1. Token Budget Utilization
    # If the text has no context prefix yet (raw body fragment), allow >= 55 tokens
    # so that after Pass 5 injects the ~20-25 token [Policy: ...] prefix, total tokens land in [80, 200].
    has_prefix = bool(EXISTING_PREFIX_REGEX.match(clean_text) or clean_text.startswith("[Policy:"))
    min_tokens = 80 if has_prefix else 55

    if token_count > 200:
        issues.append("CRITICAL_TRUNCATION")
        suggestions.append(f"Exceeds 200 tokens ({token_count} tok). Strict maximum is 200 tokens.")
    elif token_count < min_tokens:
        issues.append("MICRO_FRAGMENT")
        suggestions.append(f"Fragment under {min_tokens} tokens ({token_count} tok). Strict optimal minimum is {min_tokens} tokens.")

    # 2. Boundary Integrity
    if clean_text:
        last_char = clean_text[-1]
        if last_char not in {".", "!", "?", ":", "|", "`", '"', "'", "]"}:
            issues.append("UNTERMINATED_BOUNDARY")
            suggestions.append("Chunk does not end with terminal punctuation; sentences may be sliced mid-clause.")
        if clean_text[0].islower():
            issues.append("MID_SENTENCE_START")
            suggestions.append("Chunk starts with a lowercase letter, indicating an abrupt cut from previous section.")

    # 3. Orphan Headings
    if LONE_HEADING_REGEX.match(clean_text):
        issues.append("LONE_HEADING")
        suggestions.append("Chunk consists solely of a lone Markdown heading. Merge with the following body text.")
    m_trail = TRAILING_HEADING_REGEX.search(clean_text)
    if m_trail and m_trail.start() > 0:
        issues.append("TRAILING_ORPHAN_HEADING")
        suggestions.append("Chunk ends with an orphan Markdown heading. Relocate heading to the next chunk.")

    # 4. Table Structure
    if "|" in clean_text:
        lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
        has_table_sep = any(re.match(r"^\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?$", line) for line in lines)
        if any(line.startswith("|") for line in lines) and not has_table_sep:
            issues.append("MALFORMED_TABLE")
            suggestions.append("Markdown table missing separator row (|---|---|); columns will not parse properly.")

    # Estimate preliminary quality score (0.0 to 1.0)
    penalty = len(issues) * 0.18
    if "CRITICAL_TRUNCATION" in issues:
        penalty += 0.35
    score = max(0.05, min(1.0, 1.0 - penalty))

    return {
        "token_count": token_count,
        "is_safe_budget": min_tokens <= token_count <= 200,
        "is_truncated": token_count > 200,
        "is_micro": token_count < min_tokens,
        "quality_score": round(score, 3),
        "issues": issues,
        "suggestions": suggestions,
    }


def auto_normalize_edited_chunk(
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any], List[str]]:
    """
    Applies the full 5-pass normalizer to the edited text and metadata:
    - Adds context breadcrumb prefixes
    - Cleans punctuation and TOC dots
    - Slices or rebalances paragraphs dynamically
    """
    normalizer = ChunkNormalizer()
    chunk_in = NormalizedChunk(
        chunk_id="preview_chunk",
        text=text,
        metadata=dict(metadata or {}),
    )
    result = normalizer.normalize_chunks([chunk_in])
    if not result:
        return text, metadata or {}, ["Normalizer produced empty output."]

    normalized_text = result[0].text
    normalized_meta = result[0].metadata

    changes: List[str] = []
    if len(result) > 1:
        changes.append(f"Content was dynamically partitioned into {len(result)} balanced parts.")
    if normalized_text != text:
        changes.append("Formatting, whitespace, or breadcrumb headers were refined.")

    return normalized_text, normalized_meta, changes


def edit_and_ingest_chunk(
    chunk_id: str,
    new_text: str,
    metadata: Optional[Dict[str, Any]] = None,
    collection_name: str = COLLECTION_NAME,
    persist_directory: Optional[str] = None,
    reviewer_notes: str = "Manually edited and approved in Chunk Quality Studio",
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Atomically ingests or updates an edited chunk into ChromaDB:
    1. Validates text is non-empty and below hard ceiling.
    2. Enforces canonical metadata schema (strings/ints/floats).
    3. Adds vector embedding to ChromaDB.
    4. Removes from both quarantine store and staged review queue.
    """
    if not chunk_id or not new_text.strip():
        return False, "Chunk ID and non-empty text are required.", {}

    val_res = validate_chunk_content(new_text, metadata)
    if val_res["is_truncated"]:
        return (
            False,
            f"Cannot ingest chunk: text is {val_res['token_count']} tokens (exceeds 200-token ceiling / exceeds 245-token ceiling). Please shorten or partition first.",
            val_res,
        )
    if val_res["is_micro"]:
        # Attempt auto-normalization with context prefix to reach optimal [80, 200] density
        norm_txt, norm_meta, _ = auto_normalize_edited_chunk(new_text, metadata)
        norm_tokens = ChunkNormalizer().count_tokens(norm_txt)
        if norm_tokens < 80:
            return (
                False,
                f"Cannot ingest chunk: text is only {val_res['token_count']} tokens (strict optimal density requires 80–200 tokens). Please consolidate with neighboring text before saving.",
                val_res,
            )
        new_text = norm_txt
        metadata = norm_meta
        val_res = validate_chunk_content(new_text, metadata)

    try:
        store = ChromaVectorStore(
            collection_name=collection_name,
            persist_directory=persist_directory or str(Path(BASE_DIR) / ".chroma"),
        )

        clean_meta = dict(metadata or {})
        sanitized_meta: Dict[str, Any] = {}
        for k, v in clean_meta.items():
            if isinstance(v, (list, tuple)):
                sanitized_meta[k] = " > ".join(str(item) for item in v)
            elif v is None:
                sanitized_meta[k] = ""
            elif isinstance(v, (str, int, float, bool)):
                sanitized_meta[k] = v
            else:
                sanitized_meta[k] = str(v)

        sanitized_meta["token_count"] = val_res["token_count"]
        sanitized_meta["last_edited_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        sanitized_meta["editorial_status"] = "manually_reviewed_and_approved"
        sanitized_meta["reviewer_notes"] = reviewer_notes

        # Upsert document with vector embedding
        store.add_documents([{"id": chunk_id, "text": new_text, "metadata": sanitized_meta}])

        # Clear from quarantine store if it was archived
        quarantine = load_quarantined_chunks()
        if chunk_id in quarantine:
            del quarantine[chunk_id]
            save_quarantined_chunks(quarantine)

        # Clear from pre-ingestion staged review if it was pending
        remove_from_staged_review(chunk_id)

        msg = f"Chunk '{chunk_id}' successfully updated and indexed in ChromaDB ({val_res['token_count']} tokens, CQI ~{val_res['quality_score']})."
        logger.info(msg)
        return True, msg, val_res
    except Exception as exc:
        logger.error("Failed to edit and ingest chunk %s: %s", chunk_id, exc)
        return False, f"Failed to ingest edited chunk into ChromaDB: {exc}", val_res

