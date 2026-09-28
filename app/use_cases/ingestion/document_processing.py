from app.domain.entities.chunk_metadata import build_chunk_metadata
from app.domain.ports.document_processing import ProcessedDocument
from app.infrastructure.document.plaintext_processor import (
    SUPPORTED_EXTENSIONS,
    chunk_text,
    extract_text_from_bytes,
    extract_text_from_document,
)

def build_chunk_records_from_processed(
    processed: ProcessedDocument,
    document_id: str,
    project_id: str | None = None,
    source: str | None = None,
    file_type: str | None = None,
    version: str | None = None,
) -> list[dict]:
    """Build store-ready chunk records from a port ``ProcessedDocument``.

    The canonical metadata contract is built by
    :func:`build_chunk_metadata`; this function only surrounds it with the
    record envelope the vector store expects and adds the two pre-existing
    non-canonical keys, ``file_type`` and ``version``, which the document
    entity owns and the store has always carried.

    Both ingestion paths therefore stay interchangeable, and every chunk
    exposes the canonical keys. Absent structure is omitted rather than
    defaulted, so nothing is invented and the existing citation fallbacks still
    apply.

    ``file_type`` is the caller's already-resolved type and takes precedence
    over the parser's own report, keeping the document entity and the chunk
    metadata in agreement. Document identity and authorization scope come from
    the caller, never from the parsed content. Record ids are positional so
    they stay unique and contiguous regardless of the ordinals a chunker
    reports.
    """
    resolved_file_type = (file_type or processed.file_type or "text").lstrip(".")

    records: list[dict] = []
    entries = build_chunk_metadata(
        processed,
        document_id=document_id,
        source_filename=source or document_id,
        project_id=project_id,
    )
    for position, (entry, chunk) in enumerate(zip(entries, processed.chunks)):
        metadata = entry.as_dict()
        # Pre-canonical keys retrieval and citation code still read. Derived from
        # the canonical fields, so the two names cannot drift apart.
        metadata.update(entry.as_legacy())
        metadata["file_type"] = resolved_file_type
        metadata["version"] = version or "1.0"
        records.append(
            {
                "id": f"{document_id}-{position}",
                "text": chunk.text,
                "metadata": metadata,
            }
        )
    return records









