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
from app.infrastructure.observability.langfuse_provider import (
    LangfuseProvider,
    LangfuseSpan,
)
from app.infrastructure.observability.manager import (
    ObservabilityManager,
    get_observability_manager,
    reset_observability_manager,
)
from app.infrastructure.observability.null_provider import (
    NullObservabilityProvider,
    NullSpan,
)
from app.infrastructure.observability.phoenix_provider import (
    PhoenixProvider,
    PhoenixSpan,
)

__all__ = [
    "BaseObservabilityProvider",
    "ObservabilityPort",
    "TokenUsage",
    "TraceSpanPort",
    "NullObservabilityProvider",
    "NullSpan",
    "LangfuseProvider",
    "LangfuseSpan",
    "PhoenixProvider",
    "PhoenixSpan",
    "ObservabilityManager",
    "get_observability_manager",
    "reset_observability_manager",
]
