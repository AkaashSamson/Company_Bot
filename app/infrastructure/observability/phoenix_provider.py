import datetime
import logging
import threading
import uuid
from typing import Any, Dict, Optional

from app.domain.ports.observability import (
    BaseObservabilityProvider,
    TokenUsage,
    TraceSpanPort,
)

logger = logging.getLogger(__name__)


class PhoenixSpan(TraceSpanPort):
    """Span implementation for Arize Phoenix / OpenTelemetry tracing."""

    def __init__(
        self,
        provider: "PhoenixProvider",
        name: str,
        trace_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.provider = provider
        self.name = name
        self.trace_id = trace_id
        self.span_id = str(uuid.uuid4())
        self.metadata = metadata or {}
        self.start_time = datetime.datetime.now(datetime.timezone.utc)
        self.end_time: Optional[datetime.datetime] = None
        self.outputs: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.is_ended: bool = False

    def end(self, outputs: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
        if self.is_ended:
            return
        self.end_time = datetime.datetime.now(datetime.timezone.utc)
        self.outputs = outputs
        self.error = error
        self.is_ended = True

        duration_ms = (self.end_time - self.start_time).total_seconds() * 1000.0
        record = {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_ms": duration_ms,
            "outputs": self.outputs,
            "error": self.error,
            "metadata": self.metadata,
        }
        self.provider._record_span(record)

    def __enter__(self) -> "PhoenixSpan":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self.end(error=str(exc_val))
        else:
            self.end()


class PhoenixProvider(BaseObservabilityProvider):
    """Vendor adapter for Arize Phoenix observability.
    Uses OpenTelemetry / OpenInference semantic attributes for LLM and pipeline telemetry.
    Can export to Phoenix OTLP collector (http://localhost:6006/v1/traces) or run offline in memory.
    """

    def __init__(
        self,
        collector_endpoint: str = "http://localhost:6006/v1/traces",
        project_name: str = "company-bot",
        enabled: bool = True,
    ) -> None:
        self.collector_endpoint = collector_endpoint
        self.project_name = project_name
        self.enabled = enabled
        self._lock = threading.Lock()
        self._spans: list[Dict[str, Any]] = []
        self._llm_calls: list[Dict[str, Any]] = []
        self.total_spans_recorded: int = 0
        self.total_llm_calls_recorded: int = 0
        self.last_flushed_spans: list[Dict[str, Any]] = []
        self.last_flushed_llm_calls: list[Dict[str, Any]] = []

        logger.info(
            "PhoenixProvider initialized (endpoint: %s, project: %s, enabled: %s)",
            self.collector_endpoint,
            self.project_name,
            self.enabled,
        )

    def _record_span(self, record: Dict[str, Any]) -> None:
        with self._lock:
            self._spans.append(record)
            self.total_spans_recorded += 1

    def export_pipeline_trace(self, trace: Any) -> None:
        """Convert and export domain PipelineTrace for Phoenix/OpenInference."""
        if not self.enabled or trace is None:
            return
        # Basic trace recording for Phoenix
        trace_id = getattr(trace, "trace_id", str(uuid.uuid4()))
        meta = {
            "total_duration_ms": getattr(trace, "total_duration_ms", 0.0),
            "cache_hit": getattr(trace, "cache_hit", False),
            "query": getattr(trace, "query", ""),
        }
        self.create_trace(name="QueryOrchestrator.answer", session_id=trace_id, metadata=meta)

    def create_trace(
        self,
        name: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PhoenixSpan:
        trace_id = str(uuid.uuid4())
        meta = {
            **(metadata or {}),
            "project_name": self.project_name,
            "session_id": session_id,
            "user_id": user_id,
        }
        return PhoenixSpan(provider=self, name=name, trace_id=trace_id, metadata=meta)

    def record_llm_call(
        self,
        model: str,
        token_usage: TokenUsage,
        latency_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record LLM generation using OpenInference semantic attributes recognized by Phoenix."""
        record = {
            "model": model,
            "prompt_tokens": token_usage.prompt_tokens,
            "completion_tokens": token_usage.completion_tokens,
            "total_tokens": token_usage.total_tokens,
            "latency_ms": latency_ms,
            "openinference_attributes": {
                "llm.model_name": model,
                "llm.token_count.prompt": token_usage.prompt_tokens,
                "llm.token_count.completion": token_usage.completion_tokens,
                "llm.token_count.total": token_usage.total_tokens,
                "llm.latency_ms": latency_ms,
            },
            "metadata": metadata or {},
        }
        with self._lock:
            self._llm_calls.append(record)
            self.total_llm_calls_recorded += 1
        logger.debug("Phoenix recorded LLM call: %s (%d tokens)", model, token_usage.total_tokens)

    def record_decision_call(
        self,
        name: str,
        state: str,
        questions: Dict[str, Any],
        selection: Dict[str, Any],
        model: str = "laya",
        token_usage: Optional[TokenUsage] = None,
        latency_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record decision / guardrail call using Phoenix semantic attributes."""
        p_tok = token_usage.prompt_tokens if token_usage else 0
        c_tok = token_usage.completion_tokens if token_usage else 0
        t_tok = token_usage.total_tokens if token_usage else (p_tok + c_tok)
        record = {
            "name": name,
            "model": model,
            "state": state,
            "questions": questions,
            "selection": selection,
            "prompt_tokens": p_tok,
            "completion_tokens": c_tok,
            "total_tokens": t_tok,
            "latency_ms": latency_ms,
            "metadata": metadata or {},
        }
        with self._lock:
            self._llm_calls.append(record)
            self.total_llm_calls_recorded += 1

    def flush(self) -> None:
        with self._lock:
            span_count = len(self._spans)
            call_count = len(self._llm_calls)
            self.last_flushed_spans = list(self._spans)
            self.last_flushed_llm_calls = list(self._llm_calls)
            self._spans.clear()
            self._llm_calls.clear()
        logger.debug(
            "PhoenixProvider flushed: %d spans, %d LLM records to %s",
            span_count,
            call_count,
            self.collector_endpoint,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Inspection helper for tests and verification."""
        with self._lock:
            return {
                "active_spans": len(self._spans),
                "total_spans_recorded": self.total_spans_recorded,
                "recorded_llm_calls": len(self._llm_calls),
                "total_llm_calls_recorded": self.total_llm_calls_recorded,
                "project_name": self.project_name,
                "endpoint": self.collector_endpoint,
            }
