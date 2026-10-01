"""Stage 3 -- describe meaningful visual content with a lightweight VLM.

This is the part where OCR genuinely is not enough. A flow chart and a bar
chart are full of words, but the words do not say what the picture *means*: the
arrows carry the process and the bar heights carry the trend.

Design rules this module follows:

* **Isolated.** The rest of the POC only ever sees :class:`VlmResult`. Swapping
  the model, the vendor or local-vs-API is a one-line change in
  :func:`build_vlm` and touches nothing else.
* **No hard-coded secrets.** The API backend reads its key from the
  environment and refuses to run without one.
* **Retrieval-oriented, not creative.** The prompt asks for labels,
  components, relationships, flow, order and values. It explicitly forbids
  embellishment, because this text gets embedded and then cited to a user.
* **Honest about provenance.** Every result records which model produced it, so
  model-written text is never mistaken for text that came from the document.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from . import reporting as rep
from .config import Settings
from .stage1_docling import ExtractedPicture, ParsedDocument

logger = logging.getLogger("poc.vlm")

#: Asked for retrieval-relevant facts, and told explicitly not to be creative.
#: The output is embedded and cited, so invented detail is a correctness bug.
SYSTEM_PROMPT = (
    "You describe technical figures for a document search index. "
    "Report only what is visibly present. "
    "Do not speculate, do not add context that is not in the image, and do not "
    "use decorative or creative language."
)

USER_PROMPT_TEMPLATE = """Describe this figure so that a text search over your answer can find it.

Include, where the figure shows them:
- the exact labels and components that appear
- the relationships between components, and the direction of any arrows or flows
- the sequence of steps, if it is a process or flow diagram
- the title, axis labels, categories and numeric values, if it is a chart
- any other text that is legibly visible

Answer in at most 120 words. Plain text. No preamble."""


@dataclass
class VlmResult:
    """What a VLM said about one picture."""

    source_document: str
    picture_ref: str
    page: int | None
    section: str
    model: str
    backend: str
    description: str
    duration_seconds: float
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.description.strip())


class VlmBackend(ABC):
    """The only interface the POC knows about a VLM."""

    name: str = "abstract"

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether this backend can actually run right now."""

    @abstractmethod
    def describe(self, image_bytes: bytes, prompt: str) -> str:
        ...

    def unavailable_reason(self) -> str:
        return "no reason reported"


class LocalSmolVlmBackend(VlmBackend):
    """SmolVLM-256M running on this machine.

    The privacy-safe default: the image bytes never leave the process, there is
    no API key, and no per-call cost. It is small enough to be genuinely
    lightweight, and small enough to be visibly weak -- which is exactly what
    this POC is trying to measure.
    """

    name = "local"

    def __init__(self, model_id: str):
        self.model_id = model_id
        self._processor = None
        self._model = None

    @property
    def available(self) -> bool:
        return True

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        rep.status("vlm", "OK", f"loading {self.model_id} (first run downloads it)")
        self._processor = AutoProcessor.from_pretrained(self.model_id)
        self._model = AutoModelForImageTextToText.from_pretrained(self.model_id, dtype=torch.float32)
        self._model.eval()

    def describe(self, image_bytes: bytes, prompt: str) -> str:
        import torch
        from PIL import Image
        from io import BytesIO

        self._ensure_loaded()
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"type": "text", "text": f"{SYSTEM_PROMPT}\n\n{prompt}"},
                ],
            }
        ]
        rendered = self._processor.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False
        )
        inputs = self._processor(text=rendered, images=[image], return_tensors="pt")
        with torch.no_grad():
            output = self._model.generate(**inputs, max_new_tokens=180, do_sample=False)
        trimmed = output[0][inputs["input_ids"].shape[1] :]
        return self._processor.decode(trimmed, skip_special_tokens=True).strip()


class GeminiBackend(VlmBackend):
    """Gemini via the REST API, for comparison against the local model.

    Only ever use this with the synthetic documents in ``input/``. The free tier
    may use submitted content for product improvement, which is not acceptable
    for real HR or policy material.
    """

    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def unavailable_reason(self) -> str:
        return "POC_GEMINI_API_KEY is not set"

    def describe(self, image_bytes: bytes, prompt: str) -> str:
        import requests

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {"maxOutputTokens": 300, "temperature": 0.0},
        }
        response = requests.post(url, json=payload, timeout=90)
        if response.status_code != 200:
            raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:300]}")
        data = response.json()
        return " ".join(
            part.get("text", "")
            for candidate in data.get("candidates", [])
            for part in candidate.get("content", {}).get("parts", [])
        ).strip()


def build_vlm(settings: Settings) -> VlmBackend:
    """Pick a backend. This is the only function that names a VLM."""
    backend = settings.vlm_backend.lower()
    if backend in {"gemini", "api"}:
        return GeminiBackend(settings.gemini_api_key, settings.gemini_model)
    return LocalSmolVlmBackend(settings.local_vlm_model)


def run_vlm(
    parsed: ParsedDocument,
    backend: VlmBackend,
    settings: Settings,
    pictures: list[ExtractedPicture],
) -> list[VlmResult]:
    """Describe the routed pictures of one document."""
    if not settings.enable_vlm:
        rep.status("vlm", "SKIP", "disabled by configuration")
        return []
    if not backend.available:
        rep.status("vlm", "SKIP", backend.unavailable_reason())
        return []
    if not pictures:
        rep.status("vlm", "SKIP", "nothing was routed to the VLM for this document")
        return []

    rep.kv("vlm backend", f"{backend.name} ({settings.local_vlm_model if backend.name == 'local' else settings.gemini_model})")

    results: list[VlmResult] = []
    for picture in pictures:
        started = time.perf_counter()
        try:
            description = backend.describe(picture.image_bytes, USER_PROMPT_TEMPLATE)
            error = None
        except Exception as exc:  # noqa: BLE001
            description, error = "", f"{type(exc).__name__}: {exc}"
        result = VlmResult(
            source_document=parsed.name,
            picture_ref=picture.ref,
            page=picture.page,
            section=picture.section,
            model=settings.local_vlm_model if backend.name == "local" else settings.gemini_model,
            backend=backend.name,
            description=description,
            duration_seconds=time.perf_counter() - started,
            error=error,
        )
        results.append(result)
        if error:
            rep.status("vlm", "FAIL", f"{picture.ref}: {error}")
            continue
        rep.element(
            index=picture.order,
            content_type="image_description",
            producer=f"vlm ({result.model})",
            source=result.source_document,
            page=result.page,
            section=result.section,
            text=result.description,
            limit=settings.preview_chars * 2,
            extra=[
                ("model", result.model),
                ("backend", result.backend),
                ("characters", len(result.description)),
                ("elapsed", f"{result.duration_seconds:.1f}s"),
            ],
        )
    return results
