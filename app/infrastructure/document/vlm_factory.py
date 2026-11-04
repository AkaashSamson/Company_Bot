"""Factory for visual understanding engines.

Provides lazy construction and instance caching so models are not loaded
on module import and multiple instances are not created.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.core.settings import DOCLING_VLM_MODEL
from app.infrastructure.document.vlm_engine import (
    OllamaQwen2VLEngine,
    Qwen2VLEngine,
    VisualUnderstandingEngine,
)

logger = logging.getLogger("knowlayer.ingestion.vlm")

_ENGINE_CACHE: dict[str, VisualUnderstandingEngine] = {}
_FACTORY_LOCK = threading.Lock()


def get_vlm_engine(model_name: str | None = None) -> VisualUnderstandingEngine:
    """Obtain or lazily instantiate the configured VLM engine.

    Reuses existing cached engine instance so weights are resident in RAM
    and never loaded multiple times.
    """
    model_id = model_name or DOCLING_VLM_MODEL
    with _FACTORY_LOCK:
        if model_id in _ENGINE_CACHE:
            return _ENGINE_CACHE[model_id]

        logger.info("building Ollama Qwen2-VL engine for model=%s", model_id)
        engine = Qwen2VLEngine(model_id=model_id)

        _ENGINE_CACHE[model_id] = engine
        return engine


def clear_vlm_engine_cache() -> None:
    """Clear cached engine instances (primarily for tests)."""
    with _FACTORY_LOCK:
        _ENGINE_CACHE.clear()
