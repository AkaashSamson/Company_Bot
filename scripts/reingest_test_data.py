"""
Script to wipe the ChromaDB vector store and re-ingest all documents from test_data/.

Usage:
    python scripts/reingest_test_data.py [--data-dir test_data] [--keep-existing]
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.core.settings import BASE_DIR, COLLECTION_NAME
from app.domain.entities.organization_models import Document
from app.infrastructure.ingestion.provisioner import provision_document
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.infrastructure.document.processor_factory import build_document_processor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("knowlayer.reingest")

# Known project scoping rules for test documents
PROJECT_SCOPES = {
    "TEST-001.docx": "121",
    "DOC-002.docx": "121",
    "DOC-003.docx": "121",
    "DOC-006.docx": "121",
}


def wipe_chroma_store(store: ChromaVectorStore):
    """Safely wipe the current collection in ChromaDB."""
    logger.info("Wiping ChromaDB collection %r...", store.collection_name)
    try:
        store.client.delete_collection(name=store.collection_name)
    except Exception as e:
        logger.warning("Could not delete collection %s (may not exist): %s", store.collection_name, e)

    store.collection = store.client.get_or_create_collection(
        name=store.collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info("ChromaDB collection %r recreated successfully (count=%d).", store.collection_name, store.collection.count())


def reingest_documents(data_dir: Path, wipe: bool = True):
    if not data_dir.exists():
        logger.error("Data directory does not exist: %s", data_dir)
        sys.exit(1)

    store = ChromaVectorStore(
        collection_name=COLLECTION_NAME,
        persist_directory=str(BASE_DIR / ".chroma"),
    )

    if wipe:
        wipe_chroma_store(store)

    supported_extensions = {".docx", ".pdf", ".txt", ".md"}
    doc_files = [
        f for f in sorted(data_dir.iterdir())
        if f.is_file() and f.suffix.lower() in supported_extensions
    ]

    if not doc_files:
        logger.warning("No supported document files found in %s", data_dir)
        return

    logger.info("Found %d documents to ingest from %s", len(doc_files), data_dir)
    processor = build_document_processor()
    logger.info("Using document processor: %s", type(processor).__name__)

    total_chunks = 0
    start_total_time = time.time()
    summary_report = []

    for file_path in doc_files:
        file_name = file_path.name
        doc_id = file_path.stem
        project_id = PROJECT_SCOPES.get(file_name, "unassigned")

        doc_entity = Document(
            document_id=doc_id,
            document_name=file_name,
            project_id=project_id,
            original_filename=file_name,
            file_type=file_path.suffix.lower().lstrip("."),
            version="1.0",
        )

        logger.info("Processing %s (project_id=%s)...", file_name, project_id)
        file_start = time.time()
        try:
            chunks_created = provision_document(
                source_path=file_path,
                document=doc_entity,
                store=store,
                processor=processor,
            )
            elapsed = time.time() - file_start
            total_chunks += chunks_created
            summary_report.append({
                "file": file_name,
                "project_id": project_id,
                "chunks": chunks_created,
                "time_sec": round(elapsed, 2),
                "status": "SUCCESS",
            })
            logger.info("-> Ingested %d chunks from %s in %.2fs", chunks_created, file_name, elapsed)
        except Exception as exc:
            elapsed = time.time() - file_start
            logger.error("Failed to ingest %s: %s", file_name, exc)
            summary_report.append({
                "file": file_name,
                "project_id": project_id,
                "chunks": 0,
                "time_sec": round(elapsed, 2),
                "status": f"ERROR: {exc}",
            })

    total_time = time.time() - start_total_time
    logger.info("=" * 60)
    logger.info("INGESTION COMPLETE in %.2fs", total_time)
    logger.info("Total Chunks in ChromaDB: %d", store.collection.count())
    logger.info("=" * 60)

    print("\n--- INGESTION SUMMARY ---")
    for row in summary_report:
        print(f"[{row['status']}] {row['file']:<32} | Scope: {row['project_id']:<10} | Chunks: {row['chunks']:<4} | Time: {row['time_sec']}s")
    print("-" * 60)
    print(f"Total Stored Chunks in Collection: {store.collection.count():,}")


def main():
    parser = argparse.ArgumentParser(description="Wipe and re-ingest ChromaDB vector store.")
    parser.add_argument("--data-dir", default=str(_REPO_ROOT / "test_data"), help="Directory containing documents to ingest")
    parser.add_argument("--keep-existing", action="store_true", help="Do not wipe ChromaDB before ingesting")
    args = parser.parse_args()

    reingest_documents(data_dir=Path(args.data_dir), wipe=not args.keep_existing)


if __name__ == "__main__":
    main()
