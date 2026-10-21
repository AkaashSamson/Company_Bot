"""Picture OCR, routing, and local visual understanding (Qwen2-VL) enrichment for Docling documents."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from docling.datamodel.base_models import DocumentStream, InputFormat, ItemAndImageEnrichmentElement
from docling.datamodel.pipeline_options import EasyOcrOptions, OcrMode, PdfPipelineOptions
from docling.document_converter import DocumentConverter, ImageFormatOption
from docling_core.types.doc import PictureItem

from app.core.settings import (
    DOCLING_OCR_MIN_CONFIDENCE,
    DOCLING_SKIP_DECORATIVE_OCR,
    DOCLING_VLM_MAX_NEW_TOKENS,
    DOCLING_VLM_MODEL,
)
from app.domain.ports.document_processing import ProcessedChunk, SectionHeading
from app.domain.ports.visual_contract import VisualOutputContract
from app.infrastructure.document.vlm_engine import VisualUnderstandingEngine
from app.infrastructure.document.vlm_factory import get_vlm_engine

logger = logging.getLogger("knowlayer.ingestion.visual")

CHART_LABELS = {
    "bar_chart", "line_chart", "pie_chart", "other_chart", "scatter_plot",
    "scatter_chart", "stacked_bar_chart", "box_plot", "heatmap",
}
DIAGRAM_LABELS = {
    "flow_chart", "electrical_diagram", "engineering_drawing", "cad_drawing",
}
SCREENSHOT_LABELS = {"screenshot", "screenshot_from_computer", "screenshot_from_manual"}
DECORATIVE_LABELS = {
    "logo", "icon", "bar_code", "qr_code", "stamp", "signature",
    "page_thumbnail", "natural_image", "photograph", "other",
}
TEXTUAL_LABELS = {"table"}


@dataclass(slots=True)
class PictureFacts:
    ref: str
    image_bytes: bytes
    page_number: int | None
    section_path: tuple[SectionHeading, ...]
    classifications: tuple[tuple[str, float], ...]

    @property
    def top_class(self) -> tuple[str, float] | None:
        return self.classifications[0] if self.classifications else None


class VisualEnricher:
    """Enrich pictures without exposing Docling objects outside infrastructure."""

    def __init__(
        self,
        model_name: str = DOCLING_VLM_MODEL,
        vlm_engine: VisualUnderstandingEngine | None = None,
    ):
        self._model_name = model_name
        self._vlm_engine = vlm_engine
        self._classifier: Any | None = None
        self._ocr_converter: DocumentConverter | None = None

    @property
    def vlm_engine(self) -> VisualUnderstandingEngine:
        """Lazily resolve the visual understanding engine."""
        if self._vlm_engine is None:
            self._vlm_engine = get_vlm_engine(self._model_name)
        return self._vlm_engine

    def enrich(
        self,
        document: Any,
        facts: dict[str, Any],
        starting_index: int,
    ) -> tuple[ProcessedChunk, ...]:
        pictures = self._pictures(document, facts)
        if not pictures:
            return ()
        self._classify(document, pictures)
        output: list[ProcessedChunk] = []
        for picture in pictures:
            label = self._label(picture)
            if DOCLING_SKIP_DECORATIVE_OCR and label in DECORATIVE_LABELS:
                logger.info("skipping OCR for decorative picture %s (%s)", picture.ref, label)
                continue

            ocr_text = self._ocr(picture)
            route = self._route(label, ocr_text)
            if ocr_text and route in {"OCR", "OCR+VLM"}:
                output.append(self._chunk(
                    text=ocr_text,
                    index=starting_index + len(output),
                    picture=picture,
                    route=route,
                    produced_by="docling+easyocr",
                    verified=False,
                    review_required=False,
                    extra={"ocr_characters": len(ocr_text)},
                ))

            if route in {"VLM", "OCR+VLM"}:
                contract = self._describe(
                    picture.image_bytes,
                    ocr_context=ocr_text,
                    picture_ref=picture.ref,
                )
                search_text = (
                    contract.to_search_text()
                    if isinstance(contract, VisualOutputContract)
                    else str(contract).strip()
                )
                if search_text:
                    produced_by = "qwen2-vl"
                    metadata_extra: dict[str, Any] = {"model": self._model_name}
                    if isinstance(contract, VisualOutputContract):
                        metadata_extra.update(contract.to_metadata())

                    output.append(self._chunk(
                        text=search_text,
                        index=starting_index + len(output),
                        picture=picture,
                        route=route,
                        produced_by=produced_by,
                        verified=False,
                        review_required=True,
                        extra=metadata_extra,
                    ))
        return tuple(output)

    @staticmethod
    def _pictures(document: Any, facts: dict[str, Any]) -> list[PictureFacts]:
        pictures: list[PictureFacts] = []
        for item, _level in document.iterate_items():
            if getattr(getattr(item, "label", None), "value", getattr(item, "label", "")) != "picture":
                continue
            image = item.get_image(document)
            reference = str(getattr(item, "self_ref", ""))
            if image is None or not reference:
                continue
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            item_fact = facts.get(reference)
            pictures.append(
                PictureFacts(
                    ref=reference,
                    image_bytes=buffer.getvalue(),
                    page_number=getattr(item_fact, "page_no", None),
                    section_path=tuple(getattr(item_fact, "section_path", ()) or ()),
                    classifications=tuple(VisualEnricher._classifications(item)),
                )
            )
        return pictures

    def _classify(self, document: Any, pictures: list[PictureFacts]) -> None:
        unclassified = [picture for picture in pictures if not picture.classifications]
        if not unclassified:
            return
        try:
            if self._classifier is None:
                from docling.datamodel.accelerator_options import AcceleratorOptions
                from docling.models.stages.picture_classifier.document_picture_classifier import (
                    DocumentPictureClassifier,
                )

                self._classifier = DocumentPictureClassifier(
                    enabled=True,
                    artifacts_path=None,
                    options=PdfPipelineOptions().picture_classification_options,
                    accelerator_options=AcceleratorOptions(),
                )
            items = []
            for item, _level in document.iterate_items():
                reference = str(getattr(item, "self_ref", ""))
                if reference in {picture.ref for picture in unclassified}:
                    items.append(ItemAndImageEnrichmentElement(item=item, image=item.get_image(document)))
            list(self._classifier(doc=document, element_batch=items))
            for picture in unclassified:
                picture.classifications = tuple(
                    self._classifications(next(item for item, _ in document.iterate_items() if str(getattr(item, "self_ref", "")) == picture.ref))
                )
        except Exception:
            logger.exception("Docling picture classification failed")

    @staticmethod
    def _classifications(picture: PictureItem) -> list[tuple[str, float]]:
        found: list[tuple[str, float]] = []
        for annotation in getattr(picture, "annotations", None) or []:
            if getattr(annotation, "kind", "") != "classification":
                continue
            for predicted in getattr(annotation, "predicted_classes", None) or []:
                name = str(getattr(predicted, "class_name", "")).strip().lower()
                if name:
                    found.append((name, float(getattr(predicted, "confidence", 0.0) or 0.0)))
        return sorted(found, key=lambda pair: pair[1], reverse=True)

    @staticmethod
    def _label(picture: PictureFacts) -> str:
        return (picture.top_class[0] if picture.top_class else "").replace(" ", "_").replace("-", "_")

    def _ocr(self, picture: PictureFacts) -> str:
        if self._ocr_converter is None:
            options = PdfPipelineOptions()
            options.do_table_structure = False
            options.do_picture_classification = False
            options.do_picture_description = False
            options.do_ocr = True
            options.ocr_options = EasyOcrOptions(
                mode=OcrMode.FULL_PAGE,
                lang=["en"],
                scale=2.0,
                use_gpu=False,
                confidence_threshold=DOCLING_OCR_MIN_CONFIDENCE,
            )
            self._ocr_converter = DocumentConverter(
                format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=options)}
            )
        try:
            result = self._ocr_converter.convert(
                DocumentStream(name=f"{picture.ref}.png", stream=BytesIO(picture.image_bytes))
            )
            return "\n".join(
                text
                for item in result.document.texts
                if (text := (getattr(item, "text", "") or "").strip())
            )
        except Exception:
            logger.exception("picture OCR failed for %s", picture.ref)
            return ""

    @staticmethod
    def _route(label: str, ocr_text: str) -> str:
        if label in DECORATIVE_LABELS:
            return "IGNORE"
        if label in CHART_LABELS or label in DIAGRAM_LABELS:
            return "OCR+VLM"
        if label in TEXTUAL_LABELS or label in SCREENSHOT_LABELS:
            return "OCR+VLM"
        if ocr_text:
            return "OCR+VLM"
        return "VLM"

    def _describe(
        self,
        image_bytes: bytes,
        ocr_context: str = "",
        picture_ref: str = "",
    ) -> VisualOutputContract:
        """Describe visual content using the configured visual understanding engine."""
        return self.vlm_engine.describe(
            image_bytes=image_bytes,
            ocr_context=ocr_context,
            picture_ref=picture_ref,
        )

    @staticmethod
    def _chunk(
        *, text: str, index: int, picture: PictureFacts, route: str,
        produced_by: str, verified: bool, review_required: bool,
        extra: dict[str, Any],
    ) -> ProcessedChunk:
        metadata = {
            "produced_by": produced_by,
            "verified": verified,
            "review_required": review_required,
            "picture_ref": picture.ref,
            "routing": route,
            "docling_class": picture.top_class[0] if picture.top_class else "unclassified",
            **extra,
        }
        return ProcessedChunk(
            text=text,
            index=index,
            page_number=picture.page_number,
            section_path=picture.section_path,
            content_type="text",
            metadata=metadata,
        )
