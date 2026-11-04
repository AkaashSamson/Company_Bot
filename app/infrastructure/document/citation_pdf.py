"""Optional DOCX rendering used to provide stable page citations."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from docling.datamodel.base_models import DocumentStream
from docling.document_converter import DocumentConverter

from app.domain.ports.document_processing import ProcessedChunk
from app.core.settings import DOCLING_LIBREOFFICE_PATH

logger = logging.getLogger("knowlayer.ingestion.citation")


def _executable() -> str | None:
    configured = (DOCLING_LIBREOFFICE_PATH or os.getenv("POC_LIBREOFFICE_PATH", "")).strip()
    if configured and Path(configured).exists():
        return configured
    for name in ("soffice", "soffice.exe", "libreoffice", "libreoffice.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _normalise(value: str) -> str:
    return " ".join(value.lower().split())


def _page_texts(document: Any) -> dict[int, str]:
    pages: dict[int, list[str]] = {}
    for item, _level in document.iterate_items():
        provenance = getattr(item, "prov", None) or []
        page_numbers = {
            entry.page_no
            for entry in provenance
            if isinstance(getattr(entry, "page_no", None), int)
            and not isinstance(entry.page_no, bool)
        }
        text = (getattr(item, "text", "") or "").strip()
        for page in page_numbers:
            if text:
                pages.setdefault(page, []).append(text)
    return {page: _normalise(" ".join(parts)) for page, parts in pages.items()}


def _find_page(chunk: ProcessedChunk, pages: dict[int, str]) -> int | None:
    text = _normalise(chunk.text)
    if len(text) > 180:
        text = text[:180]
    if text:
        for page, page_text in pages.items():
            if text in page_text:
                return page

    headings = chunk.hierarchy_titles
    for heading in reversed(headings):
        needle = _normalise(heading)
        for page, page_text in pages.items():
            if needle and needle in page_text:
                return page
    return None


def map_docx_pages(
    content: bytes,
    file_name: str,
    chunks: tuple[ProcessedChunk, ...],
    converter: DocumentConverter,
    output_dir: str,
) -> tuple[tuple[ProcessedChunk, ...], Path]:
    """Render DOCX with LibreOffice and attach rendered page numbers to chunks."""
    executable = _executable()
    if executable is None:
        raise ValueError(
            "DOCX citation PDF is enabled, but LibreOffice was not found; "
            "install LibreOffice or set POC_LIBREOFFICE_PATH"
        )

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(content).hexdigest()[:16]
    safe_name = Path(file_name).stem or "document"
    with TemporaryDirectory(prefix="company-bot-citation-") as temporary:
        source = Path(temporary) / f"{safe_name}-{digest}.docx"
        source.write_bytes(content)
        command = [
            executable,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(destination),
            str(source),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        rendered = destination / f"{source.stem}.pdf"
        if completed.returncode != 0 or not rendered.exists():
            detail = (completed.stderr or completed.stdout or "no output").strip()
            raise ValueError(f"DOCX citation PDF conversion failed: {detail[:500]}")

    parsed = converter.convert(
        DocumentStream(name=rendered.name, stream=BytesIO(rendered.read_bytes()))
    ).document
    pages = _page_texts(parsed)
    mapped = tuple(
        replace(chunk, page_number=_find_page(chunk, pages) or chunk.page_number)
        for chunk in chunks
    )
    logger.info("mapped %d chunks to citation PDF pages: %s", len(mapped), rendered)
    return mapped, rendered
