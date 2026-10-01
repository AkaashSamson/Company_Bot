"""Stage 5 -- one flat, uniform representation of everything that was found.

By this point the document exists as three different kinds of knowledge: text
Docling read directly, text EasyOCR read out of a picture, and prose a VLM
wrote about a picture. Stage 5 collapses them into a single list of elements
so the rest of the experiment can treat them uniformly.

This is deliberately a demonstration format, not a production domain model. It
exists to answer one question: can all of this end up as searchable text while
still carrying enough provenance to cite it? Every element records where it came
from and which stage produced it, so the answer is inspectable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from . import reporting as rep
from .config import Settings
from .stage1_docling import ParsedDocument
from .stage2_ocr import OcrResult
from .stage3_vlm import VlmResult
from .stage4_router import RoutingDecision, Route

#: Element kinds, matching the vocabulary the experiment set out to observe.
HEADING = "heading"
PARAGRAPH = "paragraph"
LIST = "list"
TABLE = "table"
IMAGE_OCR = "image_ocr"
IMAGE_DESCRIPTION = "image_description"
IMAGE_SKIPPED = "image_skipped"

#: Provenance values, so it is always clear whether text was read or written.
SOURCE_DOCUMENT = "docling"          # text present in the document
SOURCE_OCR = "docling+easyocr"       # text read from a picture
SOURCE_VLM = f"vlm"                  # prose written about a picture


@dataclass
class Element:
    """One searchable unit, with everything needed to cite it."""

    index: int
    content_type: str
    content: str
    source_document: str
    page: int | None = None
    section: str = ""
    produced_by: str = SOURCE_DOCUMENT
    docling_label: str = ""
    picture_ref: str | None = None
    routing: str | None = None
    confidence: float | None = None
    model: str | None = None
    #: False when a human or a downstream check is needed before this is cited.
    #: Only VLM prose and elements whose numbers disagree with OCR set this.
    verified: bool = True
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        # ``verified`` is always emitted, including when True: a consumer that
        # defaults a missing field to "unknown" must be able to tell the
        # difference between checked and unchecked.
        return {
            k: v
            for k, v in asdict(self).items()
            if k == "verified" or v not in (None, "", 0) or k in {"index"}
        }


@dataclass
class NormalizedDocument:
    source_document: str
    file_type: str
    page_count: int | None
    status: str
    elements: list[Element] = field(default_factory=list)
    routing: list[RoutingDecision] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_document": self.source_document,
            "file_type": self.file_type,
            "page_count": self.page_count,
            "status": self.status,
            "element_count": len(self.elements),
            "elements": [element.as_dict() for element in self.elements],
            "routing": [decision.as_dict() for decision in self.routing],
            "warnings": self.warnings,
        }


def _table_to_text(table_item: Any) -> str:
    """Render a Docling table as pipe-separated rows.

    Keeps the cell values, which is what matters for search, without
    pretending to be Markdown.
    """
    rows: list[str] = []
    try:
        grid = table_item.data.grid
    except Exception:  # noqa: BLE001
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


def normalize(
    parsed: ParsedDocument,
    ocr_results: list[OcrResult],
    vlm_results: list[VlmResult],
    decisions: list[RoutingDecision],
    settings: Settings,
    citation_item_pages: dict[int, int] | None = None,
    citation_picture_pages: dict[str, int] | None = None,
) -> NormalizedDocument:
    """Flatten one parsed document plus its enrichments into ordered elements."""
    # A picture is located in the document by an order index; everything else
    # is attached to that anchor so enrichment lands in the right place.
    ocr_by_ref = {result.picture_ref: result for result in ocr_results}
    vlm_by_ref = {result.picture_ref: result for result in vlm_results}
    decision_by_ref = {decision.picture_ref: decision for decision in decisions}
    citation_item_pages = citation_item_pages or {}
    citation_picture_pages = citation_picture_pages or {}

    warnings: list[str] = []
    if parsed.error:
        warnings.append(parsed.error)

    elements: list[Element] = []

    for item in parsed.items:
        if item.content_type == "image":
            picture = next((p for p in parsed.pictures if p.order == item.order), None)
            if picture is None:
                continue
            elements.extend(
                _picture_elements(
                    parsed=parsed,
                    picture=picture,
                    ocr_result=ocr_by_ref.get(picture.ref),
                    vlm_result=vlm_by_ref.get(picture.ref),
                    decision=decision_by_ref.get(picture.ref),
                    settings=settings,
                    warnings=warnings,
                    citation_page=citation_picture_pages.get(picture.ref),
                )
            )
            continue

        elements.append(
            Element(
                index=-1,  # renumbered once the whole document is assembled
                content_type=item.content_type,
                content=item.text,
                source_document=parsed.name,
                page=citation_item_pages.get(item.order, item.page),
                section=item.section,
                produced_by=SOURCE_DOCUMENT,
                docling_label=item.docling_label,
            )
        )

    for position, element in enumerate(elements):
        element.index = position

    return NormalizedDocument(
        source_document=parsed.name,
        file_type=parsed.path.suffix.lstrip("."),
        page_count=parsed.page_count,
        status=parsed.status,
        elements=elements,
        routing=list(decisions),
        warnings=warnings,
    )


def _picture_elements(
    *,
    parsed: ParsedDocument,
    picture: Any,
    ocr_result: OcrResult | None,
    vlm_result: VlmResult | None,
    decision: RoutingDecision | None,
    settings: Settings,
    warnings: list[str],
    citation_page: int | None = None,
) -> list[Element]:
    """Turn one picture's enrichments into zero, one or two elements."""
    route = decision.route if decision else Route.IGNORE
    out: list[Element] = []

    if ocr_result and ocr_result.error:
        warnings.append(f"ocr failed for {picture.ref}: {ocr_result.error}")
    if vlm_result and vlm_result.error:
        warnings.append(f"vlm failed for {picture.ref}: {vlm_result.error}")

    # OCR text is kept whenever it exists, even if the picture was also sent to
    # the VLM: the exact words are worth more than a description for search,
    # and the VLM adds the meaning on top.
    if ocr_result and ocr_result.text.strip():
        out.append(
            Element(
                index=-1,  # renumbered by the caller
                content_type=IMAGE_OCR,
                content=ocr_result.text,
                source_document=parsed.name,
                page=citation_page if citation_page is not None else picture.page,
                section=picture.section,
                produced_by=SOURCE_OCR,
                docling_label="picture",
                picture_ref=picture.ref,
                routing=route.value,
                confidence=ocr_result.mean_confidence,
                note=(
                    f"docling classified this picture as "
                    f"{decision.docling_class if decision else 'unclassified'}"
                ),
            )
        )

    if vlm_result and vlm_result.description.strip():
        description = vlm_result.description
        verified = False  # VLM prose must not be treated as verified document text.
        notes = ["written by a model, not read from the document"]
        # A lightweight cross-check for chart values: pull numbers from the VLM
        # description and from OCR and flag any obvious mismatch. This cannot be
        # perfect, but it catches the 63-type failure.
        if decision and decision.docling_class in {
            "bar_chart",
            "line_chart",
            "pie_chart",
            "other_chart",
            "scatter_plot",
            "scatter_chart",
            "stacked_bar_chart",
            "box_plot",
            "heatmap",
        } and ocr_result and ocr_result.text.strip():
            import re

            def _numbers(text: str) -> set[str]:
                return set(re.findall(r"-?\d+(?:[.,]\d+)?", text))

            ocr_numbers = _numbers(ocr_result.text)
            vlm_numbers = _numbers(description)
            if vlm_numbers and ocr_numbers and not vlm_numbers.issubset(ocr_numbers | {s.replace(",", ".") for s in ocr_numbers}):
                verified = False
                notes.append("numbers differ from OCR")
        out.append(
            Element(
                index=-1,
                content_type=IMAGE_DESCRIPTION,
                content=description,
                source_document=parsed.name,
                page=citation_page if citation_page is not None else picture.page,
                section=picture.section,
                produced_by=SOURCE_VLM,
                docling_label="picture",
                picture_ref=picture.ref,
                routing=route.value,
                model=vlm_result.model,
                verified=verified,
                note="; ".join(notes),
            )
        )

    if not out:
        reason = decision.reason if decision else "no enrichment produced"
        out.append(
            Element(
                index=-1,
                content_type=IMAGE_SKIPPED,
                content="",
                source_document=parsed.name,
                page=citation_page if citation_page is not None else picture.page,
                section=picture.section,
                produced_by=SOURCE_DOCUMENT,
                docling_label="picture",
                picture_ref=picture.ref,
                routing=route.value,
                note=f"routed to {route.value}: {reason}",
            )
        )
    return out


def report(document: NormalizedDocument, settings: Settings) -> None:
    if not settings.verbose:
        return
    print(f"\n  {rep.bold('NORMALIZED ELEMENTS')}  {rep.dim(f'({len(document.elements)} total)')}")
    for element in document.elements:
        rep.element(
            index=element.index,
            content_type=element.content_type,
            producer=element.produced_by,
            source=element.source_document,
            page=element.page,
            section=element.section,
            text=element.content or element.note,
            limit=settings.preview_chars,
            extra=[(k, v) for k, v in (
                ("picture", element.picture_ref),
                ("routing", element.routing),
                ("confidence", f"{element.confidence:.3f}" if element.confidence is not None else None),
                ("model", element.model),
                ("verified", "yes" if element.verified else "NO"),
                ("note", element.note or None),
            ) if v],
        )
