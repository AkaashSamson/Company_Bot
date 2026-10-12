"""
Unified Tracing Integration Facade.

Backwards-compatibility facade re-exporting loosely coupled tracing components
from pipeline_tracer.py.
"""

from app.infrastructure.observability.pipeline_tracer import (
    _NoOpSpan,
    _is_langfuse_active,
    _sanitize_inputs,
    _sanitize_output,
    trace_step,
    traceable,
)

__all__ = [
    "_NoOpSpan",
    "_is_langfuse_active",
    "_sanitize_inputs",
    "_sanitize_output",
    "trace_step",
    "traceable",
]
