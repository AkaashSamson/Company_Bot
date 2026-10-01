"""Stage 1 -- parse documents with Docling. This is the only parser in the POC.

Docling handles DOCX, PDF and images directly. Nothing is converted to PDF on
the way in, and no second parser exists anywhere in this project.

What this stage produces for each document:

* an ordered walk of the document in reading order
* the structural label of every item (section_header, text, list_item, table,
  picture, ...)
* the page each item came from, when the format has pages at all
* the heading hierarchy in effect at each item
* Docling's own picture classification for every picture
* the raw bytes of every picture, so later stages can OCR or describe it

The classification matters more than it looks: it is the routing signal, and it
means this POC never has to invent its own image detector.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import (
    EasyOcrOptions,
    OcrMode,
    PdfPipelineOptions,
)
from docling.document_converter import (
    DocumentConverter,
    ImageFormatOption,
    PdfFormatOption,
)
from docling_core.types.doc import DocItemLabel, PictureItem

from . import reporting as rep
from .config import Settings

logger = logging.getLogger("poc.docling")

HEADING = str(DocItemLabel.SECTION_HEADER.value)

#: How a Docling item label maps onto the POC's neutral content types. The POC
#: does not need a full taxonomy; these six are what the experiment observes.
LABEL_TO_CONTENT_TYPE = {
    "section_header": "heading",
    "title": "heading",
    "text": "paragraph",
    "list_item": "list",
    "table": "table",
    "picture": "image",
    "formula": "paragraph",
    "caption": "paragraph",
    "footnote": "paragraph",
    "page_header": "paragraph",
    "page_footer": "paragraph",
}


@dataclass
class ExtractedPicture:
    """One picture lifted out of a document, with its Docling classification."""

    ref: str
    image_bytes: bytes
    order: int
    page: int | None
    section: str
    caption: str = ""
    classifications: list[tuple[str, float]] = field(default_factory=list)

    @property
    def top_class(self) -> tuple[str, float] | None:
        return self.classifications[0] if self.classifications else None


@dataclass
class ParsedItem:
    order: int
    content_type: str
    docling_label: str
    text: str
    page: int | None
    section: str
    level: int | None = None


@dataclass
class ParsedDocument:
    """Everything stage 1 learned about one source file."""

    path: Path
    name: str
    status: str
    page_count: int | None
    items: list[ParsedItem]
    pictures: list[ExtractedPicture]
    duration_seconds: float
    docling_json: dict[str, Any] | None = None
    error: str | None = None

    @property
    def label_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.docling_label] = counts.get(item.docling_label, 0) + 1
        return counts


def _page_of(item: Any) -> int | None:
    """Lowest page an item appears on, or None when the format has no pages.

    DOCX has no pagination in Docling, so ``None`` is the normal answer there.
    Guessing a page for DOCX would be inventing provenance, so we do not.
    """
    pages = [
        entry.page_no
        for entry in (getattr(item, "prov", None) or [])
        if isinstance(getattr(entry, "page_no", None), int)
        and not isinstance(entry.page_no, bool)
    ]
    return min(pages) if pages else None


def _table_text(table_item: Any) -> str:
    """Flatten a Docling table into pipe-separated rows.

    A TableItem carries no useful ``.text``; the cells live in its grid, so the
    text has to be read out of the structure. The values are what make a table
    searchable, so they are kept verbatim rather than summarised.
    """
    rows: list[str] = []
    try:
        grid = table_item.data.grid
    except Exception:  # noqa: BLE001 - a malformed table should not kill the run
        return ""
    for row in grid:
        cells = []
        for cell in row:
            try:
                cells.append(" ".join((cell.text or "").split()))
            except Exception:  # noqa: BLE001
                cells.append("")
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _classifications(picture: PictureItem) -> list[tuple[str, float]]:
    """Docling's picture labels, best first.

    Docling attaches these as an annotation when picture classification is on.
    """
    found: list[tuple[str, float]] = []
    for annotation in getattr(picture, "annotations", None) or []:
        if getattr(annotation, "kind", "") != "classification":
            continue
        for predicted in getattr(annotation, "predicted_classes", None) or []:
            name = str(getattr(predicted, "class_name", "")).strip()
            score = float(getattr(predicted, "confidence", 0.0) or 0.0)
            if name:
                found.append((name, score))
    found.sort(key=lambda pair: pair[1], reverse=True)
    return found


class PictureClassifier:
    """Runs Docling's own figure classifier over pictures that arrive unlabelled.

    Docling only runs ``do_picture_classification`` inside its PDF pipeline. A
    DOCX is read by the MSWord backend, which produces pictures but never
    invokes the classifier, so its pictures come back with no annotations at
    all. Without this pass every DOCX image would reach the router unlabelled
    and the router would have nothing to route on.

    This is Docling's model, driven over pictures Docling extracted -- not a
    second classifier and not a second parser. It only touches pictures that
    have no label yet, so a PDF that was already classified is left alone.
    """

    def __init__(self, enabled: bool):
        self._enabled = enabled
        self._model: Any | None = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            from docling.datamodel.accelerator_options import AcceleratorOptions
            from docling.models.stages.picture_classifier.document_picture_classifier import (
                DocumentPictureClassifier,
            )

            self._model = DocumentPictureClassifier(
                enabled=True,
                artifacts_path=None,
                # Reusing the options object from a real pipeline instance is
                # the reliable way to construct this: the options class has
                # required fields (model_spec, engine_options) that have no
                # sensible defaults.
                options=PdfPipelineOptions().picture_classification_options,
                accelerator_options=AcceleratorOptions(),
            )
        return self._model

    def classify(self, document: Any, items: list[tuple[PictureItem, Any]]) -> int:
        """Label the given pictures in place. Returns how many were labelled."""
        if not self._enabled or not items:
            return 0
        from docling.datamodel.base_models import ItemAndImageEnrichmentElement

        try:
            model = self._ensure_model()
            batch = [
                ItemAndImageEnrichmentElement(item=item, image=item.get_image(document))
                for item, _ in items
            ]
            # The model mutates each PictureItem by appending an annotation.
            list(model(doc=document, element_batch=batch))
        except Exception as error:  # noqa: BLE001
            rep.status("picture classification", "FAIL", f"{type(error).__name__}: {error}")
            return 0
        return sum(1 for item, _ in items if _classifications(item))


def _pipeline_options(settings: Settings) -> PdfPipelineOptions:
    options = PdfPipelineOptions()
    options.do_table_structure = True
    options.images_scale = 2.0
    options.generate_picture_images = True

    # Docling's own figure classifier. It is the POC's routing signal, which is
    # why no separate image detector is built here. Docling's picture
    # *description* stage is deliberately left off: the VLM in stage 3 is a
    # swappable adapter, and turning on both would run two models over every
    # picture for no experimental benefit.
    options.do_picture_classification = settings.enable_picture_classification

    # Page-level OCR. For scanned PDFs this is the only text source; for born
    # digital PDFs and DOCX it finds nothing and costs almost nothing.
    if settings.enable_page_ocr and settings.enable_ocr:
        options.do_ocr = True
        options.ocr_options = EasyOcrOptions(
            mode=OcrMode.DEFAULT,
            lang=list(settings.ocr_languages),
            scale=settings.ocr_scale,
            use_gpu=False,
            confidence_threshold=settings.ocr_min_confidence,
        )
    else:
        options.do_ocr = False
    return options


def build_converter(settings: Settings) -> DocumentConverter:
    """One converter, with the OCR engine applied to both PDFs and images.

    Note the engine choice lives in ``ocr_options``; Docling 2.130 selects the
    implementation from that options object, so EasyOCR is used for page-level
    OCR and for standalone image OCR without a second code path.
    """
    options = _pipeline_options(settings)
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options),
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
        }
    )


def parse_document(
    path: Path,
    converter: DocumentConverter,
    settings: Settings,
    classifier: PictureClassifier | None = None,
) -> ParsedDocument:
    import time

    started = time.perf_counter()
    raw = path.read_bytes()
    name = path.name
    print(f"\n  {rep.bold('INPUT')}  {name}  {rep.dim(f'({len(raw):,} bytes)')}")

    try:
        result = converter.convert(DocumentStream(name=name, stream=BytesIO(raw)))
    except Exception as error:  # noqa: BLE001 - a POC must report, not crash
        duration = time.perf_counter() - started
        rep.status("conversion", "FAIL", f"{type(error).__name__}: {error}")
        return ParsedDocument(
            path=path,
            name=name,
            status="FAILURE",
            page_count=None,
            items=[],
            pictures=[],
            duration_seconds=duration,
            error=f"{type(error).__name__}: {error}",
        )

    document = result.document
    duration = time.perf_counter() - started
    page_count = len(result.pages) if result.pages else None

    rep.status("conversion", "OK", f"status={result.status}, {duration:.1f}s")
    rep.kv("pages", page_count if page_count is not None else "none (format has no pagination)")

    items: list[ParsedItem] = []
    pictures: list[ExtractedPicture] = []
    # (docling PictureItem, our ExtractedPicture) pairs for pictures that came
    # back unlabelled, so the classification pass can update both.
    unlabelled: list[tuple[Any, ExtractedPicture]] = []
    section_stack: list[tuple[int, str]] = []

    for order, (item, level) in enumerate(document.iterate_items()):
        label = str(getattr(item.label, "value", item.label) or "").strip().lower()
        text = (getattr(item, "text", "") or "").strip()
        page = _page_of(item)

        if label == HEADING and text:
            while section_stack and section_stack[-1][0] >= level:
                section_stack.pop()
            section_path = " > ".join(title for _, title in section_stack)
            section_stack.append((level, text))
        else:
            section_path = " > ".join(title for _, title in section_stack)

        content_type = LABEL_TO_CONTENT_TYPE.get(label, "other")

        if label == "picture":
            image = item.get_image(document)
            if image is not None:
                buffer = BytesIO()
                image.save(buffer, format="PNG")
                extracted = ExtractedPicture(
                    ref=str(getattr(item, "self_ref", "")),
                    image_bytes=buffer.getvalue(),
                    order=order,
                    page=page,
                    section=section_path,
                    caption=" | ".join(
                        (c.text or "").strip() for c in (getattr(item, "captions", None) or [])
                    ),
                    classifications=_classifications(item),
                )
                pictures.append(extracted)
                if not extracted.classifications:
                    unlabelled.append((item, extracted))
            items.append(
                ParsedItem(
                    order=order,
                    content_type="image",
                    docling_label=label,
                    text="",
                    page=page,
                    section=section_path,
                )
            )
            continue

        if not text and label == "table":
            text = _table_text(item)

        if not text:
            continue

        items.append(
            ParsedItem(
                order=order,
                content_type=content_type,
                docling_label=label,
                text=text,
                page=page,
                section=section_path,
                level=level if label == HEADING else None,
            )
        )

    # Label anything the pipeline left unlabelled. This is the normal path for
    # DOCX; for a PDF it is a no-op because the pipeline already classified.
    if unlabelled:
        if settings.enable_picture_classification and classifier is not None:
            labelled = classifier.classify(document, unlabelled)
            for item, extracted in unlabelled:
                extracted.classifications = _classifications(item)
            rep.status(
                "picture classification",
                "OK" if labelled else "FAIL",
                f"docling labelled {labelled}/{len(unlabelled)} picture(s) "
                f"(the PDF pipeline skips this stage for DOCX)",
            )
        elif not settings.enable_picture_classification:
            rep.status("picture classification", "SKIP", "disabled by configuration")

    try:
        docling_json = document.export_to_dict()
    except Exception as error:  # noqa: BLE001
        logger.warning("docling json export failed for %s: %s", name, error)
        docling_json = None

    parsed = ParsedDocument(
        path=path,
        name=name,
        status=str(result.status),
        page_count=page_count,
        items=items,
        pictures=pictures,
        duration_seconds=duration,
        docling_json=docling_json,
    )
    _report_items(parsed, settings)
    return parsed


def _report_items(parsed: ParsedDocument, settings: Settings) -> None:
    counts = parsed.label_counts
    rep.kv(
        "structure",
        ", ".join(f"{label}={count}" for label, count in sorted(counts.items())) or "nothing",
    )
    rep.kv("pictures found", len(parsed.pictures))

    if not settings.verbose:
        return

    for item in parsed.items:
        if item.content_type == "image":
            continue
        rep.element(
            index=item.order,
            content_type=item.content_type,
            producer=f"docling ({item.docling_label})",
            source=parsed.name,
            page=item.page,
            section=item.section,
            text=item.text,
            limit=settings.preview_chars,
        )

    for picture in parsed.pictures:
        top = picture.top_class
        rep.element(
            index=picture.order,
            content_type="image_detected",
            producer="docling (picture classification)",
            source=parsed.name,
            page=picture.page,
            section=picture.section,
            text=(
                f"{len(picture.image_bytes):,} bytes of PNG extracted"
                + (f" | caption: {picture.caption}" if picture.caption else "")
            ),
            limit=settings.preview_chars,
            extra=[("docling class", f"{top[0]} ({top[1]:.2f})" if top else "unclassified")],
        )
        for name, score in picture.classifications[1:4]:
            rep.bullet(f"also: {name} ({score:.2f})")
