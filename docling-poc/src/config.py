"""Configuration for the POC. Everything is environment-driven and optional.

No secret is ever hard-coded. The only credential the POC can possibly need is
a VLM API key, and the pipeline degrades to a clearly-reported "skipped" state
when it is absent rather than failing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    input_dir: Path
    output_dir: Path
    citation_pdf_dir: Path = OUTPUT_DIR / "citations"

    # -- Docling ------------------------------------------------------------
    #: Picture classification is what makes the router cheap: Docling already
    #: labels every picture, so we do not build our own detector.
    enable_picture_classification: bool = True
    #: Page-level OCR. Covers scanned PDFs; embedded pictures are handled
    #: separately in the OCR stage.
    enable_page_ocr: bool = True
    ocr_languages: tuple[str, ...] = ("en",)

    # -- OCR (Docling + EasyOCR) -------------------------------------------
    enable_ocr: bool = True
    ocr_engine: str = "easyocr"
    ocr_min_confidence: float = 0.35
    ocr_scale: float = 2.0

    # -- VLM ----------------------------------------------------------------
    enable_vlm: bool = True
    #: "local"  -> SmolVLM-256M on this machine (no key, no data leaves the box)
    #: "gemini" -> Gemini 2.5 Flash-Lite via API (needs POC_GEMINI_API_KEY)
    vlm_backend: str = os.getenv("POC_VLM_BACKEND", "local").strip().lower()
    gemini_api_key: str = os.getenv("POC_GEMINI_API_KEY", "").strip()
    gemini_model: str = os.getenv("POC_GEMINI_MODEL", "gemini-2.5-flash-lite")
    local_vlm_model: str = os.getenv(
        "POC_LOCAL_VLM_MODEL", "HuggingFaceTB/SmolVLM-256M-Instruct"
    )

    # -- Routing ------------------------------------------------------------
    #: An unlabelled picture that OCR finds text in is most likely a screenshot,
    #: so both OCR and VLM run on it. Set to false to keep the VLM spend down.
    route_unlabelled_text_to_vlm: bool = _flag("POC_ROUTE_UNLABELLED_TO_VLM", True)
    #: Skip OCR on pictures Docling already labelled decorative. Costs accuracy
    #: on nothing and saves a full OCR pass per logo.
    skip_ocr_for_decorative: bool = _flag("POC_SKIP_OCR_DECORATIVE", True)
    #: Render DOCX to PDF only when page-number citations are required.
    enable_citation_pdf: bool = _flag("POC_CITATION_PDF", False)

    # -- Reporting ----------------------------------------------------------
    #: Print the full text of every extracted element, not just a summary.
    verbose: bool = True
    #: Characters of each element shown in the terminal.
    preview_chars: int = 220


def load_settings(**overrides) -> Settings:
    base = Settings(
        input_dir=INPUT_DIR,
        output_dir=OUTPUT_DIR,
        citation_pdf_dir=OUTPUT_DIR / "citations",
        enable_picture_classification=_flag("POC_PICTURE_CLASSIFICATION", True),
        enable_page_ocr=_flag("POC_PAGE_OCR", True),
        enable_ocr=_flag("POC_OCR", True),
        enable_vlm=_flag("POC_VLM", True),
        route_unlabelled_text_to_vlm=_flag("POC_ROUTE_UNLABELLED_TO_VLM", True),
        skip_ocr_for_decorative=_flag("POC_SKIP_OCR_DECORATIVE", True),
        enable_citation_pdf=_flag("POC_CITATION_PDF", False),
    )
    return base if not overrides else _replace(base, **overrides)


def _replace(settings: Settings, **overrides) -> Settings:
    import dataclasses

    return dataclasses.replace(settings, **overrides)
