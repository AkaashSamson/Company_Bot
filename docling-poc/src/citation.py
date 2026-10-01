"""Optional rendered-PDF citation support for DOCX sources."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from docling.datamodel.base_models import DocumentStream
from docling.document_converter import DocumentConverter

from . import reporting as rep
from .config import Settings
from .stage1_docling import ParsedDocument


@dataclass
class CitationPageMap:
    """Page anchors produced by the optional rendered citation PDF."""

    document_id: str
    source_filename: str
    pdf_path: Path
    item_pages: dict[int, int]
    picture_pages: dict[str, int]


def _normalise_text(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _page_of(item: Any) -> int | None:
    pages = [
        entry.page_no
        for entry in (getattr(item, "prov", None) or [])
        if isinstance(getattr(entry, "page_no", None), int)
        and not isinstance(entry.page_no, bool)
    ]
    return min(pages) if pages else None


def _find_soffice() -> str | None:
    configured = os.getenv("POC_LIBREOFFICE_PATH", "").strip()
    if configured and Path(configured).exists():
        return configured
    for name in ("soffice", "soffice.exe", "libreoffice", "libreoffice.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def render_citation_pdf(source: Path, output_dir: Path) -> Path:
    """Render a DOCX to PDF using LibreOffice for stable page citations."""
    executable = _find_soffice()
    if not executable:
        raise RuntimeError(
            "LibreOffice was not found; install LibreOffice or set POC_LIBREOFFICE_PATH"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    expected = output_dir / f"{source.stem}.pdf"
    command = [
        executable,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(source),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0 or not expected.exists():
        detail = (completed.stderr or completed.stdout or "no output").strip()
        raise RuntimeError(f"LibreOffice conversion failed: {detail[:500]}")
    return expected


def _page_texts(document: Any) -> dict[int, str]:
    pages: dict[int, list[str]] = {}
    for item, _level in document.iterate_items():
        page = _page_of(item)
        if page is None:
            continue
        text = (getattr(item, "text", "") or "").strip()
        if text:
            pages.setdefault(page, []).append(text)
    return {page: _normalise_text(" ".join(values)) for page, values in pages.items()}


def _match_page(text: str, section: str, pages: dict[int, str]) -> int | None:
    needle = _normalise_text(text)
    if needle:
        if len(needle) > 180:
            needle = needle[:180]
        for page, page_text in pages.items():
            if needle in page_text:
                return page

    headings = [part.strip() for part in section.split(" > ") if part.strip()]
    for heading in reversed(headings):
        needle = _normalise_text(heading)
        for page, page_text in pages.items():
            if needle and needle in page_text:
                return page
    return None


def build_citation_page_map(
    parsed: ParsedDocument,
    converter: DocumentConverter,
    settings: Settings,
) -> CitationPageMap:
    """Render and parse one DOCX, then map source anchors to PDF pages."""
    pdf_path = render_citation_pdf(parsed.path, settings.citation_pdf_dir)
    raw = pdf_path.read_bytes()
    result = converter.convert(DocumentStream(name=pdf_path.name, stream=BytesIO(raw)))
    pages = _page_texts(result.document)

    item_pages: dict[int, int] = {}
    picture_pages: dict[str, int] = {}
    for item in parsed.items:
        page = _match_page(item.text, item.section, pages)
        if page is not None:
            item_pages[item.order] = page
    for picture in parsed.pictures:
        page = _match_page(picture.caption, picture.section, pages)
        if page is not None:
            picture_pages[picture.ref] = page

    return CitationPageMap(
        document_id=hashlib.sha256(parsed.path.read_bytes()).hexdigest(),
        source_filename=parsed.name,
        pdf_path=pdf_path,
        item_pages=item_pages,
        picture_pages=picture_pages,
    )


def citation_chunks(document: Any, page_map: CitationPageMap | None) -> list[dict[str, Any]]:
    """Create the platform-facing citation chunk contract."""
    document_id = page_map.document_id if page_map else hashlib.sha256(
        document.source_document.encode("utf-8")
    ).hexdigest()
    source_filename = page_map.source_filename if page_map else document.source_document
    chunks: list[dict[str, Any]] = []
    for element in document.elements:
        if element.content_type == "image_skipped" or not element.content.strip():
            continue
        hierarchy = [part.strip() for part in element.section.split(" > ") if part.strip()]
        if element.content_type == "heading" and element.content not in hierarchy:
            hierarchy.append(element.content)
        section_heading = hierarchy[-1] if hierarchy else None
        chunks.append(
            {
                "document_id": document_id,
                "source_filename": source_filename,
                "page_number": element.page,
                "section_heading": section_heading,
                "hierarchy_path": hierarchy,
                "chunk_index": element.index,
                "content_type": "text",
                "content": element.content,
                "source_content_type": element.content_type,
                "produced_by": element.produced_by,
                "verified": element.verified,
                "review_required": not element.verified,
                "picture_ref": element.picture_ref,
            }
        )
    return chunks
