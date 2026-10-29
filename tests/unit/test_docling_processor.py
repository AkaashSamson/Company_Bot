"""Unit tests for :class:`DoclingDocumentProcessor`.

The converter and chunker are injected as stand-ins, so these tests exercise
the adapter's structural mapping — heading stacks, page provenance, content
kinds, and error translation — without loading Docling layout models or a
tokenizer. The Docling-specific pieces are never asserted on directly; the
tests are written against the neutral port contract.
"""
# pyrefly: ignore[missing-import]
import pytest

from app.core.settings import DOCLING_MAX_TOKENS, EMBEDDING_MODEL
from app.domain.ports.document_processing import (
    DocumentProcessingPort,
    ProcessedChunk,
    ProcessedDocument,
)
from app.infrastructure.document.docling_processor import DoclingDocumentProcessor


class FakeBBox:
    def __init__(self, l, t, r, b):
        self.l = l
        self.t = t
        self.r = r
        self.b = b


class FakeProvenance:
    def __init__(self, page_no, bbox=None):
        self.page_no = page_no
        self.bbox = bbox


class FakeItem:
    """Stands in for a Docling document item."""

    def __init__(self, self_ref, label, text="", page_no=None, bbox=None):
        self.self_ref = self_ref
        self.label = label
        self.text = text
        self.prov = [FakeProvenance(page_no, bbox)] if page_no is not None or bbox is not None else []


class FakeDocument:
    def __init__(self, items):
        self._items = items

    def iterate_items(self):
        return iter(self._items)


class FakeMeta:
    def __init__(self, doc_items=()):
        self.doc_items = list(doc_items)
        self.headings = None


class FakeChunk:
    """Stands in for a Docling chunk."""

    def __init__(self, text, doc_items=()):
        self.text = text
        self.meta = FakeMeta(doc_items)


class FakeResult:
    def __init__(self, document, pages=()):
        self.document = document
        self.pages = list(pages)


class FakeConverter:
    def __init__(self, document=None, pages=(), error=None):
        self._document = document
        self._pages = pages
        self._error = error
        self.calls = []

    def convert(self, stream):
        self.calls.append(stream)
        if self._error is not None:
            raise self._error
        return FakeResult(self._document, self._pages)


class FakeChunker:
    def __init__(self, chunks=(), error=None):
        self._chunks = chunks
        self._error = error
        self.documents = []

    def chunk(self, document):
        self.documents.append(document)
        if self._error is not None:
            raise self._error
        return iter(self._chunks)


def _processor(items, chunks, pages=(), converter_error=None, chunker_error=None):
    document = FakeDocument(items)
    return DoclingDocumentProcessor(
        converter=FakeConverter(document, pages=pages, error=converter_error),
        chunker=FakeChunker(chunks, error=chunker_error),
    )


def test_processor_satisfies_the_port():
    """The adapter is reachable only through the port contract."""
    assert isinstance(DoclingDocumentProcessor(), DocumentProcessingPort)


def test_simple_text_document_invents_no_structure():
    """A document with no headings and no pagination yields neutral defaults."""
    body = FakeItem("#/texts/0", "text", "Employees get ten days of annual leave.")
    processor = _processor([(body, 1)], [FakeChunk(body.text, [body])])

    result = processor.process(b"payload", "notes.txt")

    assert isinstance(result, ProcessedDocument)
    assert len(result.chunks) == 1
    chunk = result.chunks[0]
    assert chunk.text == "Employees get ten days of annual leave."
    assert chunk.index == 0
    assert chunk.page_number is None
    assert chunk.section_path == ()
    assert chunk.section is None
    assert chunk.content_type == "text"
    assert result.outline == ()
    assert result.page_count is None
    assert result.file_type == "txt"


def test_hierarchical_document_preserves_nested_section_path():
    """Nested headings flatten to an ancestor path on each chunk."""
    part = FakeItem("#/texts/0", "section_header", "Part One")
    topic = FakeItem("#/texts/1", "section_header", "Topic Two", page_no=2)
    body = FakeItem("#/texts/2", "text", "Body under the nested topic.", page_no=2)
    processor = _processor(
        [(part, 2), (topic, 3), (body, 3)],
        [FakeChunk(body.text, [body])],
        pages=[object(), object()],
    )

    result = processor.process(b"payload", "report.pdf")

    chunk = result.chunks[0]
    assert chunk.section == "Part One > Topic Two"
    assert [heading.level for heading in chunk.section_path] == [2, 3]
    assert result.outline == chunk.section_path + ()  # ordered, same content
    assert result.page_count == 2


def test_sibling_headings_at_the_same_level_do_not_accumulate():
    """A new sibling heading replaces the previous one instead of nesting under it."""
    first = FakeItem("#/texts/0", "section_header", "First Section")
    second = FakeItem("#/texts/1", "section_header", "Second Section")
    under_first = FakeItem("#/texts/2", "text", "Text under the first section.")
    under_second = FakeItem("#/texts/3", "text", "Text under the second section.")
    processor = _processor(
        [(first, 1), (under_first, 2), (second, 1), (under_second, 2)],
        [FakeChunk(under_first.text, [under_first]), FakeChunk(under_second.text, [under_second])],
    )

    result = processor.process(b"payload", "manual.docx")

    assert [chunk.section for chunk in result.chunks] == ["First Section", "Second Section"]


def test_heading_own_path_excludes_itself():
    """A heading chunk is not nested under its own title."""
    parent = FakeItem("#/texts/0", "section_header", "Outer Section")
    child = FakeItem("#/texts/1", "section_header", "Inner Section")
    processor = _processor([(parent, 1), (child, 2)], [FakeChunk(child.text, [child])])

    result = processor.process(b"payload", "manual.docx")

    assert result.chunks[0].section == "Outer Section"


def test_document_with_missing_headings_reports_empty_hierarchy():
    """No structural information yields an empty path rather than a fabricated one."""
    body = FakeItem("#/texts/0", "text", "A paragraph with no heading above it.")
    processor = _processor([(body, 1)], [FakeChunk(body.text, [body])])

    result = processor.process(b"payload", "plain.md")

    assert result.outline == ()
    assert result.chunks[0].section_path == ()
    assert result.chunks[0].section is None


def test_missing_page_provenance_yields_none():
    """Formats without pagination must not be given a guessed page number."""
    heading = FakeItem("#/texts/0", "section_header", "Section Title")
    body = FakeItem("#/texts/1", "text", "Body text without provenance.")
    assert body.prov == []
    processor = _processor([(heading, 1), (body, 1)], [FakeChunk(body.text, [body])])

    result = processor.process(b"payload", "notes.docx")

    assert result.page_count is None
    assert all(chunk.page_number is None for chunk in result.chunks)


def test_chunk_page_is_the_lowest_page_of_its_source_items():
    """A chunk spanning several items is attributed to the page it starts on."""
    first = FakeItem("#/texts/0", "text", "Content on page three.", page_no=3)
    second = FakeItem("#/texts/1", "text", "Content continuing on page four.", page_no=4)
    processor = _processor(
        [(first, 1), (second, 1)], [FakeChunk("Combined text.", [first, second])], pages=[1, 2, 3, 4]
    )

    result = processor.process(b"payload", "long.pdf")

    assert result.chunks[0].page_number == 3


def test_non_numeric_page_provenance_is_ignored():
    """Malformed provenance is skipped rather than persisted."""
    body = FakeItem("#/texts/0", "text", "Body text.")
    body.prov = [FakeProvenance(None), FakeProvenance(True)]
    processor = _processor([(body, 1)], [FakeChunk(body.text, [body])])

    result = processor.process(b"payload", "notes.docx")

    assert result.chunks[0].page_number is None


def test_content_type_is_preserved_from_the_source_element():
    """Tables and other element kinds survive the translation."""
    table = FakeItem("#/tables/0", "table", "| a | b |")
    body = FakeItem("#/texts/0", "text", "A paragraph.")
    processor = _processor(
        [(table, 1), (body, 1)], [FakeChunk(table.text, [table]), FakeChunk(body.text, [body])]
    )

    result = processor.process(b"payload", "report.docx")

    assert [chunk.content_type for chunk in result.chunks] == ["table", "text"]


def test_chunk_without_source_items_keeps_neutral_defaults():
    """A chunk Docling cannot attribute stays empty rather than guessed."""
    processor = _processor([(FakeItem("#/texts/0", "text", "Body."), 1)], [FakeChunk("Unattributed text.")])

    result = processor.process(b"payload", "notes.txt")

    chunk = result.chunks[0]
    assert chunk.page_number is None
    assert chunk.section_path == ()
    assert chunk.content_type == "text"


def test_blank_chunks_are_dropped_and_indexes_stay_contiguous():
    """Empty chunks are not persisted and the sequence is not left gapped."""
    body = FakeItem("#/texts/0", "text", "Real content.")
    processor = _processor(
        [(body, 1)],
        [FakeChunk("   ", [body]), FakeChunk(body.text, [body]), FakeChunk("", [body])],
    )

    result = processor.process(b"payload", "notes.txt")

    assert len(result.chunks) == 1
    assert result.chunks[0].index == 0
    assert result.chunks[0].text == "Real content."


def test_multiple_documents_are_processed_independently():
    """Two documents yield separate, independently indexed neutral results."""
    first_body = FakeItem("#/texts/0", "section_header", "Policy Alpha")
    first_text = FakeItem("#/texts/1", "text", "Alpha body.", page_no=1)
    second_body = FakeItem("#/texts/0", "section_header", "Policy Beta")
    second_text = FakeItem("#/texts/1", "text", "Beta body.", page_no=9)
    first = _processor(
        [(first_body, 1), (first_text, 1)], [FakeChunk(first_text.text, [first_text])], pages=[1]
    )
    second = _processor(
        [(second_body, 1), (second_text, 1)], [FakeChunk(second_text.text, [second_text])], pages=[1] * 9
    )

    first_result = first.process(b"one", "alpha.pdf")
    second_result = second.process(b"two", "beta.pdf")

    assert [chunk.section for chunk in first_result.chunks] == ["Policy Alpha"]
    assert [chunk.section for chunk in second_result.chunks] == ["Policy Beta"]
    assert [chunk.index for chunk in first_result.chunks] == [0]
    assert [chunk.index for chunk in second_result.chunks] == [0]
    assert first_result.chunks[0].page_number == 1
    assert second_result.chunks[0].page_number == 9
    assert first_result.file_type == "pdf"
    assert second_result.file_type == "pdf"


def test_unsupported_extension_raises_the_existing_value_error():
    """Unsupported input keeps the ingestion layer's established error contract."""
    processor = _processor([], [])

    with pytest.raises(ValueError, match="Unsupported document type"):
        processor.process(b"payload", "policy.rst")

    with pytest.raises(ValueError, match=r"supported: .*\.docx"):
        processor.process(b"payload", "policy.rst")


def test_missing_extension_is_reported_as_none():
    processor = _processor([], [])

    with pytest.raises(ValueError, match=r"\(none\)"):
        processor.process(b"payload", "policy")


def test_converter_failure_is_reported_as_value_error():
    """Parser failures surface with the repository's error convention."""
    processor = _processor([], [], converter_error=RuntimeError("layout model exploded"))

    with pytest.raises(ValueError, match="Unable to parse document"):
        processor.process(b"payload", "broken.pdf")


def test_conversion_without_a_document_is_reported_as_value_error():
    processor = DoclingDocumentProcessor(converter=FakeConverter(None), chunker=FakeChunker([]))

    with pytest.raises(ValueError, match="no document"):
        processor.process(b"payload", "broken.pdf")


def test_chunker_failure_is_reported_as_value_error():
    processor = _processor(
        [(FakeItem("#/texts/0", "text", "Body."), 1)], [], chunker_error=RuntimeError("tokenizer failed")
    )

    with pytest.raises(ValueError, match="Unable to chunk document"):
        processor.process(b"payload", "broken.pdf")


def test_raw_bytes_are_passed_to_the_converter():
    """The adapter hands the converter the untouched file bytes."""
    document = FakeDocument([])
    converter = FakeConverter(document)
    DoclingDocumentProcessor(converter=converter, chunker=FakeChunker([])).process(
        b"raw file bytes", "notes.txt"
    )

    assert converter.calls[0].stream.read() == b"raw file bytes"


def test_supported_extensions_are_derived_from_the_docling_registry():
    """Capability comes from Docling's own registry, not a hand-kept list."""
    extensions = DoclingDocumentProcessor().supported_extensions()

    for expected in (".docx", ".pdf", ".txt", ".md", ".html", ".csv"):
        assert expected in extensions
    # Legacy Office needs LibreOffice and reStructuredText has no Docling backend.
    assert ".doc" not in extensions
    assert ".rst" not in extensions


def test_supports_matches_supported_extensions():
    processor = DoclingDocumentProcessor()

    assert processor.supports("handbook.docx") is True
    assert processor.supports("HANDBOOK.PDF") is True
    assert processor.supports("notes.txt") is True
    assert processor.supports("policy.rst") is False
    assert processor.supports("archive") is False


def test_chunker_is_configured_from_the_projects_embedding_strategy():
    """Chunk size is tied to the embedding model so chunks are never truncated.

    Asserted on the injected configuration rather than by building a tokenizer,
    which would download model weights.
    """
    processor = DoclingDocumentProcessor()

    assert processor._tokenizer_name == EMBEDDING_MODEL
    assert processor._max_tokens == DOCLING_MAX_TOKENS


def test_chunker_tokenizer_failure_is_reported_as_value_error():
    """A tokenizer that cannot be loaded surfaces as the established error type."""
    processor = DoclingDocumentProcessor(tokenizer_name="definitely-not-a-real-tokenizer")

    with pytest.raises(ValueError, match="Unable to initialise the Docling chunker tokenizer"):
        _ = processor.chunker


def test_result_contains_only_neutral_types():
    """No Docling object may cross the adapter boundary."""
    heading = FakeItem("#/texts/0", "section_header", "Section Title")
    body = FakeItem("#/texts/1", "text", "Body text.", page_no=1)
    processor = _processor([(heading, 1), (body, 1)], [FakeChunk(body.text, [body])], pages=[1])

    result = processor.process(b"payload", "manual.pdf")

    assert isinstance(result, ProcessedDocument)
    assert all(isinstance(chunk, ProcessedChunk) for chunk in result.chunks)
    assert type(result).__module__ == "app.domain.ports.document_processing"
    assert {type(chunk).__module__ for chunk in result.chunks} == {
        "app.domain.ports.document_processing"
    }


def test_layout_aware_table_detection_and_metadata():
    """Table layout kind and metadata are captured on processed chunk."""
    table = FakeItem("#/tables/0", "table", "| Col A | Col B |\n|---|---|\n| 1 | 2 |", page_no=1)
    processor = _processor([(table, 1)], [FakeChunk(table.text, [table])], pages=[1])

    result = processor.process(b"payload", "sheet.pdf")

    assert len(result.chunks) == 1
    chunk = result.chunks[0]
    assert chunk.content_type == "table"
    assert chunk.metadata.get("layout_type") == "table"
    assert chunk.metadata.get("is_table") is True


def test_layout_aware_bbox_extraction():
    """Spatial bounding box coordinates are extracted and aggregated."""
    bbox = FakeBBox(l=15.5, t=20.0, r=400.0, b=120.5)
    item = FakeItem("#/texts/0", "text", "Bounded text.", page_no=2, bbox=bbox)
    processor = _processor([(item, 1)], [FakeChunk(item.text, [item])], pages=[1, 2])

    result = processor.process(b"payload", "form.pdf")

    assert len(result.chunks) == 1
    chunk = result.chunks[0]
    assert chunk.metadata.get("bbox") == "15.5,20.0,400.0,120.5"


def test_layout_aware_header_footer_filtering(monkeypatch):
    """Standalone page headers and footers are suppressed when configured."""
    monkeypatch.setattr("app.infrastructure.document.docling_processor.DOCLING_FILTER_HEADERS_FOOTERS", True)
    header = FakeItem("#/headers/0", "page_header", "Confidential Page 1", page_no=1)
    body = FakeItem("#/texts/0", "text", "Important policy content.", page_no=1)
    footer = FakeItem("#/footers/0", "page_footer", "Page 1 of 10", page_no=1)
    processor = _processor(
        [(header, 1), (body, 1), (footer, 1)],
        [FakeChunk(header.text, [header]), FakeChunk(body.text, [body]), FakeChunk(footer.text, [footer])],
        pages=[1],
    )

    result = processor.process(b"payload", "doc.pdf")

    # Header and footer chunks filtered out, only body chunk survives
    assert len(result.chunks) == 1
    assert result.chunks[0].text == "Important policy content."


def test_build_pdf_format_option_configures_layout_aware_pipeline():
    """PdfFormatOption is configured with TableFormer, OCR, and reading order."""
    from app.infrastructure.document.docling_processor import _build_pdf_format_option
    from docling.document_converter import PdfFormatOption
    from docling.datamodel.pipeline_options import TableFormerMode

    option = _build_pdf_format_option()
    assert isinstance(option, PdfFormatOption)
    assert option.pipeline_options.do_table_structure is True
    assert option.pipeline_options.table_structure_options.mode == TableFormerMode.ACCURATE
    assert option.pipeline_options.use_reading_order_separators is True

