"""Stage 4 -- decide what each picture actually needs.

The whole point of a router is that most pictures need nothing. Sending every
image to a VLM costs time, money and storage, and most documents are full of
logos, dividers and decorative marks that carry nothing retrievable.

The classifier is deliberately thin. It does not try to be a general vision
model. It starts from the label Docling's own figure classifier already
produced, adds two cheap signals, and lands on one of three routes:

    TEXT_HEAVY  -> OCR      the picture is mostly words; OCR reads it exactly
    VISUAL      -> VLM      the picture carries structure, relationships or values
    BOTH        -> OCR+VLM  text *and* layout matter, so keep both outputs
    IGNORE      -> nothing  decorative, too small, or empty

Two things here are deliberately cheaper than they look:

* :func:`should_skip_ocr` is a label-only decision that runs *before* OCR, so a
  logo never costs a full OCR pass. OCR itself is the routing probe, which is
  why the ordering used to waste it on decorative pictures.
* A text-heavy screenshot goes to both OCR and VLM rather than to one or the
  other. OCR gives the exact words; OCR alone throws away which field sits next
  to which, which for a UI screenshot is usually the point.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from . import reporting as rep
from .config import Settings
from .stage1_docling import ExtractedPicture
from .stage2_ocr import OcrResult


class Route(str, Enum):
    OCR = "OCR"
    VLM = "VLM"
    #: Both outputs are kept: OCR for the exact words, VLM for the layout.
    BOTH = "OCR+VLM"
    IGNORE = "IGNORE"

    @property
    def wants_ocr(self) -> bool:
        return self in {Route.OCR, Route.BOTH}

    @property
    def wants_vlm(self) -> bool:
        return self in {Route.VLM, Route.BOTH}


#: Docling's figure labels grouped by what we actually want to do with them.
#: Source: docling_core.types.doc.labels.PictureClassificationLabel
CHART_LABELS = {
    "bar_chart", "line_chart", "pie_chart", "other_chart", "scatter_plot",
    "scatter_chart", "stacked_bar_chart", "box_plot", "heatmap",
}
DIAGRAM_LABELS = {
    "flow_chart", "electrical_diagram", "engineering_drawing", "cad_drawing",
}
SCREENSHOT_LABELS = {
    "screenshot", "screenshot_from_computer", "screenshot_from_manual",
}
DECORATIVE_LABELS = {
    "logo", "icon", "bar_code", "qr_code", "stamp", "signature",
    "page_thumbnail", "natural_image", "photograph", "other",
}
    #: An image of a table is usually text, but BOTH protects against a chart
    #: that Docling classified as a table.
TEXTUAL_LABELS = {"table"}


@dataclass
class RoutingDecision:
    picture_ref: str
    source_document: str
    page: int | None
    section: str
    route: Route
    reason: str
    docling_class: str
    docling_confidence: float | None
    ocr_characters: int

    def as_dict(self) -> dict:
        return {
            "source_document": self.source_document,
            "picture_ref": self.picture_ref,
            "page": self.page,
            "section": self.section,
            "route": self.route.value,
            "reason": self.reason,
            "docling_class": self.docling_class,
            "docling_confidence": self.docling_confidence,
            "ocr_characters": self.ocr_characters,
        }


def _normalise(label: str) -> str:
    return str(label or "").strip().lower().replace(" ", "_").replace("-", "_")


def should_skip_ocr(picture: ExtractedPicture) -> bool:
    """Whether a picture can be ignored before OCR runs, on its label alone.

    Stage 2 needs to know this so it does not spend a full OCR pass on a logo.
    Only labels that are decorative *regardless of content* qualify, because
    anything else might turn out to be text-heavy and the character count is a
    routing input. An unlabelled picture is never skipped: it is exactly the
    case where OCR is the only signal available.
    """
    top = picture.top_class
    return bool(top) and _normalise(top[0]) in DECORATIVE_LABELS


def decide(
    picture: ExtractedPicture,
    ocr_result: OcrResult | None,
    settings: Settings,
) -> RoutingDecision:
    """Route one picture, given whatever OCR already found in it.

    OCR is a probe here, not the final answer: the router uses the character
    count to tell a text-heavy image from a diagram whose labels OCR could read
    but whose meaning it cannot express.
    """
    top = picture.top_class
    label = _normalise(top[0]) if top else ""
    confidence = top[1] if top else None
    characters = ocr_result.char_count if ocr_result else 0

    def decision(route: Route, reason: str) -> RoutingDecision:
        return RoutingDecision(
            picture_ref=picture.ref,
            source_document=ocr_result.source_document if ocr_result else "",
            page=picture.page,
            section=picture.section,
            route=route,
            reason=reason,
            docling_class=label or "unclassified",
            docling_confidence=confidence,
            ocr_characters=characters,
        )

    # 1. Explicitly uninformative. Do this first so a logo never costs an OCR call.
    if label in DECORATIVE_LABELS:
        return decision(Route.IGNORE, f"docling classified it as {label}, which carries no retrievable content")

    # 2. Structure the words cannot express.
    if label in CHART_LABELS:
        return decision(Route.VLM, f"docling classified it as {label}; the values and trend are the content")
    if label in DIAGRAM_LABELS:
        return decision(Route.VLM, f"docling classified it as {label}; the relationships live in the arrows")

    # 3. Text-shaped content, including an image of a table.
    if label in TEXTUAL_LABELS:
        return decision(Route.BOTH, f"docling classified it as {label}; keep OCR text and VLM visual validation")
    if label in SCREENSHOT_LABELS:
        if characters >= _text_threshold(settings):
            return decision(
                Route.BOTH,
                f"docling classified it as {label} and OCR found {characters} characters; keep exact text and layout",
            )
        return decision(Route.VLM, f"docling classified it as {label} but OCR found little text; its layout is the content")

    # 4. No usable label: fall back to the size of what OCR found. Docling's
    # label is absent, so the picture could be anything -- most likely a text
    # screenshot, where OCR alone would discard the layout. Route both unless
    # the extra VLM cost is switched off.
    unknown_route = Route.BOTH if settings.route_unlabelled_text_to_vlm else Route.OCR
    if characters >= _text_threshold(settings):
        return decision(unknown_route, f"unclassified, but OCR found {characters} characters of text")
    if characters > 0:
        return decision(unknown_route, f"unclassified, but OCR found {characters} characters of text")

    # 5. An unclassified image with no OCR text may still be a visual-only
    # diagram or chart. Let the VLM inspect it instead of discarding it.
    if not label and settings.route_unlabelled_text_to_vlm:
        return decision(Route.VLM, "unclassified and OCR found no text; visual review required")

    return decision(Route.IGNORE, "no classification and no text detected")


def _text_threshold(settings: Settings) -> int:
    """Characters above which a picture counts as text-heavy.

    Tuned by eye against the synthetic corpus, not optimised. It is recorded as
    a single named threshold so it is obvious what to change.
    """
    return 40


def report(decisions: list[RoutingDecision], settings: Settings) -> None:
    rows = [
        [
            d.docling_class,
            f"{d.docling_confidence:.2f}" if d.docling_confidence is not None else "-",
            str(d.ocr_characters),
            d.route.value,
            d.reason,
        ]
        for d in decisions
    ]
    rep.kv("routing table", "")
    rep.table(rows, ["docling class", "conf", "chars", "route", "reason"])
