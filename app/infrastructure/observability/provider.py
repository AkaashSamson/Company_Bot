"""
Observability Provider Contracts and Implementations.

Exports:
- TokenUsage: Value object for token consumption tracking.
- TraceSpanPort: Protocol for individual trace spans.
- BaseObservabilityProvider: Protocol for observability providers.
- NullObservabilityProvider: Default no-op provider for local dev / tests.
"""

from app.domain.ports.observability import (
    BaseObservabilityProvider,
    ObservabilityPort,
    TokenUsage,
    TraceSpanPort,
)
from app.infrastructure.observability.null_provider import (
    NullObservabilityProvider,
    NullSpan,
)

__all__ = [
    "BaseObservabilityProvider",
    "ObservabilityPort",
    "TokenUsage",
    "TraceSpanPort",
    "NullObservabilityProvider",
    "NullSpan",
]
