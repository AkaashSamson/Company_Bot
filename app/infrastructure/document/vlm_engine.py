"""Dedicated Visual Understanding Engine abstraction and implementations.

Provides:
- VisualUnderstandingEngine: Abstract base interface
- OllamaQwen2VLEngine: Production-grade 8-bit quantized Qwen2-VL engine via Ollama
- Qwen2VLEngine: Backward-compatible alias for OllamaQwen2VLEngine
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time
from abc import ABC, abstractmethod
from io import BytesIO
from typing import Any

import httpx

from app.core.settings import (
    DOCLING_VLM_BASE_URL,
    DOCLING_VLM_MAX_NEW_TOKENS,
    DOCLING_VLM_MODEL,
    DOCLING_VLM_TIMEOUT_SECONDS,
)
from app.domain.ports.visual_contract import VisualOutputContract
from app.infrastructure.document.image_normalizer import (
    guard_max_dimension,
    normalize_alpha_to_white,
)

logger = logging.getLogger("knowlayer.ingestion.vlm")


class VisualUnderstandingEngine(ABC):
    """Abstract visual understanding engine contract."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Identifier of the underlying visual model."""

    @property
    @abstractmethod
    def device(self) -> str:
        """Execution device (cpu, cuda, ollama)."""

    @abstractmethod
    def describe(
        self,
        image_bytes: bytes,
        ocr_context: str = "",
        picture_ref: str = "",
    ) -> VisualOutputContract:
        """Analyze an image and return structured visual facts."""


class OllamaQwen2VLEngine(VisualUnderstandingEngine):
    """Production-grade VLM engine backed by decoupled Ollama running 8-bit Qwen2-VL.

    Optimizations:
    - Zero local compilation or PyTorch VLM memory bloat (~2.4 GB GGUF Q8_0).
    - Offloaded CPU SIMD inference (AVX2/AVX-512) managed by Ollama daemon.
    - Dynamic memory management: weights auto-unload when idle via Ollama keep_alive.
    - Fault-isolated: C++ crashes or OOMs do not terminate the FastAPI application.
    - Validates image bytes with PIL before dispatching over the wire.
    - Structured contract parsing with robust bounded JSON recovery.
    """

    _lock = threading.Lock()

    def __init__(
        self,
        base_url: str = DOCLING_VLM_BASE_URL,
        model_name: str = DOCLING_VLM_MODEL,
        timeout_seconds: float = DOCLING_VLM_TIMEOUT_SECONDS,
        max_new_tokens: int = DOCLING_VLM_MAX_NEW_TOKENS,
        **kwargs: Any,
    ):
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._max_new_tokens = max_new_tokens
        self._client: httpx.Client | None = None
        self._init_lock = threading.Lock()

    @property
    def model_id(self) -> str:
        return self._model_name

    @property
    def device(self) -> str:
        return "ollama"

    @property
    def base_url(self) -> str:
        return self._base_url

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            with self._init_lock:
                if self._client is None:
                    self._client = httpx.Client(timeout=self._timeout_seconds)
        return self._client

    def describe(
        self,
        image_bytes: bytes,
        ocr_context: str = "",
        picture_ref: str = "",
    ) -> VisualOutputContract:
        """Execute structured visual analysis on image bytes via Ollama."""
        if not image_bytes:
            return VisualOutputContract(
                visual_type="other",
                summary="Empty or missing image bytes",
                source_reference=picture_ref,
                uncertain_items=["image_empty"],
            )

        from PIL import Image

        # Validate image format locally before network transmission
        try:
            image = Image.open(BytesIO(image_bytes))
            image.verify()
        except Exception as error:
            logger.warning("invalid image bytes for ref=%s: %s", picture_ref, error)
            return VisualOutputContract(
                visual_type="other",
                summary="Invalid image data",
                source_reference=picture_ref,
                uncertain_items=["image_corrupt_or_unsupported"],
            )

        # Normalize alpha channel to white matte and guard maximum resolution to 1024px
        try:
            image_bytes, _ = normalize_alpha_to_white(image_bytes)
            image_bytes, _ = guard_max_dimension(image_bytes, max_dim=1024)
        except Exception as norm_err:
            logger.warning(
                "image normalization failed for ref=%s: %s; using original bytes",
                picture_ref,
                norm_err,
            )

        system_instruction = (
            "You are a factual technical visual analyzer. "
            "Describe the diagram, chart, or image factually and concisely in 2 to 3 sentences. "
            "State what type of visual it is (e.g. architecture diagram, flowchart, chart, screenshot), "
            "the core components or services, and the key relationships, data flows, or labels. "
            "Do not output markdown code blocks, JSON, or conversational filler. Return plain text only."
        )

        prompt_text = "Provide a concise factual description of this visual asset."
        if ocr_context:
            truncated_ocr = ocr_context[:300].strip()
            prompt_text += f" Context: [{truncated_ocr}]."

        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt_text, "images": [b64_image]},
            ],
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": self._max_new_tokens,
            },
        }

        client = self._get_client()
        t_start = time.perf_counter()
        try:
            with self._lock:
                response = client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            raw_output = data.get("message", {}).get("content", "").strip()
            eval_count = data.get("eval_count", 0)
            infer_time = time.perf_counter() - t_start
            tok_s = eval_count / infer_time if infer_time > 0 and eval_count > 0 else 0.0

            logger.info(
                "Ollama Qwen2-VL inference complete [ref=%s, time=%.2fs, tokens=%d, tok/s=%.1f]",
                picture_ref,
                infer_time,
                eval_count,
                tok_s,
            )
            return self._parse_contract(raw_output, picture_ref)
        except Exception as exc:
            logger.warning(
                "Ollama Qwen2-VL inference failed for ref=%s: %s; returning safe fallback",
                picture_ref,
                exc,
            )
            return VisualOutputContract(
                visual_type="other",
                summary="Visual analysis unavailable due to service error",
                source_reference=picture_ref,
                uncertain_items=["vlm_service_unavailable"],
            )

    @staticmethod
    def _infer_visual_type(text: str) -> str:
        """Infer visual category from natural language summary text."""
        lower = text.lower()
        if any(k in lower for k in ("architecture", "system diagram", "component diagram", "network topology", "infrastructure")):
            return "architecture_diagram"
        if any(k in lower for k in ("flowchart", "flow chart", "workflow", "process flow", "sequence diagram", "decision tree")):
            return "flowchart"
        if any(k in lower for k in ("chart", "graph", "plot", "histogram", "pie chart", "bar chart", "line graph", "scatter")):
            return "chart"
        if any(k in lower for k in ("screenshot", "screen shot", "user interface", "ui mockup", "web page", "app window")):
            return "screenshot"
        if any(k in lower for k in ("table", "tabular", "spreadsheet", "matrix", "grid")):
            return "table"
        return "other"

    @classmethod
    def _parse_contract(cls, raw_text: str, picture_ref: str) -> VisualOutputContract:
        """Parse raw model output into VisualOutputContract.

        Supports both concise natural language summaries (Option 2) and
        structured JSON contracts (legacy/explicit format), with bounded
        recovery for malformed responses.
        """
        if not raw_text or not raw_text.strip():
            return VisualOutputContract(
                visual_type="other",
                summary="Visual element produced no description.",
                source_reference=picture_ref,
            )

        cleaned = raw_text.strip()

        # Check if the text is attempted JSON
        is_attempted_json = (
            "not valid json" in cleaned.lower()
            or cleaned.startswith("{")
            or "```json" in cleaned
            or ('"visual_type"' in cleaned and '"summary"' in cleaned)
        )

        # If it looks like JSON or markdown-fenced JSON, try parsing JSON first
        json_target = cleaned
        if "```" in json_target:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", json_target)
            if match:
                json_target = match.group(1).strip()

        start_brace = json_target.find("{")
        end_brace = json_target.rfind("}")
        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            try:
                candidate = json_target[start_brace : end_brace + 1]
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return VisualOutputContract(
                        visual_type=str(data.get("visual_type", "other")).strip().lower(),
                        summary=str(data.get("summary", "")).strip(),
                        entities=[
                            str(e).strip()
                            for e in data.get("entities", [])
                            if str(e).strip()
                        ],
                        relationships=[
                            str(r).strip()
                            for r in data.get("relationships", [])
                            if str(r).strip()
                        ],
                        visible_text=[
                            str(t).strip()
                            for t in data.get("visible_text", [])
                            if str(t).strip()
                        ],
                        uncertain_items=[
                            str(u).strip()
                            for u in data.get("uncertain_items", [])
                            if str(u).strip()
                        ],
                        source_reference=picture_ref,
                    )
            except Exception as json_err:
                logger.debug(
                    "JSON parse failed on candidate JSON (%s)",
                    json_err,
                )

        # If JSON was attempted but failed/corrupt, bounded recovery preserves safety
        if is_attempted_json:
            first_sentence = raw_text.split("\n")[0][:250].strip()
            return VisualOutputContract(
                visual_type="other",
                summary=first_sentence or raw_text[:250].strip(),
                source_reference=picture_ref,
                uncertain_items=["unstructured_vlm_output"],
            )

        # Natural language summary path (Option 2: concise plain text)
        clean_text = re.sub(r"^```(?:[a-zA-Z]+)?\s*", "", cleaned)
        clean_text = re.sub(r"\s*```$", "", clean_text).strip()
        visual_type = cls._infer_visual_type(clean_text)

        return VisualOutputContract(
            visual_type=visual_type,
            summary=clean_text[:1000].strip(),
            source_reference=picture_ref,
        )


class Qwen2VLEngine(OllamaQwen2VLEngine):
    """Qwen2-VL visual understanding engine powered by Ollama GGUF.

    Maintains full backward compatibility for existing callers and tests.
    """

    def __init__(
        self,
        model_id: str | None = None,
        base_url: str = DOCLING_VLM_BASE_URL,
        model_name: str | None = None,
        timeout_seconds: float = DOCLING_VLM_TIMEOUT_SECONDS,
        device: str = "cpu",
        **kwargs: Any,
    ):
        chosen_model = model_name or model_id or DOCLING_VLM_MODEL
        super().__init__(
            base_url=base_url,
            model_name=chosen_model,
            timeout_seconds=timeout_seconds,
            **kwargs,
        )
        self._legacy_device = device

    @property
    def device(self) -> str:
        return self._legacy_device or "ollama"
