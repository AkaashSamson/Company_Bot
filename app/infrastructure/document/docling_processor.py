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
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc import DocItemLabel

from app.core.settings import (
    DOCLING_AUTO_OCR_SELECTIVE,
    DOCLING_CITATION_PDF_DIR,
    DOCLING_CITATION_PDF_ENABLED,
    DOCLING_MAX_TOKENS,
    DOCLING_NUM_THREADS,
    DOCLING_PDF_OCR_SCALE,
    DOCLING_SKIP_BLANK_PAGES,
    DOCLING_VISUAL_ENRICHMENT_ENABLED,
    EMBEDDING_MODEL,
)
from app.domain.ports.document_processing import (
    DocumentProcessingPort,
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


def _has_digital_text(content: bytes) -> bool:
    """Quickly check if a PDF has native digital text stream using pypdfium2."""
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(content)
        sample_count = min(3, len(doc))
        for i in range(sample_count):
            text = doc[i].get_textpage().get_text_range().strip()
            if len(text) > 40:
                return True
        return False
    except Exception:
        return False


_cached_converters: dict[bool, DocumentConverter] = {}


def get_docling_converter(is_digital_pdf: bool = False) -> DocumentConverter:
    """Get or construct a shared, pre-warmed DocumentConverter with multi-core acceleration."""
    key = is_digital_pdf and DOCLING_AUTO_OCR_SELECTIVE
    if key not in _cached_converters:
        import torch
        from docling.datamodel.pipeline_options import (
            AcceleratorDevice,
            AcceleratorOptions,
            OcrAutoOptions,
            OcrMode,
            PdfPipelineOptions,
            TableFormerMode,
            TableStructureOptions,
        )
        from docling.document_converter import PdfFormatOption

        device = AcceleratorDevice.CUDA if torch.cuda.is_available() else AcceleratorDevice.AUTO
        pdf_options = PdfPipelineOptions()
        pdf_options.accelerator_options = AcceleratorOptions(
            num_threads=DOCLING_NUM_THREADS,
            device=device,
        )
        pdf_options.table_structure_options = TableStructureOptions(
            mode=TableFormerMode.FAST,
            do_cell_matching=True,
        )
        if key:
            # Fast digital mode: Native text already present in PDF stream; skip heavy RapidOCR pixel pass.
            pdf_options.do_ocr = False
            logger.info("Configured Docling with do_ocr=False (Digital Fast Mode, %d threads)", DOCLING_NUM_THREADS)
        else:
            # Scanned / Image PDF: Run RapidOCR with layout awareness
            pdf_options.do_ocr = True
            pdf_options.ocr_options = OcrAutoOptions(
                mode=OcrMode.PDF_AWARE_LAYOUT_REGIONS,
                scale=DOCLING_PDF_OCR_SCALE,
            )
            logger.info("Configured Docling with full RapidOCR (Scanned Document Mode, %d threads)", DOCLING_NUM_THREADS)

        if DOCLING_VISUAL_ENRICHMENT_ENABLED:
            pdf_options.generate_picture_images = True

        format_options = {
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options),
        }

        _cached_converters[key] = DocumentConverter(
            allowed_formats=sorted({fmt.value for fmt in _EXTENSION_TO_FORMAT.values()}),
            format_options=format_options,
        )
    return _cached_converters[key]


@dataclass(frozen=True, slots=True)
class _ItemFacts:
    """Structural facts captured per document item during a single index pass."""

    label: str
    page_no: int | None
    section_path: tuple[SectionHeading, ...]


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
            return get_docling_converter(is_digital_pdf=False)
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
        """Run the converter and return the document plus its page count."""
        stream = DocumentStream(name=Path(file_name).name, stream=BytesIO(content))
        converter = self._converter
        if converter is None:
            is_digital = Path(file_name).suffix.lower() == ".pdf" and _has_digital_text(content)
            converter = get_docling_converter(is_digital_pdf=is_digital)

        try:
            result = converter.convert(stream)
        except Exception as error:
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
            if DOCLING_SKIP_BLANK_PAGES and len(text) < 3 and not text.isalnum():
                continue
            section_path, page_number, label = self._facts_of(self._items_of(raw_chunk), facts)
            # An unattributable chunk keeps the port's own default content type
            # rather than an empty string, which would otherwise reach Chroma.
            known_type = {"content_type": label} if label else {}
            chunks.append(
                ProcessedChunk(
                    text=text,
                    index=len(chunks),
                    page_number=page_number,
                    section_path=section_path,
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
    ) -> tuple[tuple[SectionHeading, ...], int | None, str]:
        """Reduce a chunk's source items to one path, one page, and one kind."""
        pages: list[int] = []
        section_path: tuple[SectionHeading, ...] = ()
        label = ""

        for item in items:
            item_facts = facts.get(getattr(item, "self_ref", None))
            if item_facts is None:
                continue
            if not label:
                label = item_facts.label
            if not section_path:
                section_path = item_facts.section_path
            if item_facts.page_no is not None:
                pages.append(item_facts.page_no)

        return section_path, min(pages) if pages else None, label
