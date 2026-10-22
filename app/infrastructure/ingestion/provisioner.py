import base64
import logging
import re
from pathlib import Path

from app.core.settings import BASE_DIR, COLLECTION_NAME, DOCUMENTS_DIR
from app.domain.ports.document_processing import DocumentProcessingPort
from app.infrastructure.document.processor_factory import build_document_processor
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.use_cases.ingestion.document_processing import build_chunk_records_from_processed

logger = logging.getLogger("knowlayer.ingestion")

_UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9 _.\-]+")


def _safe_document_id(document_id: str) -> str:
    candidate = _UNSAFE_ID_CHARS.sub("_", document_id).strip(" ._")
    if not candidate:
        raise ValueError("document_id contains no usable filename characters")
    return candidate


def _detect_extension(raw: bytes, name: str) -> str:
    """Resolve the file type for a content upload.

    A supplied filename extension is authoritative so formats such as CSV,
    HTML, and PDF are not misclassified merely because their bytes are
    decodable as UTF-8. Byte sniffing remains the fallback for extensionless
    uploads, including DOCX and plain text content.
    """
    suffix = Path(name).suffix.lower()
    if suffix:
        return suffix

    if raw[:2] == b"PK" and b"[Content_Types].xml" in raw[:4096]:
        return ".docx"
    try:
        raw.decode("utf-8")
        return ".txt"
    except UnicodeDecodeError:
        return ""


def provision_document(
    source_path,
    document,
    content=None,
    store=None,
    processor: DocumentProcessingPort | None = None,
) -> int:
    """Extract, chunk, and embed a document into the vector store.

    - ``content``: base64-encoded file contents (upload path).
    - ``source_path``: path of a file already on disk under DOCUMENTS_DIR.
    - ``store``: optional vector store to write chunks into; defaults to the
      configured collection in ``.chroma``.
    - ``processor``: any ``DocumentProcessingPort`` implementation. When
      omitted the configured processor is built by
      :func:`build_document_processor`, which is the only place the concrete
      parsers are chosen. This module depends on the port, never on a parser.
    - Neither ``content`` nor ``source_path``: metadata-only registration, returns 0.

    Parsing and chunking always run through the port, so there is a single
    record-building path and every stored chunk carries the canonical metadata
    contract regardless of which processor ran.
    """
    if source_path is None and content is None:
        return 0

    if content is not None:
        try:
            raw = base64.b64decode(content, validate=True)
        except Exception as error:
            raise ValueError("Document content is not valid base64") from error

        extension = _detect_extension(raw, document.document_name)
        parse_name = f"upload{extension}"
    else:
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(source_path)
        raw = path.read_bytes()
        extension = path.suffix.lower()
        parse_name = path.name

    if processor is None:
        processor = build_document_processor()
    if not processor.supports(parse_name):
        supported = ", ".join(sorted(processor.supported_extensions()))
        raise ValueError(
            f"Unsupported document type: {extension or '(none)'} (supported: {supported})"
        )
    processed = processor.process(raw, parse_name)

    if content is not None:
        destination = Path(DOCUMENTS_DIR) / f"{_safe_document_id(document.document_id)}{extension}"
        destination.write_bytes(raw)
        logger.info("saved uploaded document to %s", destination)
        document.original_filename = document.original_filename or document.document_name
        document.file_type = (processed.file_type or extension).lstrip(".")
        document.storage_location = str(destination)
    else:
        document.original_filename = document.original_filename or Path(source_path).name
        document.file_type = document.file_type or (processed.file_type or extension).lstrip(".")
        document.storage_location = document.storage_location or str(source_path)

    records = build_chunk_records_from_processed(
        processed,
        document_id=document.document_id,
        project_id=getattr(document, "project_id", None),
        source=document.document_name,
        file_type=getattr(document, "file_type", None),
        version=getattr(document, "version", None),
    )
    if not records:
        logger.warning("no chunks produced for document %r", document.document_id)
        return 0

    store = store or ChromaVectorStore(collection_name=COLLECTION_NAME, persist_directory=str(BASE_DIR / ".chroma"))
    store.add_documents(records)
    logger.info("provisioned %d chunks for document %r", len(records), document.document_id)
    return len(records)


def remove_document(document_id: str, storage_location: str | None = None) -> None:
    """Remove a document's vectors from the vector store and clean up its file on disk."""
    try:
        store = ChromaVectorStore(collection_name=COLLECTION_NAME, persist_directory=str(BASE_DIR / ".chroma"))
        store.collection.delete(where={"document_id": document_id})
        logger.info("removed vectors for document %r (total=%d)", document_id, store.collection.count())
    except Exception as err:
        logger.warning("failed to remove vectors for document %r: %s", document_id, err)

    if storage_location:
        try:
            loc = Path(storage_location)
            if loc.is_file():
                loc.unlink()
                logger.info("removed document file at %s", loc)
        except Exception as err:
            logger.warning("failed to remove document storage file %s: %s", storage_location, err)

    try:
        safe_id = _safe_document_id(document_id)
        docs_path = Path(DOCUMENTS_DIR)
        if docs_path.exists():
            for file_path in docs_path.glob(f"{safe_id}.*"):
                if file_path.is_file():
                    file_path.unlink()
                    logger.info("removed document file %s", file_path)
    except Exception as err:
        logger.warning("failed to clean up files in DOCUMENTS_DIR for %r: %s", document_id, err)