from typing import Any, Dict, Optional

from app.domain.ports.observability import (
    BaseObservabilityProvider,
    TokenUsage,
    TraceSpanPort,
)


class NullSpan(TraceSpanPort):
    """Safe no-op span implementation for tests and offline execution."""

    def __init__(self, name: str = "noop") -> None:
        self.name = name
        self.outputs: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.is_ended: bool = False

    def end(self, outputs: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
        self.outputs = outputs
        self.error = error
        self.is_ended = True

    def __enter__(self) -> "NullSpan":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self.end(error=str(exc_val))
        else:
            self.end()


class NullObservabilityProvider(BaseObservabilityProvider):
    """Default no-op observability provider.
    Guarantees zero network calls and zero crashes when telemetry is disabled or in unit tests.
    """

    def export_pipeline_trace(self, trace: Any) -> None:
        """No-op export for offline / null provider."""
        pass

    def create_trace(
        self,
        name: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> NullSpan:
        return NullSpan(name=name)

    def record_llm_call(
        self,
        model: str,
        token_usage: TokenUsage,
        latency_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        pass

    def flush(self) -> None:
        pass
