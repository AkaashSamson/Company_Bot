import base64
import logging
import re
from pathlib import Path

from app.core.settings import (
    BASE_DIR,
    COLLECTION_NAME,
    DOCUMENTS_DIR,
    ENABLE_CHUNK_NORMALIZATION,
    ENABLE_SEMANTIC_CHUNK_MERGING,
    CHUNK_NORMALIZER_HARD_CEILING,
    CHUNK_NORMALIZER_MIN_FRAGMENT_TOKENS,
    SEMANTIC_MERGE_ABSORBER_MAX_CHARS,
    SEMANTIC_MERGE_CANDIDATE_MAX_CHARS,
    SEMANTIC_MERGE_MAX_CHARS,
    SEMANTIC_MERGE_SIMILARITY_THRESHOLD,
)
from app.domain.ports.document_processing import DocumentProcessingPort
from app.infrastructure.document.bridge_linked_chunking import (
    link_store_records_with_bridges,
)
from app.infrastructure.document.chunk_normalizer import ChunkNormalizer
from app.infrastructure.document.chunking_strategies import (
    CHUNK_STRATEGIES_META,
    apply_chunking_strategy,
)
from app.infrastructure.document.processor_factory import build_document_processor
from app.infrastructure.ingestion.semantic_merger import (
    SemanticMergeConfig,
    semantic_merge_chunk_records,
)
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
    enable_semantic_merging: bool | None = None,
    enable_chunk_normalization: bool | None = None,
    chunking_strategy: str | None = None,
    target_tokens: int | None = None,
    overlap_pct: int | None = None,
    enable_bridge_linking: bool = True,
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

    resolved_file_type = (processed.file_type or extension).lstrip(".")

    if chunking_strategy and chunking_strategy in CHUNK_STRATEGIES_META:
        full_text = "\n\n".join(c.text for c in processed.chunks) if processed.chunks else ""
        if not full_text.strip() and raw:
            try:
                full_text = raw.decode("utf-8", errors="ignore")
            except Exception:
                pass
        strat_chunks = apply_chunking_strategy(
            strategy_key=chunking_strategy,
            text=full_text,
            target_tokens=target_tokens,
            overlap_pct=overlap_pct,
            doc_prefix=document.document_id,
            enable_bridge_links=enable_bridge_linking,
        )
        records = [
            {
                "id": sc.id,
                "text": sc.text,
                "metadata": {
                    "document_id": document.document_id,
                    "doc_id": document.document_id,
                    "source_filename": document.document_name,
                    "source": document.document_name,
                    "project_id": getattr(document, "project_id", "unassigned"),
                    "version": getattr(document, "version", "1.0"),
                    "file_type": resolved_file_type,
                    "chunk_index": sc.sequence_index,
                    "sequence_index": sc.sequence_index,
                    "previous_chunk_id": sc.previous_chunk_id,
                    "next_chunk_id": sc.next_chunk_id,
                    "strategy": sc.strategy,
                    "token_count": sc.token_count,
                    "content_type": "text",
                    "parent_id": getattr(sc, "parent_id", None) or (sc.metadata.get("parent_id") if hasattr(sc, "metadata") else None),
                    "parent_text": getattr(sc, "parent_text", None) or (sc.metadata.get("parent_text") if hasattr(sc, "metadata") else None),
                    **(
                        {
                            "bridge_type": sc.bridge_to_next["relationship"],
                            "bridge_confidence": sc.bridge_to_next["confidence"],
                            "bridge_to_next_id": sc.bridge_to_next["bridge_id"],
                            "bridge_rationale": sc.bridge_to_next["rationale"],
                        }
                        if sc.bridge_to_next
                        else {}
                    ),
                },
            }
            for sc in strat_chunks
        ]
    else:
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

    # Deterministic 5-pass Chunk Normalization (token budgets, table headers, cutoff tags)
    should_normalize = ENABLE_CHUNK_NORMALIZATION if enable_chunk_normalization is None else enable_chunk_normalization
    if should_normalize and records:
        normalizer = ChunkNormalizer(
            hard_token_ceiling=CHUNK_NORMALIZER_HARD_CEILING,
            min_fragment_tokens=CHUNK_NORMALIZER_MIN_FRAGMENT_TOKENS,
        )
        records = normalizer.normalize_chunk_records(records)

    # Semantic Chunk Merging pass: consolidate micro-fragments and noise before indexing
    should_merge = ENABLE_SEMANTIC_CHUNK_MERGING if enable_semantic_merging is None else enable_semantic_merging
    if should_merge and len(records) > 1:
        cfg = SemanticMergeConfig(
            max_chunk_chars=SEMANTIC_MERGE_MAX_CHARS,
            absorber_max_chars=SEMANTIC_MERGE_ABSORBER_MAX_CHARS,
            candidate_max_chars=SEMANTIC_MERGE_CANDIDATE_MAX_CHARS,
            similarity_threshold=SEMANTIC_MERGE_SIMILARITY_THRESHOLD,
            scope_field="document_id",
            enabled=True,
        )
        records, merge_res = semantic_merge_chunk_records(records, config=cfg)
        if merge_res.absorbed_chunks_count > 0:
            logger.info(
                "semantic chunk merging consolidated %d chunks (reduction: %.1f%%) for %r",
                merge_res.absorbed_chunks_count,
                merge_res.reduction_percentage,
                document.document_id,
            )
            if should_normalize:
                records = normalizer.normalize_chunk_records(records)


    # Establish Doubly Linked List pointers and typed boundary bridges across all chunks
    if enable_bridge_linking and records:
        records = link_store_records_with_bridges(records, doc_id=document.document_id)

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