import base64
import logging
import re
from pathlib import Path

from app.core.settings import BASE_DIR, COLLECTION_NAME, DOCUMENTS_DIR
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.use_cases.ingestion.document_processing import (
    SUPPORTED_EXTENSIONS,
    build_chunk_records,
    extract_text_from_bytes,
    extract_text_from_document,
)

logger = logging.getLogger("knowlayer.ingestion")

_UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9 _.\-]+")


def _safe_document_id(document_id: str) -> str:
    candidate = _UNSAFE_ID_CHARS.sub("_", document_id).strip(" ._")
    if not candidate:
        raise ValueError("document_id contains no usable filename characters")
    return candidate


def _detect_extension(raw: bytes, name: str) -> str:
    """Resolve the file type for a content upload from the actual bytes.

    DOCX files are zip archives carrying a content-types part; the remaining
    supported formats are UTF-8 text. The name extension is used only as a
    fallback when the bytes cannot be classified.
    """
    if raw[:2] == b"PK" and b"[Content_Types].xml" in raw[:4096]:
        return ".docx"
    try:
        raw.decode("utf-8")
        return ".txt"
    except UnicodeDecodeError:
        return Path(name).suffix.lower()


def provision_document(source_path, document, content=None, store=None) -> int:
    """Extract, chunk, and embed a document into the vector store.

    - ``content``: base64-encoded file contents (upload path).
    - ``source_path``: path of a file already on disk under DOCUMENTS_DIR.
    - ``store``: optional vector store to write chunks into; defaults to the
      configured collection in ``.chroma``.
    - Neither ``content`` nor ``source_path``: metadata-only registration, returns 0.
    """
    if source_path is None and content is None:
        return 0

    if content is not None:
        try:
            raw = base64.b64decode(content, validate=True)
        except Exception as error:
            raise ValueError("Document content is not valid base64") from error

        extension = _detect_extension(raw, document.document_name)
        if extension not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise ValueError(f"Unsupported document type: {extension or '(none)'} (supported: {supported})")

        text = extract_text_from_bytes(raw, f"upload{extension}")

        destination = Path(DOCUMENTS_DIR) / f"{_safe_document_id(document.document_id)}{extension}"
        destination.write_bytes(raw)
        logger.info("saved uploaded document to %s", destination)
    else:
        text = extract_text_from_document(source_path)

    records = build_chunk_records(
        text,
        document_id=document.document_id,
        project_id=getattr(document, "project_id", None),
        source=document.document_name,
    )
    if not records:
        logger.warning("no chunks produced for document %r", document.document_id)
        return 0

    store = store or ChromaVectorStore(collection_name=COLLECTION_NAME, persist_directory=str(BASE_DIR / ".chroma"))
    store.add_documents(records)
    logger.info("provisioned %d chunks for document %r", len(records), document.document_id)
    return len(records)


def remove_document(document_id: str) -> None:
    """Remove a document's vectors from the vector store (exact id match)."""
    store = ChromaVectorStore(collection_name=COLLECTION_NAME, persist_directory=str(BASE_DIR / ".chroma"))
    store.collection.delete(where={"document_id": document_id})
    logger.info("removed vectors for document %r (total=%d)", document_id, store.collection.count())