"""Remote GPU-accelerated document processor adapter for DocumentProcessingPort.

Dispatches document conversion and structural chunking over HTTP to a remote
GPU worker (e.g. running on Kaggle with dual Tesla T4 / P100 GPUs or cloud VM).
Returns a neutral ProcessedDocument, allowing local ChromaDB and SQLite storage
to proceed identically with zero local CPU load.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import httpx

from app.core.settings import DOCLING_REMOTE_TIMEOUT
from app.domain.ports.document_processing import (
    DocumentProcessingPort,
    ProcessedChunk,
    ProcessedDocument,
    SectionHeading,
)

logger = logging.getLogger("knowlayer.ingestion.remote")

# Standard extensions supported by remote Docling GPU service
REMOTE_SUPPORTED_EXTENSIONS = (
    ".asciidoc",
    ".docx",
    ".html",
    ".md",
    ".pdf",
    ".pptx",
    ".xlsx",
)


class RemoteDoclingProcessor:
    """DocumentProcessingPort adapter delegating conversion to a remote GPU worker."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = DOCLING_REMOTE_TIMEOUT,
        fallback: DocumentProcessingPort | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._fallback = fallback

    def supported_extensions(self) -> Sequence[str]:
        return REMOTE_SUPPORTED_EXTENSIONS

    def supports(self, file_name: str) -> bool:
        ext = Path(file_name).suffix.lower()
        return ext in REMOTE_SUPPORTED_EXTENSIONS

    def process(self, content: bytes, file_name: str) -> ProcessedDocument:
        """Upload raw document bytes to remote GPU worker and parse response."""
        endpoint = f"{self._base_url}/process-document"
        logger.info(
            "Dispatching %r (%d bytes) to remote GPU worker at %s",
            file_name,
            len(content),
            endpoint,
        )

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                files = {"file": (Path(file_name).name, content, "application/octet-stream")}
                response = client.post(endpoint, files=files)
                response.raise_for_status()
                data = response.json()

            chunks: list[ProcessedChunk] = []
            for item in data.get("chunks", []):
                section_path = tuple(
                    SectionHeading(level=int(h["level"]), title=str(h["title"]))
                    for h in item.get("section_path", [])
                    if isinstance(h, dict) and "level" in h and "title" in h
                )
                chunks.append(
                    ProcessedChunk(
                        text=str(item.get("text", "")),
                        index=int(item.get("index", len(chunks))),
                        page_number=item.get("page_number"),
                        section_path=section_path,
                        content_type=str(item.get("content_type", "text")),
                        metadata=dict(item.get("metadata", {})),
                    )
                )

            outline = tuple(
                SectionHeading(level=int(h["level"]), title=str(h["title"]))
                for h in data.get("outline", [])
                if isinstance(h, dict) and "level" in h and "title" in h
            )

            file_type = data.get("file_type") or Path(file_name).suffix.lower().lstrip(".") or None
            page_count = data.get("page_count")

            logger.info(
                "Remote GPU worker successfully processed %r: %d chunks, %d outline entries, %s pages",
                file_name,
                len(chunks),
                len(outline),
                page_count,
            )

            return ProcessedDocument(
                chunks=tuple(chunks),
                file_type=file_type,
                page_count=page_count,
                outline=outline,
                metadata=dict(data.get("metadata", {})),
            )

        except Exception as error:
            logger.warning(
                "Remote GPU processing failed for %r at %s: %s",
                file_name,
                endpoint,
                error,
            )
            if self._fallback is not None and self._fallback.supports(file_name):
                logger.info("Falling back to local processor for %r", file_name)
                return self._fallback.process(content, file_name)

            raise ValueError(
                f"Remote document processing service at {self._base_url} is unreachable or returned an error: {error}. "
                f"Please ensure your Kaggle GPU notebook is active and Cloudflare Tunnel is running."
            ) from error
