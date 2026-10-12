from app.domain.entities.chunk_metadata import build_chunk_metadata
from app.domain.ports.document_processing import ProcessedDocument

def _contextualize(hierarchy_path: tuple[str, ...], chunk_text: str, budget_chars: int = 200) -> str:
    """Safely combine heading hierarchy with chunk text within a strict budget.
    
    1. Filters out unreasonably long headers (likely paragraphs misidentified by Docling).
    2. Takes the deepest headers first.
    3. Prepends them up to `budget_chars` limit.
    """
    if not hierarchy_path:
        return chunk_text
        
    # Filter out bad headers (e.g. > 100 characters)
    valid_headers = [h for h in hierarchy_path if len(h) <= 100]
    if not valid_headers:
        return chunk_text
        
    # Build prefix starting from deepest/most relevant headers
    prefix_parts = []
    current_length = 0
    
    for h in reversed(valid_headers):
        if current_length + len(h) + 3 > budget_chars:
            break
        prefix_parts.insert(0, h)
        current_length += len(h) + 3
        
    if not prefix_parts:
        return chunk_text
        
    hierarchy_prefix = " > ".join(prefix_parts)
    return f"{hierarchy_prefix}\n\n{chunk_text}"


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
        for key, value in chunk.metadata.items():
            if key not in {
                "document_id",
                "project_id",
                "source_filename",
                "page_number",
                "section_heading",
                "hierarchy_path",
                "chunk_index",
                "content_type",
            }:
                metadata[key] = value
        text_with_context = _contextualize(entry.hierarchy_path, chunk.text)
        
        records.append(
            {
                "id": f"{document_id}-{position}",
                "text": text_with_context,
                "metadata": metadata,
            }
        )
    return records









