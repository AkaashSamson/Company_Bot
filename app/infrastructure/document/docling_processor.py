"""Docling-backed implementation of :class:`DocumentProcessingPort`.

This module is the *only* place in the application that imports Docling.
Conversion and chunking are delegated to ``DocumentConverter`` and
``HybridChunker``; their result is translated into the neutral
``ProcessedDocument`` / ``ProcessedChunk`` contract before it is returned, so
no Docling object crosses the adapter boundary.

Both the converter and the chunker are constructed lazily and can be injected,
which keeps the adapter independently testable: tests supply stand-ins and
exercise the structural mapping without loading layout models or a tokenizer.
"""
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Sequence

from docling.chunking import HybridChunker
from docling.datamodel.base_models import DocumentStream, FormatToExtensions, InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode,
    RapidOcrOptions,
)
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc import DocItemLabel

from app.core.settings import (
    DOCLING_CITATION_PDF_DIR,
    DOCLING_CITATION_PDF_ENABLED,
    DOCLING_FILTER_HEADERS_FOOTERS,
    DOCLING_LAYOUT_AWARE,
    DOCLING_MAX_TOKENS,
    DOCLING_OCR_ENABLED,
    DOCLING_TABLE_STRUCTURE_ENABLED,
    DOCLING_VISUAL_ENRICHMENT_ENABLED,
    EMBEDDING_MODEL,
)
from app.domain.ports.document_processing import (
    DocumentProcessingPort,
    MetadataValue,
    ProcessedChunk,
    ProcessedDocument,
    SectionHeading,
)
from app.infrastructure.document.visual_enrichment import VisualEnricher
from app.infrastructure.document.citation_pdf import map_docx_pages

logger = logging.getLogger("knowlayer.ingestion")


# Formats Docling can recognise but this adapter does not claim: they need
# external binaries or optional extras outside the application's dependency
# set, or they share an extension with other formats so routing is ambiguous.
_EXCLUDED_FORMATS = frozenset(
    {
        InputFormat.AUDIO,  # requires the `asr` extra and ffmpeg
        InputFormat.VIDEO,  # requires the `asr` extra and ffmpeg
        InputFormat.DOC,
        InputFormat.PPT,
        InputFormat.XLS,  # legacy binary Office formats require LibreOffice
        InputFormat.RTF,
        InputFormat.ODT,
        InputFormat.ODS,
        InputFormat.ODP,
        InputFormat.IWORK_PAGES,  # requires the `format-iwork` extra
        InputFormat.METS_GBS,  # multi-part archive, not a single upload
        InputFormat.XML_JATS,
        InputFormat.XML_XBRL,
        InputFormat.XML_DOCLANG,
        InputFormat.XML_USPTO,  # all four claim `.xml`, so routing is ambiguous
    }
)


def _build_extension_map() -> dict[str, InputFormat]:
    """Derive the extension -> format map from Docling's own registry.

    Nothing is hard-coded, so the adapter automatically tracks whatever formats
    the installed Docling release can parse. Earlier formats win for extensions
    claimed more than once.
    """
    mapping: dict[str, InputFormat] = {}
    for file_format, extensions in dict(FormatToExtensions).items():
        if file_format in _EXCLUDED_FORMATS:
            continue
        for extension in extensions:
            mapping.setdefault(extension.lower(), file_format)
    return mapping


_EXTENSION_TO_FORMAT = _build_extension_map()
_HEADING_LABEL = str(DocItemLabel.SECTION_HEADER.value)


def _label_of(item: Any) -> str:
    """Return an item's element kind as a lower-case neutral string."""
    label = getattr(item, "label", "")
    return str(getattr(label, "value", label) or "").strip().lower()


def _page_of(item: Any) -> int | None:
    """Return the lowest page an item appears on, or ``None`` when unknown.

    Docling leaves provenance empty for formats without pagination (DOCX, HTML,
    Markdown), so ``None`` is the normal answer there and must not be guessed.
    """
    pages = [
        page
        for page in (getattr(entry, "page_no", None) for entry in (getattr(item, "prov", None) or []))
        if isinstance(page, int) and not isinstance(page, bool)
    ]
    return min(pages) if pages else None


def _bbox_of(item: Any) -> tuple[float, float, float, float] | None:
    """Extract spatial bounding box (l, t, r, b) from item provenance."""
    for entry in getattr(item, "prov", None) or []:
        bbox = getattr(entry, "bbox", None)
        if bbox is not None:
            l = getattr(bbox, "l", None)
            t = getattr(bbox, "t", None)
            r = getattr(bbox, "r", None)
            b = getattr(bbox, "b", None)
            if all(isinstance(v, (int, float)) for v in (l, t, r, b)):
                return (float(l), float(t), float(r), float(b))
    return None


def _is_torchvision_available() -> bool:
    """Return True only when torchvision is importable AND transformers agrees it exists.

    The transformers ``is_torchvision_available`` helper is the canonical check
    used by ``AutoImageProcessor``, so we mirror it here to pre-empt the error
    that would otherwise surface at layout-model load time.
    """
    try:
        import torchvision  # noqa: F401
        from transformers.utils import is_torchvision_available as _tv_check
        return _tv_check()
    except Exception:
        return False


def _build_pdf_format_option() -> PdfFormatOption:
    """Build layout-aware PDF pipeline options with TableFormer, OCR, and reading order.

    Falls back to a plain ``PdfFormatOption`` when the layout model's
    ``AutoImageProcessor`` dependency (torchvision) is unavailable in the
    current Python environment, so ingestion never hard-fails due to a missing
    optional dependency.
    """
    pipeline_options = PdfPipelineOptions()
    if DOCLING_LAYOUT_AWARE:
        # Guard: layout-heron uses AutoImageProcessor which requires torchvision.
        # In some Windows environments (e.g. uvicorn --reload multiprocessing
        # workers that inherit a different interpreter) torchvision may not be
        # importable even though it is installed.  We degrade gracefully instead
        # of letting the whole ingestion fail.
        if not _is_torchvision_available():
            logger.warning(
                "DOCLING_LAYOUT_AWARE is enabled but torchvision is not available "
                "in this Python process.  Falling back to standard (non-layout-aware) "
                "PDF parsing.  Install torchvision or ensure the correct interpreter "
                "is used to re-enable layout parsing."
            )
            return PdfFormatOption(pipeline_options=pipeline_options)

        pipeline_options.do_table_structure = DOCLING_TABLE_STRUCTURE_ENABLED
        if DOCLING_TABLE_STRUCTURE_ENABLED:
            try:
                pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
                pipeline_options.table_structure_options.do_cell_matching = True
            except Exception as e:
                logger.warning("Could not set TableFormer accurate mode: %s", e)

        pipeline_options.do_ocr = DOCLING_OCR_ENABLED
        if DOCLING_OCR_ENABLED:
            try:
                pipeline_options.ocr_options = RapidOcrOptions()
            except Exception as e:
                logger.warning("Could not configure RapidOcrOptions: %s", e)

        pipeline_options.generate_picture_images = DOCLING_VISUAL_ENRICHMENT_ENABLED or True
        pipeline_options.generate_page_images = False
        pipeline_options.use_reading_order_separators = True
        pipeline_options.do_code_enrichment = True
        pipeline_options.do_formula_enrichment = True

    return PdfFormatOption(pipeline_options=pipeline_options)


@dataclass(frozen=True, slots=True)
class _ItemFacts:
    """Structural facts captured per document item during a single index pass."""

    label: str
    page_no: int | None
    section_path: tuple[SectionHeading, ...]
    bbox: tuple[float, float, float, float] | None = None
    is_table: bool = False
    is_header_or_footer: bool = False


class DoclingDocumentProcessor:
    """Parse and structurally chunk documents with Docling's HybridChunker."""

    def __init__(
        self,
        converter: DocumentConverter | None = None,
        chunker: HybridChunker | None = None,
        tokenizer_name: str | None = None,
        max_tokens: int | None = None,
        visual_enricher: VisualEnricher | None = None,
    ):
        self._converter = converter
        self._chunker = chunker
        # The chunker tokenizes with the same model the vector store embeds
        # with, so chunk boundaries line up with the embedding window.
        self._tokenizer_name = tokenizer_name or EMBEDDING_MODEL
        self._max_tokens = int(max_tokens or DOCLING_MAX_TOKENS)
        self._visual_enricher = visual_enricher

    @property
    def converter(self) -> DocumentConverter:
        """Lazily built converter; loading layout models is deferred."""
        if self._converter is None:
            format_options = {}
            if DOCLING_LAYOUT_AWARE:
                try:
                    format_options[InputFormat.PDF] = _build_pdf_format_option()
                except Exception as error:
                    logger.warning("Could not initialize layout-aware PdfFormatOption: %s", error)

            self._converter = DocumentConverter(
                allowed_formats=sorted({fmt.value for fmt in _EXTENSION_TO_FORMAT.values()}),
                format_options=format_options if format_options else None,
            )
        return self._converter


    @property
    def chunker(self) -> HybridChunker:
        """Lazily built hybrid chunker bound to the project's embedding model."""
        if self._chunker is None:
            try:
                tokenizer = HuggingFaceTokenizer.from_pretrained(
                    model_name=self._tokenizer_name, max_tokens=self._max_tokens
                )
            except Exception as error:
                raise ValueError(
                    f"Unable to initialise the Docling chunker tokenizer "
                    f"{self._tokenizer_name!r}: {error}"
                ) from error
            self._chunker = HybridChunker(tokenizer=tokenizer, max_tokens=self._max_tokens)
        return self._chunker

    def supported_extensions(self) -> Sequence[str]:
        """Extensions this adapter can convert, derived from Docling's registry."""
        return sorted(f".{extension}" for extension in _EXTENSION_TO_FORMAT)

    def supports(self, file_name: str) -> bool:
        """Whether Docling recognises the given file's extension."""
        return self._format_of(file_name) is not None

    def process(self, content: bytes, file_name: str) -> ProcessedDocument:
        """Convert bytes into a neutral, structurally chunked document.

        Raises ``ValueError`` — the convention the ingestion layer already maps
        to a rejected upload — for unsupported types and conversion failures.
        """
        file_format = self._format_of(file_name)
        if file_format is None:
            supported = ", ".join(self.supported_extensions())
            suffix = Path(file_name).suffix.lower()
            raise ValueError(
                f"Unsupported document type: {suffix or '(none)'} (supported: {supported})"
            )

        document, page_count = self._convert(content, file_name)
        outline, facts = self._index_items(document)
        chunks = self._collect_chunks(document, facts)
        if DOCLING_VISUAL_ENRICHMENT_ENABLED:
            enricher = self._visual_enricher or VisualEnricher()
            visual_chunks = enricher.enrich(document, facts, starting_index=len(chunks))
            chunks = (*chunks, *visual_chunks)
        if DOCLING_CITATION_PDF_ENABLED and Path(file_name).suffix.lower() == ".docx":
            chunks, _citation_pdf = map_docx_pages(
                content,
                file_name,
                tuple(chunks),
                self.converter,
                DOCLING_CITATION_PDF_DIR,
            )

        logger.info(
            "docling processed %r: %d chunks, %d outline entries, pages=%s",
            file_name,
            len(chunks),
            len(outline),
            page_count,
        )
        return ProcessedDocument(
            chunks=tuple(chunks),
            file_type=Path(file_name).suffix.lower().lstrip(".") or None,
            page_count=page_count,
            outline=tuple(outline),
        )

    def _format_of(self, file_name: str) -> InputFormat | None:
        return _EXTENSION_TO_FORMAT.get(Path(file_name).suffix.lower().lstrip("."))

    def _convert(self, content: bytes, file_name: str) -> tuple[Any, int | None]:
        """Run the converter and return the document plus its page count.

        If the primary (layout-aware) converter raises a torchvision /
        ``AutoImageProcessor`` error, the method automatically retries with a
        plain ``DocumentConverter`` that has no layout-model dependencies.  This
        makes ingestion robust in environments where the correct Python
        interpreter is not the one executing the request (e.g. uvicorn
        ``--reload`` multiprocessing workers on Windows).
        """
        _TORCHVISION_HINT = "torchvision"
        _AUTOIMAGE_HINT = "AutoImageProcessor"

        stream = DocumentStream(name=Path(file_name).name, stream=BytesIO(content))
        try:
            result = self.converter.convert(stream)
        except Exception as error:
            err_str = str(error)
            # Graceful fallback: if the layout model cannot load because
            # torchvision is absent in *this* subprocess, retry without layout
            # options rather than failing the whole ingestion request.
            if _TORCHVISION_HINT in err_str or _AUTOIMAGE_HINT in err_str:
                logger.warning(
                    "Layout-aware parsing failed for %r due to missing torchvision "
                    "(%s).  Retrying with standard (non-layout-aware) converter.",
                    file_name,
                    error,
                )
                try:
                    fallback_converter = DocumentConverter(
                        allowed_formats=sorted(
                            {fmt.value for fmt in _EXTENSION_TO_FORMAT.values()}
                        )
                    )
                    stream = DocumentStream(
                        name=Path(file_name).name, stream=BytesIO(content)
                    )
                    result = fallback_converter.convert(stream)
                except Exception as fallback_error:
                    raise ValueError(
                        f"Unable to parse document {file_name!r}: {fallback_error}"
                    ) from fallback_error
            else:
                raise ValueError(f"Unable to parse document {file_name!r}: {error}") from error

        document = getattr(result, "document", None)
        if document is None:
            raise ValueError(f"Unable to parse document {file_name!r}: conversion produced no document")

        pages = getattr(result, "pages", None)
        page_count = len(pages) if pages else None
        return document, page_count

    def _index_items(self, document: Any) -> tuple[list[SectionHeading], dict[str, _ItemFacts]]:
        """Walk the document once, recording outline and per-item structural facts.

        ``iterate_items`` yields items in reading order with their nesting
        depth, so a stack of the currently open headings yields each item's
        ancestor path without assuming anything about the document's headings.
        """
        outline: list[SectionHeading] = []
        facts: dict[str, _ItemFacts] = {}
        stack: list[SectionHeading] = []

        try:
            items = document.iterate_items()
        except Exception as error:
            logger.warning("docling structure unavailable for this document: %s", error)
            return outline, facts

        for item, level in items:
            label = _label_of(item)
            is_heading = label == _HEADING_LABEL
            if is_heading:
                while stack and stack[-1].level >= level:
                    stack.pop()
            # Captured after the pop so a heading's own path excludes itself.
            section_path = tuple(stack)
            if is_heading:
                title = (getattr(item, "text", "") or "").strip()
                if title:
                    heading = SectionHeading(level=level, title=title)
                    stack.append(heading)
                    outline.append(heading)
            reference = getattr(item, "self_ref", None)
            if reference:
                facts[reference] = _ItemFacts(
                    label=label,
                    page_no=_page_of(item),
                    section_path=section_path,
                    bbox=_bbox_of(item),
                    is_table=(label == "table"),
                    is_header_or_footer=(label in ("page_header", "page_footer")),
                )
        return outline, facts

    def _collect_chunks(
        self, document: Any, facts: dict[str, _ItemFacts]
    ) -> tuple[ProcessedChunk, ...]:
        """Translate HybridChunker output into neutral chunks."""
        try:
            raw_chunks = self.chunker.chunk(document)
        except Exception as error:
            raise ValueError(f"Unable to chunk document: {error}") from error

        chunks: list[ProcessedChunk] = []
        for raw_chunk in raw_chunks:
            text = (getattr(raw_chunk, "text", "") or "").strip()
            if not text:
                continue
            section_path, page_number, label, layout_meta = self._facts_of(
                self._items_of(raw_chunk), facts
            )
            # Layout-aware artifact filter: skip pure header/footer chunks if enabled
            if DOCLING_FILTER_HEADERS_FOOTERS and layout_meta.get("is_header_or_footer"):
                logger.debug("Filtered out recurring layout artifact chunk: %r", text[:60])
                continue

            known_type = {"content_type": label} if label else {}
            chunks.append(
                ProcessedChunk(
                    text=text,
                    index=len(chunks),
                    page_number=page_number,
                    section_path=section_path,
                    metadata=layout_meta,
                    **known_type,
                )
            )
        return tuple(chunks)

    @staticmethod
    def _items_of(raw_chunk: Any) -> list[Any]:
        meta = getattr(raw_chunk, "meta", None)
        return list(getattr(meta, "doc_items", None) or [])

    @staticmethod
    def _facts_of(
        items: list[Any], facts: dict[str, _ItemFacts]
    ) -> tuple[tuple[SectionHeading, ...], int | None, str, dict[str, MetadataValue]]:
        """Reduce a chunk's source items to one path, one page, one kind, and layout metadata."""
        pages: list[int] = []
        section_path: tuple[SectionHeading, ...] = ()
        label = ""
        is_table = False
        bboxes: list[tuple[float, float, float, float]] = []
        item_count = 0
        header_footer_count = 0

        for item in items:
            item_facts = facts.get(getattr(item, "self_ref", None))
            if item_facts is None:
                continue
            item_count += 1
            if getattr(item_facts, "is_header_or_footer", False):
                header_footer_count += 1
            if not label:
                label = item_facts.label
            if getattr(item_facts, "is_table", False):
                is_table = True
            if not section_path:
                section_path = item_facts.section_path
            if item_facts.page_no is not None:
                pages.append(item_facts.page_no)
            if getattr(item_facts, "bbox", None) is not None:
                bboxes.append(item_facts.bbox)

        bbox_str: str | None = None
        if bboxes:
            l = min(b[0] for b in bboxes)
            t = min(b[1] for b in bboxes)
            r = max(b[2] for b in bboxes)
            b_bottom = max(b[3] for b in bboxes)
            bbox_str = f"{l:.1f},{t:.1f},{r:.1f},{b_bottom:.1f}"

        layout_meta: dict[str, MetadataValue] = {}
        if label:
            layout_meta["layout_type"] = label
        if is_table:
            layout_meta["is_table"] = True
        if bbox_str is not None:
            layout_meta["bbox"] = bbox_str

        is_pure_header_footer = (item_count > 0 and header_footer_count == item_count)
        if is_pure_header_footer:
            layout_meta["is_header_or_footer"] = True

        return section_path, min(pages) if pages else None, label, layout_meta
