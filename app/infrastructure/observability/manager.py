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


def to_token_usage(usage_input: Any) -> Optional[TokenUsage]:
    """Boundary converter: safely translates LLMTokenUsage, dict, or TokenUsage into domain TokenUsage."""
    if usage_input is None:
        return None

    if isinstance(usage_input, TokenUsage):
        return usage_input

    # Duck-typed handling for LLMTokenUsage or any object with token attributes
    if hasattr(usage_input, "prompt_tokens"):
        p = getattr(usage_input, "prompt_tokens", 0)
        c = getattr(usage_input, "completion_tokens", 0)
        t = getattr(usage_input, "total_tokens", 0) or (p + c)
        return TokenUsage(prompt_tokens=p, completion_tokens=c, total_tokens=t)

    # Dict handling
    if isinstance(usage_input, dict):
        p = usage_input.get("prompt_tokens", 0)
        c = usage_input.get("completion_tokens", 0)
        t = usage_input.get("total_tokens", 0) or (p + c)
        return TokenUsage(prompt_tokens=p, completion_tokens=c, total_tokens=t)

    return None


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

    def export_pipeline_trace(self, trace: Any) -> None:
        """Delegate pipeline trace export to active provider."""
        self.dispatch_trace(trace)

    def dispatch_trace(self, trace: Any) -> None:
        """Dispatch a completed PipelineTrace execution record to the active observability provider.

        Binds root trace, individual stage spans, and LLM token usage (Task AB-6.3).
        Fails safe with logging: telemetry dispatch errors never raise exceptions to caller.
        """
        if trace is None:
            return

        try:
            with self._lock:
                provider = self._active_provider

            # Clean Architecture: If provider implements export_pipeline_trace (e.g. Langfuse), delegate directly
            if isinstance(provider, LangfuseProvider) or (getattr(provider, "supports_pipeline_export", None) is True):
                provider.export_pipeline_trace(trace)
                return

            trace_metadata = {
                "query": getattr(trace, "query", ""),
                "total_duration_ms": getattr(trace, "total_duration_ms", 0.0),
                "cache_hit": getattr(trace, "cache_hit", False),
                "early_exit": getattr(trace, "early_exit", False),
                "exit_stage": getattr(trace.exit_stage, "value", None) if getattr(trace, "exit_stage", None) else None,
                "exit_reason": getattr(trace, "exit_reason", None),
                "total_tokens": getattr(trace, "total_tokens", 0),
            }

            session_id = getattr(trace, "trace_id", None)
            root_span = provider.create_trace(
                name="QueryOrchestrator.answer",
                session_id=session_id,
                user_id=getattr(trace, "metadata", {}).get("user_id"),
                metadata=trace_metadata,
            )

            # Process individual stage spans
            spans = getattr(trace, "spans", []) or []
            for span in spans:
                stage_val = getattr(span.stage, "value", str(span.stage)) if hasattr(span, "stage") else "unknown"

                # Calculate duration safely without TypeError if end_time is None
                duration_ms = getattr(span, "duration_ms", 0.0)
                if not duration_ms:
                    start_t = getattr(span, "start_time", 0.0)
                    end_t = getattr(span, "end_time", None)
                    if end_t is not None and start_t:
                        duration_ms = (end_t - start_t) * 1000.0


                if stage_val == "llm_generation":
                    # Check for explicit token object in metadata or span attributes
                    out_meta = getattr(span, "output_metadata", {}) or {}
                    raw_usage = out_meta.get("tokens") or out_meta.get("token_usage")
                    if raw_usage is None and (getattr(span, "prompt_tokens", 0) or getattr(span, "completion_tokens", 0)):
                        raw_usage = {
                            "prompt_tokens": getattr(span, "prompt_tokens", 0),
                            "completion_tokens": getattr(span, "completion_tokens", 0),
                            "total_tokens": getattr(span, "tokens_used", 0),
                        }

                    token_vo = to_token_usage(raw_usage)
                    if token_vo is not None:
                        model_name = getattr(span, "input_metadata", {}).get("model", "unknown")
                        provider.record_llm_call(
                            model=model_name,
                            token_usage=token_vo,
                            latency_ms=duration_ms,
                            metadata=out_meta,
                        )
                elif stage_val.startswith("jev_") and hasattr(provider, "record_decision_call"):
                    in_meta = getattr(span, "input_metadata", {}) or {}
                    out_meta = getattr(span, "output_metadata", {}) or {}
                    model_name = in_meta.get("model", "typesafe/jev-1.14")
                    token_vo = None
                    if getattr(span, "prompt_tokens", 0) or getattr(span, "completion_tokens", 0):
                        token_vo = TokenUsage(
                            prompt_tokens=getattr(span, "prompt_tokens", 0),
                            completion_tokens=getattr(span, "completion_tokens", 0),
                            total_tokens=getattr(span, "tokens_used", 0),
                        )
                    provider.record_decision_call(
                        name=stage_val,
                        state=in_meta.get("state", ""),
                        questions=in_meta.get("questions", {}),
                        selection=out_meta.get("selection", out_meta),
                        model=model_name,
                        token_usage=token_vo,
                        latency_ms=duration_ms,
                        metadata=out_meta,
                    )

            if root_span:
                output_payload = {"final_response": getattr(trace, "final_response", None)}
                root_span.end(outputs=output_payload)

            provider.flush()

        except Exception as exc:
            logger.warning("ObservabilityManager failed to dispatch trace %s: %s", getattr(trace, "trace_id", "unknown"), exc)

    def record_decision_call(
        self,
        name: str,
        state: str,
        questions: Dict[str, Any],
        selection: Dict[str, Any],
        model: str = "typesafe/jev-1.14",
        token_usage: Optional[TokenUsage] = None,
        latency_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an individual decision / guardrail call to the active provider."""
        with self._lock:
            provider = self._active_provider
        if hasattr(provider, "record_decision_call"):
            try:
                provider.record_decision_call(
                    name=name,
                    state=state,
                    questions=questions,
                    selection=selection,
                    model=model,
                    token_usage=token_usage,
                    latency_ms=latency_ms,
                    metadata=metadata,
                )
            except Exception as exc:
                logger.warning("ObservabilityManager record_decision_call failed: %s", exc)



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
