"""Stage 2 -- read text out of pictures with Docling's EasyOCR integration.

This stage is an *enrichment* step, not a parser. The document has already been
understood by Docling in stage 1; all we do here is take a picture Docling
already located and ask its OCR engine what the text says.

How EasyOCR is reached: the picture bytes are handed back to Docling as an
``InputFormat.IMAGE`` document with ``EasyOcrOptions`` configured. That runs
Docling's own pipeline (layout, then OCR) over the image, so the OCR engine,
its language handling, its scaling and its confidence threshold are all
Docling's. There is no second text-extraction path.

Docling does not OCR embedded DOCX pictures during normal conversion, which is
precisely why this stage exists.
"""

from __future__ import annotations

import logging
import tempfile
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import (
    EasyOcrOptions,
    OcrMode,
    PdfPipelineOptions,
)
from docling.document_converter import DocumentConverter, ImageFormatOption

from . import reporting as rep
from .config import Settings
from .stage1_docling import ExtractedPicture, ParsedDocument

logger = logging.getLogger("poc.ocr")


@dataclass
class OcrLine:
    text: str
    confidence: float


@dataclass
class OcrResult:
    """OCR outcome for one picture, tied back to where it came from."""

    source_document: str
    picture_ref: str
    page: int | None
    section: str
    engine: str
    lines: list[OcrLine]
    duration_seconds: float
    error: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def mean_confidence(self) -> float | None:
        if not self.lines:
            return None
        return sum(line.confidence for line in self.lines) / len(self.lines)

    @property
    def char_count(self) -> int:
        return sum(len(line.text) for line in self.lines)


def build_image_converter(settings: Settings) -> DocumentConverter:
    """A Docling converter whose OCR engine is EasyOCR.

    ``do_table_structure`` and picture classification are switched off: for a
    single embedded image we only want text, and leaving the other models on
    would add seconds per picture for no benefit.
    """
    options = PdfPipelineOptions()
    options.do_table_structure = False
    options.do_picture_classification = False
    options.do_picture_description = False
    options.images_scale = 1.0
    options.do_ocr = True
    options.ocr_options = EasyOcrOptions(
        mode=OcrMode.FULL_PAGE,
        lang=list(settings.ocr_languages),
        scale=settings.ocr_scale,
        use_gpu=False,
        confidence_threshold=settings.ocr_min_confidence,
    )
    return DocumentConverter(format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=options)})


def ocr_picture(
    converter: DocumentConverter,
    picture: ExtractedPicture,
    document_name: str,
    settings: Settings,
    workdir: Path,
) -> OcrResult:
    started = time.perf_counter()
    # Keep the extracted picture on disk so the VLM stage and a human can both
    # look at exactly the bytes that were processed.
    workdir.mkdir(parents=True, exist_ok=True)
    picture_path = workdir / f"{document_name}__{Path(picture.ref).name or 'picture'}.png"
    picture_path.write_bytes(picture.image_bytes)

    try:
        result = converter.convert(
            DocumentStream(name=picture_path.name, stream=BytesIO(picture.image_bytes))
        )
    except Exception as error:  # noqa: BLE001
        duration = time.perf_counter() - started
        return OcrResult(
            source_document=document_name,
            picture_ref=picture.ref,
            page=picture.page,
            section=picture.section,
            engine="easyocr (via docling)",
            lines=[],
            duration_seconds=duration,
            error=f"{type(error).__name__}: {error}",
        )

    lines: list[OcrLine] = []
    for text_item in result.document.texts:
        text = (text_item.text or "").strip()
        if not text:
            continue
        confidence = _confidence_of(text_item)
        # Docling's own threshold already filters weak cells; this is a second,
        # explicit guard so the reported number and the kept text agree.
        if confidence is not None and confidence < settings.ocr_min_confidence:
            continue
        lines.append(OcrLine(text=text, confidence=confidence if confidence is not None else -1.0))

    return OcrResult(
        source_document=document_name,
        picture_ref=picture.ref,
        page=picture.page,
        section=picture.section,
        engine="easyocr (via docling)",
        lines=lines,
        duration_seconds=time.perf_counter() - started,
    )


def _confidence_of(text_item) -> float | None:
    """Best available per-cell confidence.

    Text items produced by OCR do not always carry a confidence, so ``None`` is
    a legitimate answer and is reported as such rather than as 1.0.
    """
    meta = getattr(text_item, "meta", None)
    for attribute in ("ocr_score", "confidence"):
        value = getattr(text_item, attribute, None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        value = getattr(meta, attribute, None) if meta is not None else None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def pictures_needing_ocr(parsed: ParsedDocument, settings: Settings) -> list[ExtractedPicture]:
    """The pictures OCR is actually worth running on.

    Docling's own label is checked first because a decorative picture is a
    guaranteed waste: the router would ignore it no matter what OCR found, and a
    full OCR pass costs seconds. This is deliberately conservative -- only
    labels that are decorative regardless of content are skipped, and an
    unlabelled picture is always kept because its character count is the only
    routing signal available for it.
    """
    from .stage4_router import should_skip_ocr

    if not settings.skip_ocr_for_decorative:
        return list(parsed.pictures)
    return [picture for picture in parsed.pictures if not should_skip_ocr(picture)]


def run_ocr(
    parsed: ParsedDocument,
    converter: DocumentConverter,
    settings: Settings,
    workdir: Path,
) -> list[OcrResult]:
    """OCR the pictures of one document that are not already known to be junk."""
    if not parsed.pictures:
        rep.status("ocr", "SKIP", "no pictures in this document")
        return []
    if not settings.enable_ocr:
        rep.status("ocr", "SKIP", "disabled by configuration")
        return []

    targets = pictures_needing_ocr(parsed, settings)
    skipped = len(parsed.pictures) - len(targets)
    if skipped:
        rep.kv(
            "skipped by label",
            f"{skipped} picture(s) docling labelled decorative -- not worth an OCR pass",
        )
    if not targets:
        rep.status("ocr", "SKIP", "every picture is already labelled decorative")
        return []

    results: list[OcrResult] = []
    for picture in targets:
        result = ocr_picture(converter, picture, parsed.name, settings, workdir)
        results.append(result)
        if result.error:
            rep.status("ocr", "FAIL", f"{picture.ref}: {result.error}")
            continue
        mean = result.mean_confidence
        rep.element(
            index=picture.order,
            content_type="image_ocr",
            producer=result.engine,
            source=result.source_document,
            page=result.page,
            section=result.section,
            text=result.text,
            limit=settings.preview_chars,
            extra=[
                ("engine", result.engine),
                ("lines", len(result.lines)),
                ("characters", result.char_count),
                (
                    "mean confidence",
                    f"{mean:.3f}" if mean is not None and mean >= 0 else "not reported by docling",
                ),
                ("elapsed", f"{result.duration_seconds:.1f}s"),
            ],
        )
    return results


def _keep_temp_dir() -> Path:  # pragma: no cover - convenience for manual reruns
    directory = Path(tempfile.gettempdir()) / "docling-poc-pictures"
    directory.mkdir(parents=True, exist_ok=True)
    return directory
