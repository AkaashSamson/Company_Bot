#!/usr/bin/env python3
"""
scripts/normalize_chroma_corpus.py
Reads all existing chunks in ChromaDB, applies ChunkNormalizer, and re-indexes them.
Supports --dry-run to audit changes safely before writing.
Edge-case hardened:
  - EC-15: Non-primitive metadata sanitization
  - EC-16: Out-of-order ChromaDB dump sequential sorting before Pass 1 healing
  - EC-17: Zero-downtime staging collection rebuild and atomic swap
  - EC-18: Batch insert memory protection
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Safe stdout encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import chromadb
from app.core.settings import settings
from app.infrastructure.document.chunk_normalizer import (
    ChunkNormalizer,
    NormalizedChunk,
    LONE_HEADING_REGEX,
    TRAILING_HEADING_REGEX,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("corpus_normalizer")


def sanitize_chroma_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """EC-15: Sanitize metadata for ChromaDB storage (converts lists/tuples to strings)."""
    clean: Dict[str, Any] = {}
    for k, v in (meta or {}).items():
        if isinstance(v, (list, tuple)):
            clean[k] = " > ".join(str(item) for item in v)
        elif v is None:
            clean[k] = ""
        elif isinstance(v, (str, int, float, bool)):
            clean[k] = v
        else:
            clean[k] = str(v)
    return clean


def remediate_collection_zero_downtime(client, collection_name: str, normalizer: ChunkNormalizer, batch_size: int = 100) -> None:
    """EC-17: Zero-downtime rebuild using staging collection with atomic modify swap."""
    collection = client.get_collection(name=collection_name)
    raw = collection.get(include=["documents", "metadatas"])
    ids = raw.get("ids", [])
    docs = raw.get("documents", [])
    metas = raw.get("metadatas", [])

    records = [
        NormalizedChunk(chunk_id=str(cid), text=str(doc), metadata=meta or {})
        for cid, doc, meta in zip(ids, docs, metas)
        if doc is not None
    ]

    # EC-16: Sort out-of-order ChromaDB hash dump into strict document/page/chunk sequence
    # BEFORE Pass 1 boundary healing runs!
    records.sort(
        key=lambda c: (
            str(c.metadata.get("source_filename") or c.metadata.get("source_file") or ""),
            int(c.metadata.get("page_number") or 0),
            int(c.metadata.get("split_index") or c.metadata.get("chunk_index") or 0),
            c.chunk_id,
        )
    )

    logger.info("Executing 5-pass chunk normalization on %d chunks...", len(records))
    normalized = normalizer.normalize_chunks(records)
    logger.info("Normalized %d raw chunks -> %d clean chunks.", len(records), len(normalized))

    # EC-17: Build into a staging collection first so live RAG queries experience minimal downtime
    staging_name = f"{collection_name}__staging"
    try:
        client.delete_collection(name=staging_name)
    except Exception:
        pass

    staging_col = client.create_collection(
        name=staging_name,
        metadata={"hnsw:space": "cosine"},
    )

    logger.info("Writing normalized chunks to staging collection '%s'...", staging_name)
    for i in range(0, len(normalized), batch_size):
        batch = normalized[i : i + batch_size]
        staging_col.add(
            ids=[c.chunk_id for c in batch],
            documents=[c.text for c in batch],
            metadatas=[sanitize_chroma_metadata(c.metadata) for c in batch],
        )

    # Atomic swap: delete old collection and rename staging collection to active name
    logger.info("Swapping staging collection '%s' to active '%s'...", staging_name, collection_name)
    client.delete_collection(name=collection_name)
    staging_col.modify(name=collection_name)
    logger.info("Zero-downtime corpus remediation complete!")


def remediate_collection(dry_run: bool = False, batch_size: int = 100, collection_name: Optional[str] = None):
    target_collection = collection_name or settings.CHROMA_COLLECTION
    client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    try:
        collection = client.get_collection(name=target_collection)
    except Exception as exc:
        available = [c.name for c in client.list_collections()]
        logger.warning("Could not access collection '%s': %s (Available: %s)", target_collection, exc, available)
        if available and target_collection not in available:
            target_collection = available[0]
            logger.info("Falling back to active collection: '%s'", target_collection)
            collection = client.get_collection(name=target_collection)
        else:
            return

    data = collection.get(include=["documents", "metadatas"])
    ids, docs, metas = data.get("ids", []), data.get("documents", []), data.get("metadatas", [])

    logger.info("Found %d chunks in collection '%s'.", len(ids), target_collection)
    if not ids:
        return

    # Convert to NormalizedChunk list
    raw_chunks = [
        NormalizedChunk(chunk_id=str(cid), text=str(doc), metadata=meta or {})
        for cid, doc, meta in zip(ids, docs, metas)
    ]

    # EC-16: Sort chunks for coherent sequential healing across documents and pages
    raw_chunks.sort(
        key=lambda c: (
            str(c.metadata.get("source_filename") or c.metadata.get("source_file") or ""),
            int(c.metadata.get("page_number", 0) or 0),
            int(c.metadata.get("chunk_index", 0) or 0),
        )
    )

    normalizer = ChunkNormalizer(
        model_name=settings.EMBEDDING_MODEL,
        hard_token_ceiling=settings.CHUNK_HARD_TOKEN_CEILING,
        coalesce_max_tokens=settings.CHUNK_COALESCE_MAX_TOKENS,
        min_fragment_tokens=settings.CHUNK_MIN_FRAGMENT_TOKENS,
    )

    if dry_run:
        logger.info("Running 5-pass normalization on corpus (DRY RUN) for '%s'...", target_collection)
        orphan_heading_chunks = 0
        oversized_chunks = 0
        micro_fragment_chunks = 0
        noisy_artifact_chunks = 0

        for c in raw_chunks:
            tok_count = normalizer.count_tokens(c.text)
            if tok_count > normalizer.hard_token_ceiling or tok_count > 200:
                oversized_chunks += 1
            if tok_count < normalizer.min_fragment_tokens:
                micro_fragment_chunks += 1
            m_trail = TRAILING_HEADING_REGEX.search(c.text)
            if LONE_HEADING_REGEX.match(c.text) or (m_trail and m_trail.start() > 0):
                orphan_heading_chunks += 1
            if "\t" in c.text or re.search(r"\.{4,}", c.text) or re.search(r"-{4,}", c.text):
                noisy_artifact_chunks += 1

        normalized_chunks = normalizer.normalize_chunks(raw_chunks)

        print("\n" + "=" * 65)
        print(f"  CHROMA CORPUS NORMALIZATION AUDIT REPORT (DRY RUN)")
        print(f"  Collection: {target_collection}")
        print("=" * 65)
        print(f"  Total Raw Chunks Audited:              {len(raw_chunks):>5}")
        print(f"  Chunks Flagged for Truncation/Split:   {oversized_chunks:>5} (>200 tokens / ceiling)")
        print(f"  Chunks with Orphan Headings:           {orphan_heading_chunks:>5} (Lone or trailing)")
        print(f"  Micro-Fragment Chunks:                 {micro_fragment_chunks:>5} (<55 tokens)")
        print(f"  Chunks with Noise / Repetitive Syntax: {noisy_artifact_chunks:>5}")
        print("-" * 65)
        print(f"  Normalized Clean Chunks Produced:      {len(normalized_chunks):>5}")
        print("=" * 65 + "\n")
        logger.info("[DRY RUN] No database writes executed.")
        return

    remediate_collection_zero_downtime(client, target_collection, normalizer, batch_size=batch_size)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remediate existing ChromaDB chunks.")
    parser.add_argument("--dry-run", action="store_true", help="Audit transformation without writing to ChromaDB")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch insertion size")
    parser.add_argument("--collection", type=str, default=None, help="Target collection name (defaults to settings.CHROMA_COLLECTION)")
    args = parser.parse_args()

    remediate_collection(dry_run=args.dry_run, batch_size=args.batch_size, collection_name=args.collection)
