"""Lightweight PDF processor using pypdf.

Provides basic text extraction and chunking for PDF documents when
heavyweight structural parsers (like Docling) are not enabled or installed.
"""
from io import BytesIO
import logging
from pathlib import Path
from typing import Sequence

from app.domain.ports.document_processing import (
    DocumentProcessingPort,
    ProcessedChunk,
    ProcessedDocument,
)
from app.infrastructure.document.plaintext_processor import chunk_text

logger = logging.getLogger("knowlayer.ingestion")


class PdfDocumentProcessor:
    """Extract text from PDF pages and split into chunks using pypdf."""

    def supported_extensions(self) -> Sequence[str]:
        return (".pdf",)

    def supports(self, file_name: str) -> bool:
        return Path(file_name).suffix.lower() == ".pdf"

    def process(self, content: bytes, file_name: str) -> ProcessedDocument:
        from pypdf import PdfReader

        try:
            reader = PdfReader(BytesIO(content))
            pages_text = [page.extract_text() or "" for page in reader.pages]
            full_text = "\n\n".join(t.strip() for t in pages_text if t.strip())
        except Exception as exc:
            logger.error("Failed to extract text from PDF %r: %s", file_name, exc)
            raise ValueError(f"Failed to extract text from PDF {file_name}: {exc}") from exc

        chunks = tuple(
            ProcessedChunk(text=chunk, index=index)
            for index, chunk in enumerate(chunk_text(full_text))
            if chunk.strip()
        )
        logger.info("PDF processed %r into %d chunks", file_name, len(chunks))
        return ProcessedDocument(chunks=chunks, file_type="pdf")
