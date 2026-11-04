"""Picture OCR, routing, and local visual understanding (Qwen2-VL) enrichment for Docling documents."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from docling.datamodel.base_models import ItemAndImageEnrichmentElement
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling_core.types.doc import PictureItem

from app.core.settings import (
    DOCLING_SKIP_BLANK_PAGES,
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
        candidates = []
        for picture in pictures:
            label = self._label(picture)
            if DOCLING_SKIP_DECORATIVE_OCR and label in DECORATIVE_LABELS:
                logger.info("skipping decorative picture %s (%s)", picture.ref, label)
                continue

            # Skip blank or empty images (e.g. scanner duplex blanks)
            if DOCLING_SKIP_BLANK_PAGES and picture.image_bytes:
                try:
                    from app.infrastructure.document.image_normalizer import is_blank_page
                    if is_blank_page(picture.image_bytes):
                        logger.info("skipping blank picture %s", picture.ref)
                        continue
                except Exception:
                    pass

            # Skip small decorative images/icons (< 150x150 px)
            if DOCLING_SKIP_DECORATIVE_OCR and picture.image_bytes:
                try:
                    from PIL import Image
                    with Image.open(BytesIO(picture.image_bytes)) as pil_img:
                        if pil_img.width < 150 and pil_img.height < 150:
                            logger.info(
                                "skipping small decorative image %s (%dx%d)",
                                picture.ref,
                                pil_img.width,
                                pil_img.height,
                            )
                            continue
                except Exception:
                    pass

            route = self._route(label)
            if route == "IGNORE":
                continue

            candidates.append((picture, route))

        if not candidates:
            return ()

        # Parallelize VLM description across threads if multiple candidates exist
        import concurrent.futures
        descriptions: dict[str, Any] = {}
        if len(candidates) > 1:
            max_workers = min(3, len(candidates))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(self._describe, pic.image_bytes, picture_ref=pic.ref): pic.ref
                    for pic, _ in candidates
                }
                for future in concurrent.futures.as_completed(future_map):
                    ref = future_map[future]
                    try:
                        descriptions[ref] = future.result()
                    except Exception as err:
                        logger.warning("VLM description failed for %s: %s", ref, err)
                        descriptions[ref] = None
        else:
            pic, _ = candidates[0]
            try:
                descriptions[pic.ref] = self._describe(pic.image_bytes, picture_ref=pic.ref)
            except Exception as err:
                logger.warning("VLM description failed for %s: %s", pic.ref, err)
                descriptions[pic.ref] = None

        # Assemble chunks in deterministic order
        output: list[ProcessedChunk] = []
        for picture, route in candidates:
            contract = descriptions.get(picture.ref)
            if not contract:
                continue

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
        """Deprecated: OCR is handled natively and exhaustively by Qwen2-VL."""
        logger.debug("VisualEnricher._ocr is deprecated; OCR is now integrated into Qwen2-VL")
        return ""

    @staticmethod
    def _route(label: str, ocr_text: str = "") -> str:
        """Determine routing for an image. All non-decorative images route directly to VLM."""
        if label in DECORATIVE_LABELS:
            return "IGNORE"
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
