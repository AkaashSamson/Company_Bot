"""Tests for the fixed-width text adapter and the processor composition root.

The composition root is what keeps a supported file type working when the
structural parser cannot handle it, so the routing tests matter more than the
parsing tests here.
"""

import pytest

from app.domain.ports.document_processing import (
    DocumentProcessingPort,
    ProcessedDocument,
)
from app.infrastructure.document.plaintext_processor import PlainTextDocumentProcessor
from app.infrastructure.document.local_document_loader import LocalDocumentLoader
from app.infrastructure.document.processor_factory import (
    CompositeDocumentProcessor,
    build_document_processor,
)
from app.use_cases.ingestion.document_processing import SUPPORTED_EXTENSIONS


class _StubProcessor:
    """A port implementation that records what it was asked to handle."""

    def __init__(self, extensions, chunks=("Body",)):
        self._extensions = tuple(extensions)
        self._chunks = tuple(chunks)
        self.seen = []

    def supported_extensions(self):
        return self._extensions

    def supports(self, file_name):
        return file_name.lower().endswith(self._extensions)

    def process(self, content, file_name):
        self.seen.append(file_name)
        from app.domain.ports.document_processing import ProcessedChunk

        return ProcessedDocument(
            chunks=tuple(
                ProcessedChunk(text=text, index=index) for index, text in enumerate(self._chunks)
            )
        )


# --- the text adapter satisfies the port -------------------------------------


def test_plaintext_processor_satisfies_the_port():
    assert isinstance(PlainTextDocumentProcessor(), DocumentProcessingPort)


def test_plaintext_processor_supports_every_legacy_extension():
    processor = PlainTextDocumentProcessor()

    assert set(processor.supported_extensions()) == SUPPORTED_EXTENSIONS


@pytest.mark.parametrize("extension", sorted(SUPPORTED_EXTENSIONS))
def test_plaintext_processor_accepts_each_supported_extension(extension):
    assert PlainTextDocumentProcessor().supports(f"document{extension}")


@pytest.mark.parametrize("extension", [".pdf", ".png", ".exe", ""])
def test_plaintext_processor_rejects_other_extensions(extension):
    assert not PlainTextDocumentProcessor().supports(f"document{extension}")


# --- the text adapter reports no structure it cannot know --------------------


def test_plaintext_processor_produces_text_chunks_without_invented_structure():
    processed = PlainTextDocumentProcessor().process(
        b"Employees get ten days of annual leave. Contact the HR team to book them.",
        "leave.txt",
    )

    assert processed.chunks
    assert all(chunk.page_number is None for chunk in processed.chunks)
    assert all(chunk.section_path == () for chunk in processed.chunks)
    assert all(chunk.content_type == "text" for chunk in processed.chunks)
    assert [chunk.index for chunk in processed.chunks] == list(range(len(processed.chunks)))


def test_plaintext_processor_reports_the_file_type():
    processed = PlainTextDocumentProcessor().process(b"Body", "notes.md")

    assert processed.file_type == "md"


def test_plaintext_processor_splits_a_long_document_into_several_chunks():
    text = "\n\n".join(f"Paragraph number {n} with enough words to stand alone." for n in range(12))

    processed = PlainTextDocumentProcessor().process(text.encode("utf-8"), "long.txt")

    assert len(processed.chunks) > 1


def test_plaintext_processor_rejects_an_unsupported_extension():
    with pytest.raises(ValueError, match="Unsupported document type"):
        PlainTextDocumentProcessor().process(b"body", "photo.png")


def test_plaintext_processor_raises_for_a_corrupt_docx():
    with pytest.raises(Exception):
        PlainTextDocumentProcessor().process(b"not really a docx", "broken.docx")


# --- composition keeps formats the structural parser cannot handle -----------


def test_composite_routes_to_the_first_processor_that_claims_a_format():
    primary, fallback = _StubProcessor((".pdf",)), _StubProcessor((".rst",))
    composite = CompositeDocumentProcessor(primary, fallback)

    composite.process(b"a", "a.pdf")
    composite.process(b"b", "b.rst")

    assert primary.seen == ["a.pdf"]
    assert fallback.seen == ["b.rst"]


def test_composite_unions_supported_extensions():
    composite = CompositeDocumentProcessor(_StubProcessor((".pdf",)), _StubProcessor((".rst",)))

    assert set(composite.supported_extensions()) == {".pdf", ".rst"}


def test_composite_supports_a_format_either_processor_claims():
    composite = CompositeDocumentProcessor(_StubProcessor((".pdf",)), _StubProcessor((".rst",)))

    assert composite.supports("a.pdf")
    assert composite.supports("a.rst")
    assert not composite.supports("a.png")


def test_composite_rejects_a_format_no_processor_claims():
    composite = CompositeDocumentProcessor(_StubProcessor((".pdf",)), _StubProcessor((".rst",)))

    with pytest.raises(ValueError, match="Unsupported document type"):
        composite.process(b"a", "a.png")


def test_composite_falls_back_for_a_format_the_structural_parser_lacks():
    """``DOCLING_ENABLED`` must never cost a supported file type.

    ``.rst`` is the concrete case: the application has always accepted it and
    the structural parser has no backend for it.
    """
    structural = _StubProcessor((".docx", ".txt", ".md", ".pdf"))
    composite = CompositeDocumentProcessor(structural, PlainTextDocumentProcessor())

    assert composite.supports("handbook.rst")
    assert composite.supports("handbook.docx")

    composite.process(b"Title\n=====\n\nBody text.", "handbook.rst")

    assert structural.seen == []
    assert composite.process(b"body", "handbook.rst").file_type == "rst"


# --- the factory honours the flag --------------------------------------------


def test_factory_returns_the_text_pipeline_when_structural_parsing_is_off():
    processor = build_document_processor(structural=False)

    assert isinstance(processor, PlainTextDocumentProcessor)


def test_factory_composes_the_structural_parser_when_enabled():
    processor = build_document_processor(structural=True)

    assert isinstance(processor, CompositeDocumentProcessor)
    assert processor.supports("handbook.docx")
    assert processor.supports("handbook.rst")


def test_factory_default_follows_the_configured_flag(monkeypatch):
    monkeypatch.setattr(
        "app.infrastructure.document.processor_factory.DOCLING_ENABLED", False, raising=True
    )
    assert isinstance(build_document_processor(), PlainTextDocumentProcessor)

    monkeypatch.setattr(
        "app.infrastructure.document.processor_factory.DOCLING_ENABLED", True, raising=True
    )
    assert isinstance(build_document_processor(), CompositeDocumentProcessor)


def test_local_loader_uses_the_active_processor_capabilities(tmp_path):
    (tmp_path / "policy.pdf").write_bytes(b"pdf")
    (tmp_path / "notes.rst").write_text("notes", encoding="utf-8")
    processor = _StubProcessor((".pdf",))

    files = LocalDocumentLoader(str(tmp_path), processor=processor).list_documents()

    assert files == [str(tmp_path / "policy.pdf")]
