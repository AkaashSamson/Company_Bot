"""Real-model smoke test for Qwen2-VL-2B-Instruct.

Runs actual inference with the cached model weights on CPU to verify that the
complete multimodal path (processor, tokenization, forward pass, and contract parsing)
executes end-to-end without errors.
"""

import os
import pytest
from PIL import Image, ImageDraw
from io import BytesIO

from app.infrastructure.document.vlm_engine import Qwen2VLEngine
from app.domain.ports.visual_contract import VisualOutputContract


def _create_synthetic_architecture_diagram() -> bytes:
    """Create a synthetic diagram with labeled boxes and an arrow."""
    img = Image.new("RGB", (400, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Box 1: Ingestion
    draw.rectangle([20, 50, 150, 150], outline=(0, 0, 0), width=2, fill=(230, 240, 255))
    draw.text((40, 90), "Ingestion API", fill=(0, 0, 0))

    # Box 2: ChromaDB
    draw.rectangle([250, 50, 380, 150], outline=(0, 0, 0), width=2, fill=(230, 255, 230))
    draw.text((270, 90), "Chroma VectorStore", fill=(0, 0, 0))

    # Arrow connecting them
    draw.line([(150, 100), (250, 100)], fill=(0, 0, 0), width=3)
    draw.polygon([(250, 100), (240, 95), (240, 105)], fill=(0, 0, 0))
    draw.text((170, 80), "store", fill=(100, 100, 100))

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.integration
def test_qwen2_vl_real_model_smoke():
    """Verify that Qwen2-VL-2B executes real CPU inference on a synthetic diagram."""
    image_bytes = _create_synthetic_architecture_diagram()
    engine = Qwen2VLEngine(
        model_name="qwen2-vl:2b",
        max_new_tokens=100,
    )

    contract = engine.describe(
        image_bytes=image_bytes,
        ocr_context="Ingestion API, Chroma VectorStore, store",
        picture_ref="#/pictures/smoke_0",
    )

    assert isinstance(contract, VisualOutputContract)
    assert contract.source_reference == "#/pictures/smoke_0"
    assert contract.summary != ""
    assert isinstance(contract.entities, list)
    assert isinstance(contract.relationships, list)
    # Search text formatting check
    search_text = contract.to_search_text()
    assert len(search_text) > 10
