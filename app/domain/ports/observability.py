from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class TokenUsage:
    """Standardized representation of token usage across any LLM provider."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if self.total_tokens == 0 and (self.prompt_tokens > 0 or self.completion_tokens > 0):
            # object.__setattr__ required because class is frozen
            object.__setattr__(self, "total_tokens", self.prompt_tokens + self.completion_tokens)


@runtime_checkable
class TraceSpanPort(Protocol):
    """Protocol for an individual trace span (timed sub-operation)."""

    def end(self, outputs: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
        """Complete the span, recording outputs or error details."""
        ...

    def __enter__(self) -> "TraceSpanPort":
        ...

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        ...


@runtime_checkable
class BaseObservabilityProvider(Protocol):
    """Vendor-neutral observability port for tracing and token/cost tracking."""

    def export_pipeline_trace(self, trace: Any) -> None:
        """Convert and export a complete domain PipelineTrace with child spans."""
        ...

    def create_trace(
        self,
        name: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TraceSpanPort:
        """Start a new root trace or child span."""
        ...

    def record_llm_call(
        self,
        model: str,
        token_usage: TokenUsage,
        latency_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log token consumption and latency for an LLM generation call."""
        ...

    def flush(self) -> None:
        """Ensure all buffered events are sent to the external observability platform."""
        ...


# Type alias for Hexagonal naming consistency
ObservabilityPort = BaseObservabilityProvider
