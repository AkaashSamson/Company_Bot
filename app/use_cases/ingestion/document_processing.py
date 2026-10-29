from typing import List, Dict, Any, Optional
from pathlib import Path
import hashlib
import logging

from app.core.settings import settings
from app.domain.entities.chunk_metadata import build_chunk_metadata
from app.domain.entities.document_models import DocumentChunk
from app.domain.ports.document_processing import ProcessedDocument
from app.infrastructure.document.dynamic_section_assignor import DynamicSectionAssignor
from app.infrastructure.document.chunk_normalizer import ChunkNormalizer, NormalizedChunk
from app.infrastructure.vector.chroma_client import ChromaClient

logger = logging.getLogger(__name__)


def sanitize_chroma_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    EC-15: ChromaDB strictly requires str, int, float, or bool metadata values.
    Converts lists/tuples (like `page_span: [1, 2]`) to `"1 > 2"` and `None` to `""`.
    """
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


def ensure_fallback_contract_metadata(chunk: NormalizedChunk) -> NormalizedChunk:
    """
    EC-19: When CHUNK_NORMALIZER_ENABLED=False, ensure mandatory schema keys
    and [Policy: ... | Section: ...] headers still exist so downstream code never crashes.
    """
    meta = chunk.metadata
    src = str(meta.get("source_filename") or meta.get("source_file") or "General_Policy.pdf")
    h_path = str(meta.get("heading_hierarchy") or "General Policy")
    meta.setdefault("source_filename", src)
    meta.setdefault("page_number", 1)
    meta.setdefault("heading_hierarchy", h_path)
    meta.setdefault("hierarchy_path", h_path)
    meta.setdefault("section_heading", h_path.split(">")[-1].strip())
    meta.setdefault("chunk_type", "table" if chunk.text.count("|") >= 4 else "text")
    if not chunk.text.startswith("[Policy:"):
        stem = Path(src).stem.replace("_", " ")
        chunk.text = f"[Policy: {stem} | Section: {h_path}]\n{chunk.text}".strip()
    meta.setdefault(
        "content_hash", hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()[:16]
    )
    return chunk


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
    normalize: bool = False,
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

    if normalize and records:
        from app.infrastructure.document.chunk_normalizer import ChunkNormalizer
        records = ChunkNormalizer().normalize_chunk_records(records)

    return records


class DocumentIngestionUseCase:
    def __init__(self, chroma_client: Optional[ChromaClient] = None):
        if chroma_client is None:
            chroma_client = ChromaClient()
        self.chroma_client = chroma_client
        self.section_assignor = DynamicSectionAssignor()
        self.normalizer = ChunkNormalizer(
            model_name=settings.EMBEDDING_MODEL,
            hard_token_ceiling=settings.CHUNK_HARD_TOKEN_CEILING,
            coalesce_max_tokens=settings.CHUNK_COALESCE_MAX_TOKENS,
            min_fragment_tokens=settings.CHUNK_MIN_FRAGMENT_TOKENS,
        )

    def process_and_index_document(
        self,
        raw_chunks: List[Dict[str, Any]],  # List of dicts with 'text', 'metadata'
        source_filename: str,
        document_id: str,
        project_id: str,
    ) -> List[DocumentChunk]:
        """
        Executes raw extraction -> section tracking -> 5-pass normalization -> ChromaDB storage.
        """
        if not raw_chunks:
            return []

        # 1. Convert raw input dicts to NormalizedChunk containers
        raw_normalized = [
            NormalizedChunk(
                chunk_id=c.get("chunk_id", c.get("id", f"{document_id}_raw_{idx}")),
                text=c["text"],
                metadata={
                    **c.get("metadata", {}),
                    "source_filename": source_filename,
                    "document_id": document_id,
                    "project_id": project_id,
                },
            )
            for idx, c in enumerate(raw_chunks)
        ]

        # 2. Assign dynamic section hierarchy if enabled
        if settings.DYNAMIC_SECTION_TRACKING_ENABLED:
            raw_normalized = self.section_assignor.assign_sections_to_chunks(
                raw_normalized,
                document_title=Path(source_filename).stem,
            )

        # 3. Apply 5-pass chunk normalization or fallback metadata enforcement (EC-19)
        if settings.CHUNK_NORMALIZER_ENABLED:
            final_normalized = self.normalizer.normalize_chunks(raw_normalized)
        else:
            final_normalized = [ensure_fallback_contract_metadata(c) for c in raw_normalized]

        # 4. Convert to Domain Entities
        domain_chunks: List[DocumentChunk] = []
        texts_to_embed: List[str] = []
        ids_to_index: List[str] = []
        metas_to_index: List[Dict[str, Any]] = []

        for c in final_normalized:
            domain_chunk = DocumentChunk(
                chunk_id=c.chunk_id,
                document_id=document_id,
                text=c.text,  # Prefixed text: [Policy: ... | Section: ...]
                metadata=c.metadata,
            )
            domain_chunks.append(domain_chunk)

            ids_to_index.append(c.chunk_id)
            texts_to_embed.append(c.text)
            metas_to_index.append(c.metadata)

        # 5. Persist to ChromaDB in batches with sanitized metadata (EC-15 & EC-18)
        batch_size = 100
        for start in range(0, len(ids_to_index), batch_size):
            end = start + batch_size
            self.chroma_client.add_documents(
                collection_name=settings.CHROMA_COLLECTION,
                ids=ids_to_index[start:end],
                documents=texts_to_embed[start:end],
                metadatas=[sanitize_chroma_metadata(m) for m in metas_to_index[start:end]],
            )

        logger.info(
            "Successfully indexed %d normalized chunks for document '%s' (doc_id=%s)",
            len(domain_chunks),
            source_filename,
            document_id,
        )
        return domain_chunks
