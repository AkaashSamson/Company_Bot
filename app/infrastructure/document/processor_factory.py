"""Composition root for the document-processing port.

This is the only module that names a concrete parser. It assembles the port
implementation the application ingests with, so that the provisioner, the
batch script, and the API wiring all obtain the same processor without any of
them importing a document-conversion library.

The structural parser is selected by ``DOCLING_ENABLED``. The fixed-width text
pipeline is always composed in behind it, which is what keeps a supported file
type working when the structural parser cannot handle it -- reStructuredText is
the concrete case: the application has always accepted ``.rst`` and the
structural parser has no backend for it.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.core.settings import DOCLING_ENABLED
from app.domain.ports.document_processing import (
    DocumentProcessingPort,
    ProcessedDocument,
)
from app.infrastructure.document.plaintext_processor import PlainTextDocumentProcessor

logger = logging.getLogger("knowlayer.ingestion")


class CompositeDocumentProcessor:
    """Route each document to the first processor that claims its format.

    Implements the port by delegation, so composing processors changes no
    caller. Ordering encodes preference: the first processor that reports
    support for a file name handles it.
    """

    def __init__(self, *processors: DocumentProcessingPort):
        self._processors = processors

    def supported_extensions(self) -> Sequence[str]:
        extensions: set[str] = set()
        for processor in self._processors:
            extensions.update(processor.supported_extensions())
        return tuple(sorted(extensions))

    def supports(self, file_name: str) -> bool:
        return any(processor.supports(file_name) for processor in self._processors)

    def process(self, content: bytes, file_name: str) -> ProcessedDocument:
        for processor in self._processors:
            if processor.supports(file_name):
                return processor.process(content, file_name)

        supported = ", ".join(self.supported_extensions())
        suffix = Path(file_name).suffix.lower()
        raise ValueError(f"Unsupported document type: {suffix or '(none)'} (supported: {supported})")


def build_document_processor(structural: bool | None = None) -> DocumentProcessingPort:
    """Build the document processor the application ingests with.

    ``structural`` overrides ``DOCLING_ENABLED`` and exists for tests and for
    callers that need to pin a pipeline; when omitted the configured flag
    decides. Either way the text and pdf pipelines stay available as fallbacks, so
    enabling the structural parser never removes a supported file type.
    """
    from app.infrastructure.document.pdf_processor import PdfDocumentProcessor

    use_structural = DOCLING_ENABLED if structural is None else structural
    text_processor = PlainTextDocumentProcessor()
    pdf_processor = PdfDocumentProcessor()

    if not use_structural:
        logger.debug("structural parsing disabled; using the text and pdf pipelines")
        return CompositeDocumentProcessor(text_processor, pdf_processor)

    try:
        from app.infrastructure.document.docling_processor import DoclingDocumentProcessor

        logger.debug("structural parsing enabled; composing over the text pipeline fallback")
        return CompositeDocumentProcessor(DoclingDocumentProcessor(), text_processor, pdf_processor)
    except ImportError as exc:
        logger.warning(
            "Docling parser requested but dependency is missing (%s); falling back to plain text and pdf pipeline",
            exc,
        )
        return CompositeDocumentProcessor(text_processor, pdf_processor)


class UploadFileProcessorAdapter:
    """Adapter allowing FastAPI UploadFile or bytes/content to be processed via DocumentProcessingPort."""

    def __init__(self, port: DocumentProcessingPort, filename: Optional[str] = None):
        self.port = port
        self.filename = filename

    async def process(self, file_or_content: Any, filename: Optional[str] = None) -> List[Dict[str, Any]]:
        target_name = filename or self.filename or getattr(file_or_content, "filename", "document.txt")
        if hasattr(file_or_content, "read"):
            read_fn = file_or_content.read
            content = read_fn()
            if asyncio.iscoroutine(content):
                content = await content
            if hasattr(file_or_content, "seek"):
                seek_fn = file_or_content.seek
                res = seek_fn(0)
                if asyncio.iscoroutine(res):
                    await res
        elif isinstance(file_or_content, bytes):
            content = file_or_content
        else:
            content = str(file_or_content).encode("utf-8")

        processed: ProcessedDocument = self.port.process(content, target_name)
        raw_fragments: List[Dict[str, Any]] = []
        for idx, chunk in enumerate(processed.chunks):
            raw_fragments.append(
                {
                    "chunk_id": f"{target_name}_{idx}",
                    "text": chunk.text,
                    "metadata": {
                        **chunk.metadata,
                        "page_number": getattr(chunk, "page_number", None),
                        "section_heading": getattr(chunk, "section_heading", None),
                    },
                }
            )
        return raw_fragments


def get_document_processor(filename: Optional[str] = None) -> UploadFileProcessorAdapter:
    port = build_document_processor()
    return UploadFileProcessorAdapter(port, filename=filename)
