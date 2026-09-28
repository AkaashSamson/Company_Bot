"""Fixed-width text implementation of :class:`DocumentProcessingPort`.

This is the pre-existing extraction and chunking behaviour -- ``python-docx``
for ``.docx``, UTF-8 decoding for the text formats, and fixed-width paragraph
and sentence chunking -- presented through the same port as the structural
parser.

It exists for two reasons:

* it is the pipeline the application used before the structural parser, and
  remains the active one while that parser is held behind ``DOCLING_ENABLED``;
* it is the fallback for formats the structural parser cannot handle, so a
  supported file type is never silently lost when the parser is enabled.

Importing the extraction and chunking primitives from the ingestion use case
mirrors how :mod:`app.infrastructure.document.local_document_loader` and
:mod:`app.infrastructure.ingestion.provisioner` already obtain
``SUPPORTED_EXTENSIONS``. The primitives have not been relocated, so that
decision stays open without being forced here.
"""

import logging
from pathlib import Path
from typing import Sequence

from app.domain.ports.document_processing import (
    DocumentProcessingPort,
    ProcessedChunk,
    ProcessedDocument,
)
from app.use_cases.ingestion.document_processing import (
    SUPPORTED_EXTENSIONS,
    chunk_text,
    extract_text_from_bytes,
)

logger = logging.getLogger("knowlayer.ingestion")


class PlainTextDocumentProcessor:
    """Parse and chunk documents with the fixed-width text pipeline.

    Reports no document structure: the fixed-width splitter has no notion of
    headings or pages, so ``page_number`` is left unset, the heading hierarchy
    is empty, and the content type is plain text. Those omissions are
    meaningful and are not backfilled.
    """

    def supported_extensions(self) -> Sequence[str]:
        """Extensions the text pipeline has always accepted."""
        return tuple(sorted(SUPPORTED_EXTENSIONS))

    def supports(self, file_name: str) -> bool:
        return Path(file_name).suffix.lower() in SUPPORTED_EXTENSIONS

    def process(self, content: bytes, file_name: str) -> ProcessedDocument:
        """Extract text and split it into fixed-width chunks.

        Raises ``ValueError`` for an unsupported extension, matching the
        convention the ingestion layer maps to a rejected upload.
        """
        if not self.supports(file_name):
            supported = ", ".join(self.supported_extensions())
            suffix = Path(file_name).suffix.lower()
            raise ValueError(
                f"Unsupported document type: {suffix or '(none)'} (supported: {supported})"
            )

        text = extract_text_from_bytes(content, file_name)
        chunks = tuple(
            ProcessedChunk(text=chunk, index=index)
            for index, chunk in enumerate(chunk_text(text))
            if chunk.strip()
        )
        logger.info(
            "plaintext processed %r into %d chunks", file_name, len(chunks)
        )
        return ProcessedDocument(
            chunks=chunks,
            file_type=Path(file_name).suffix.lower().lstrip(".") or None,
        )
