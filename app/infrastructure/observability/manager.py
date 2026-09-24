import logging
import threading
from typing import Any, Dict, Optional

from app.core import settings
from app.domain.ports.observability import (
    BaseObservabilityProvider,
    ObservabilityPort,
    TokenUsage,
    TraceSpanPort,
)
from app.infrastructure.observability.langfuse_provider import LangfuseProvider
from app.infrastructure.observability.null_provider import NullObservabilityProvider
from app.infrastructure.observability.phoenix_provider import PhoenixProvider

logger = logging.getLogger(__name__)


class ObservabilityManager(BaseObservabilityProvider):
    """Central router and dispatcher for application observability.
    
    Implements BaseObservabilityProvider (Proxy / Facade pattern).
    Routes calls to the currently active infrastructure provider (Langfuse, Phoenix, Null).
    Allows dynamic runtime switching between observability backends without code modifications.
    """

    def __init__(self, provider: Optional[BaseObservabilityProvider] = None) -> None:
        self._lock = threading.Lock()
        if provider is not None:
            self._active_provider = provider
        else:
            self._active_provider = self._build_default_provider()

    @staticmethod
    def _build_default_provider() -> BaseObservabilityProvider:
        provider_name = getattr(settings, "OBSERVABILITY_PROVIDER", "null").lower()

        if provider_name == "langfuse":
            return LangfuseProvider(
                public_key=getattr(settings, "LANGFUSE_PUBLIC_KEY", ""),
                secret_key=getattr(settings, "LANGFUSE_SECRET_KEY", ""),
                host=getattr(settings, "LANGFUSE_HOST", "http://localhost:3000"),
            )
        elif provider_name == "phoenix":
            return PhoenixProvider(
                collector_endpoint=getattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces"),
                project_name=getattr(settings, "PHOENIX_PROJECT_NAME", "company-bot"),
            )
        else:
            return NullObservabilityProvider()

    def set_provider(self, provider: BaseObservabilityProvider) -> None:
        """Switch the active provider directly (useful for tests or custom injection)."""
        with self._lock:
            self._active_provider = provider
            logger.info("ObservabilityManager switched to custom provider: %s", type(provider).__name__)

    def switch_provider(self, provider_type: str) -> None:
        """Switch provider by name at runtime ('null', 'langfuse', 'phoenix')."""
        provider_name = provider_type.lower()
        with self._lock:
            if provider_name == "langfuse":
                self._active_provider = LangfuseProvider(
                    public_key=getattr(settings, "LANGFUSE_PUBLIC_KEY", ""),
                    secret_key=getattr(settings, "LANGFUSE_SECRET_KEY", ""),
                    host=getattr(settings, "LANGFUSE_HOST", "http://localhost:3000"),
                )
            elif provider_name == "phoenix":
                self._active_provider = PhoenixProvider(
                    collector_endpoint=getattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces"),
                    project_name=getattr(settings, "PHOENIX_PROJECT_NAME", "company-bot"),
                )
            elif provider_name == "null":
                self._active_provider = NullObservabilityProvider()
            else:
                logger.warning("Unknown observability provider '%s', defaulting to NullObservabilityProvider", provider_type)
                self._active_provider = NullObservabilityProvider()
            logger.info("ObservabilityManager switched active provider to: %s", type(self._active_provider).__name__)

    @property
    def active_provider(self) -> BaseObservabilityProvider:
        with self._lock:
            return self._active_provider

    # Delegate BaseObservabilityProvider methods to active provider

    def create_trace(
        self,
        name: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TraceSpanPort:
        with self._lock:
            provider = self._active_provider
        return provider.create_trace(name=name, session_id=session_id, user_id=user_id, metadata=metadata)

    def record_llm_call(
        self,
        model: str,
        token_usage: TokenUsage,
        latency_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            provider = self._active_provider
        provider.record_llm_call(model=model, token_usage=token_usage, latency_ms=latency_ms, metadata=metadata)

    def flush(self) -> None:
        with self._lock:
            provider = self._active_provider
        provider.flush()


# Global Singleton & Accessors
_manager_instance: Optional[ObservabilityManager] = None
_manager_lock = threading.Lock()


def get_observability_manager() -> ObservabilityManager:
    """Get or initialize the process-wide ObservabilityManager singleton."""
    global _manager_instance
    if _manager_instance is None:
        with _manager_lock:
            if _manager_instance is None:
                _manager_instance = ObservabilityManager()
    return _manager_instance


def reset_observability_manager() -> None:
    """Reset the singleton instance (primarily for unit test isolation)."""
    global _manager_instance
    with _manager_lock:
        _manager_instance = None
