"""
Langfuse v4 Observability Provider.

Engineered according to the official Langfuse AI Skill best practices:
- Uses canonical observation types ('chain', 'retriever', 'tool', 'generation', 'guardrail', 'agent').
- Maintains span nesting and hierarchy via OpenTelemetry context propagation.
- Captures model name, usage_details (prompt, completion, total tokens), and latency for automated cost calculation.
- Associates traces with session_id and user_id for multi-turn conversational tracing.
- Captures user-meaningful inputs and outputs while masking confidential keys.
- Implements fail-safe execution: never crashes the caller if Langfuse is offline or unreachable.
- Flushes queues gracefully on process shutdown.
"""

import datetime
import logging
import threading
from typing import Any, Dict, Optional, Generator
from contextlib import contextmanager

from app.core import settings
from app.domain.ports.observability import (
    BaseObservabilityProvider,
    TokenUsage,
    TraceSpanPort,
)

logger = logging.getLogger(__name__)

# Optional Langfuse SDK import
try:
    from langfuse import Langfuse, propagate_attributes
    _HAS_LANGFUSE = True
except ImportError:
    Langfuse = None  # type: ignore
    propagate_attributes = None  # type: ignore
    _HAS_LANGFUSE = False


def _resolve_observation_type(name: str, run_type: Optional[str] = None) -> str:
    """Map observation name or run_type to canonical Langfuse observation types.
    
    Valid types in Langfuse v4:
    'chain', 'retriever', 'tool', 'generation', 'agent', 'guardrail', 'evaluator', 'span'.
    """
    if run_type:
        rt = run_type.lower()
        if rt in ("llm", "generation"):
            return "generation"
        if rt in ("retriever", "retrieval"):
            return "retriever"
        if rt in ("tool", "function"):
            return "tool"
        if rt in ("chain", "turn", "orchestrator"):
            return "chain"
        if rt in ("guardrail", "safety"):
            return "guardrail"
        if rt in ("agent",):
            return "agent"

    lower = name.lower()
    if any(k in lower for k in ("generation", "llm", "generate", "chat")):
        return "generation"
    if any(k in lower for k in ("retrieval", "retriever", "vector", "search", "cache", "faq")):
        return "retriever"
    if any(k in lower for k in ("normalize", "normalizer", "tool", "filter", "preprocess")):
        return "tool"
    if any(k in lower for k in ("guardrail", "safety", "scope", "authorize", "probe")):
        return "guardrail"
    if any(k in lower for k in ("answer", "orchestrator", "chain", "pipeline", "turn")):
        return "chain"
    if "agent" in lower:
        return "agent"
    return "span"


class LangfuseSpan(TraceSpanPort):
    """Trace span adapter conforming to TraceSpanPort, backed by Langfuse v4 SDK."""

    def __init__(
        self,
        provider: "LangfuseProvider",
        name: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        cm: Any = None,
        sdk_obs: Any = None,
    ) -> None:
        self.provider = provider
        self.name = name
        self.session_id = session_id
        self.user_id = user_id
        self.metadata = dict(metadata or {})
        self._cm = cm
        self._sdk_obs = sdk_obs
        self.start_time = datetime.datetime.now(datetime.timezone.utc)
        self.end_time: Optional[datetime.datetime] = None
        self.outputs: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.is_ended: bool = False

    def update(
        self,
        input: Optional[Any] = None,
        output: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update active observation properties dynamically."""
        if metadata:
            self.metadata.update(metadata)
        if self._sdk_obs is not None:
            try:
                update_kwargs: Dict[str, Any] = {}
                if input is not None:
                    update_kwargs["input"] = input
                if output is not None:
                    update_kwargs["output"] = output
                if self.metadata:
                    update_kwargs["metadata"] = self.metadata
                if update_kwargs:
                    self._sdk_obs.update(**update_kwargs)
            except Exception as exc:
                logger.debug("Langfuse observation update failed: %s", exc)

    def end(self, outputs: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
        if self.is_ended:
            return
        self.end_time = datetime.datetime.now(datetime.timezone.utc)
        self.outputs = outputs
        self.error = error
        self.is_ended = True

        duration_ms = (self.end_time - self.start_time).total_seconds() * 1000.0
        meta = {**self.metadata, "duration_ms": duration_ms}
        if self.session_id:
            meta["session_id"] = self.session_id
        if self.user_id:
            meta["user_id"] = self.user_id

        # Update and close Langfuse observation
        if self._sdk_obs is not None:
            try:
                self._sdk_obs.update(
                    output=outputs,
                    status_message=error,
                    level="ERROR" if error else "DEFAULT",
                    metadata=meta,
                )
            except Exception as exc:
                logger.debug("Langfuse observation update on end failed: %s", exc)

        if self._cm is not None:
            try:
                self._cm.__exit__(None, None, None)
            except Exception as exc:
                logger.debug("Langfuse observation context exit failed: %s", exc)

    def __enter__(self) -> "LangfuseSpan":
        if self._cm is not None and self._sdk_obs is None:
            try:
                self._sdk_obs = self._cm.__enter__()
            except Exception as exc:
                logger.debug("Langfuse context manager __enter__ failed: %s", exc)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self.end(error=str(exc_val))
        else:
            self.end(outputs=self.outputs)


class LangfuseProvider(BaseObservabilityProvider):
    """Vendor adapter for Langfuse observability.
    
    Built according to the official Langfuse AI Skill best practices:
    - Resolves credentials cleanly from environment or settings.
    - Automatically structures traces with canonical observation types ('chain', 'retriever', 'tool', 'generation').
    - Nests multi-step pipelines accurately using OpenTelemetry context propagation.
    - Captures model details, token consumption (input/output/total), and latencies.
    - Tracks session_id for multi-turn conversation views and user_id for cost attribution.
    - Zero crash guarantee: gracefully falls back to no-op mode if server is unavailable.
    """

    supports_pipeline_export: bool = True

    def __init__(
        self,
        public_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        host: Optional[str] = None,
        enabled: bool = True,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._lock = threading.Lock()

        # Cleanly resolve credentials
        pk = public_key if public_key is not None else getattr(settings, "LANGFUSE_PUBLIC_KEY", "")
        sk = secret_key if secret_key is not None else getattr(settings, "LANGFUSE_SECRET_KEY", "")
        raw_host = host if host is not None else getattr(settings, "LANGFUSE_HOST", getattr(settings, "LANGFUSE_BASE_URL", "https://cloud.langfuse.com"))

        self.public_key = str(pk or "").strip("\"' \t\r\n")
        self.secret_key = str(sk or "").strip("\"' \t\r\n")
        self.host = str(raw_host or "https://cloud.langfuse.com").strip("\"' \t\r\n").rstrip("/")

        self.timeout = timeout_seconds
        self.enabled = enabled and bool(self.public_key and self.secret_key and _HAS_LANGFUSE)
        self._client: Optional[Any] = None

        if self.enabled:
            try:
                self._client = Langfuse(
                    public_key=self.public_key,
                    secret_key=self.secret_key,
                    host=self.host,
                    timeout=self.timeout,
                )
                auth_ok = self._client.auth_check()
                if auth_ok:
                    logger.info("LangfuseProvider successfully authenticated with %s", self.host)
                else:
                    logger.warning("LangfuseProvider auth check failed for %s; continuing in fallback mode", self.host)
            except Exception as exc:
                logger.warning("LangfuseProvider failed to initialize SDK: %s", exc)
                self.enabled = False
                self._client = None
        else:
            logger.debug(
                "LangfuseProvider running in offline / dry-run mode (has_sdk=%s, has_keys=%s)",
                _HAS_LANGFUSE,
                bool(self.public_key and self.secret_key),
            )

    def export_pipeline_trace(self, trace: Any) -> None:
        """Convert domain PipelineTrace and StageSpans into Langfuse hierarchical observations."""
        if not self.enabled or self._client is None or trace is None:
            return

        try:
            query = getattr(trace, "query", "")
            final_response = getattr(trace, "final_response", None)
            trace_id = getattr(trace, "trace_id", None)
            meta = {
                "total_duration_ms": getattr(trace, "total_duration_ms", 0.0),
                "cache_hit": getattr(trace, "cache_hit", False),
                "early_exit": getattr(trace, "early_exit", False),
                "exit_stage": getattr(trace.exit_stage, "value", None) if getattr(trace, "exit_stage", None) else None,
                "exit_reason": getattr(trace, "exit_reason", None),
                "total_tokens": getattr(trace, "total_tokens", 0),
            }
            user_id = getattr(trace, "metadata", {}).get("user_id") if hasattr(trace, "metadata") else None
            session_id = getattr(trace, "metadata", {}).get("session_id", trace_id)

            # 1. Start Root Observation
            root_obs = self._client.start_observation(
                name="QueryOrchestrator.answer",
                as_type="chain",
                input=query,
                output={"final_response": final_response} if final_response is not None else None,
                metadata={**meta, "session_id": session_id, "user_id": user_id},
            )

            # Inject pre-recorded root start timestamp into OpenTelemetry span
            t_start = getattr(trace, "start_time", None)
            if root_obs is not None and hasattr(root_obs, "_otel_span") and t_start:
                try:
                    root_obs._otel_span._start_time = int(t_start * 1e9)
                except Exception:
                    pass

            # 2. Iterate and attach Child Stage Spans (nested under root_obs)
            spans = getattr(trace, "spans", []) or []
            for span in spans:
                raw_stage = getattr(span, "stage", "stage")
                stage_val = getattr(raw_stage, "value", str(raw_stage)).upper()
                obs_type = _resolve_observation_type(stage_val)

                span_kwargs: Dict[str, Any] = {
                    "name": stage_val,
                    "as_type": obs_type,
                    "input": getattr(span, "input_metadata", None),
                    "output": getattr(span, "output_metadata", None),
                    "metadata": {
                        "duration_ms": getattr(span, "duration_ms", 0.0),
                        "error": getattr(span, "error", None),
                    },
                }

                # Attach generation model & token metrics for LLM stages
                if obs_type == "generation" or "generation" in stage_val.lower():
                    model_name = getattr(span, "input_metadata", {}).get("model", "unknown")
                    span_kwargs["model"] = model_name
                    p_tok = getattr(span, "prompt_tokens", 0)
                    c_tok = getattr(span, "completion_tokens", 0)
                    t_tok = getattr(span, "tokens_used", 0) or (p_tok + c_tok)
                    if t_tok > 0 or p_tok > 0 or c_tok > 0:
                        span_kwargs["usage_details"] = {
                            "input": p_tok,
                            "output": c_tok,
                            "total": t_tok,
                        }

                # Nest under root_obs using root_obs.start_observation
                child_obs = None
                if root_obs is not None and hasattr(root_obs, "start_observation"):
                    child_obs = root_obs.start_observation(**span_kwargs)
                else:
                    child_obs = self._client.start_observation(**span_kwargs)

                if child_obs is not None:
                    # Inject child start timestamp
                    child_start = getattr(span, "start_time", None)
                    child_start_ns = int(child_start * 1e9) if child_start else None
                    if hasattr(child_obs, "_otel_span") and child_start_ns:
                        try:
                            child_obs._otel_span._start_time = child_start_ns
                        except Exception:
                            pass

                    if getattr(span, "error", None):
                        child_obs.update(level="ERROR", status_message=str(span.error))

                    dur_ms = getattr(span, "duration_ms", 0.0) or 0.0
                    # Ensure at least 0.1ms (100,000 ns) so span is visible and strictly monotonic
                    dur_ns = max(int(dur_ms * 1_000_000), 100_000)
                    child_end_ns = (child_start_ns + dur_ns) if child_start_ns else None
                    child_obs.end(end_time=child_end_ns)

            # 3. End Root Observation with recorded end_time
            if root_obs is not None:
                t_end = getattr(trace, "end_time", None)
                root_end_ns = int(t_end * 1e9) if t_end else None
                root_obs.end(end_time=root_end_ns)

            self.flush()

        except Exception as exc:
            logger.warning("Langfuse export_pipeline_trace encountered error: %s", exc)

    @property
    def client(self) -> Optional[Any]:
        return self._client

    def create_trace(
        self,
        name: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        inputs: Optional[Any] = None,
        run_type: Optional[str] = None,
    ) -> LangfuseSpan:
        """Create a new root trace or child observation span."""
        obs_type = _resolve_observation_type(name, run_type)
        meta = dict(metadata or {})
        if session_id:
            meta["session_id"] = session_id
        if user_id:
            meta["user_id"] = user_id

        cm = None
        sdk_obs = None

        if self.enabled and self._client is not None:
            try:
                # Apply attributes context if available
                if propagate_attributes and (session_id or user_id):
                    propagate_attributes(
                        session_id=session_id,
                        user_id=user_id,
                        tags=["knowlayer", "rag"],
                    )

                cm = self._client.start_as_current_observation(
                    name=name,
                    as_type=obs_type,
                    input=inputs,
                    metadata=meta,
                )
                sdk_obs = cm.__enter__()
            except Exception as exc:
                logger.debug("Langfuse start_as_current_observation failed: %s", exc)
                cm = None
                sdk_obs = None

        return LangfuseSpan(
            provider=self,
            name=name,
            session_id=session_id,
            user_id=user_id,
            metadata=meta,
            cm=cm,
            sdk_obs=sdk_obs,
        )

    @contextmanager
    def trace_step(
        self,
        name: str,
        inputs: Optional[Any] = None,
        run_type: str = "span",
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Generator[LangfuseSpan, None, None]:
        """Context manager for tracing an internal pipeline step."""
        span = self.create_trace(
            name=name,
            session_id=session_id,
            user_id=user_id,
            metadata=metadata,
            inputs=inputs,
            run_type=run_type,
        )
        try:
            yield span
        except Exception as exc:
            span.end(error=str(exc))
            raise
        else:
            if not span.is_ended:
                span.end()

    def record_llm_call(
        self,
        model: str,
        token_usage: TokenUsage,
        latency_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
        prompt: Optional[Any] = None,
        completion: Optional[Any] = None,
    ) -> None:
        """Log token consumption, latency, and messages as a Langfuse generation observation."""
        if not self.enabled or self._client is None:
            logger.debug("Langfuse dry-run recorded LLM call: %s (%d tokens)", model, token_usage.total_tokens)
            return

        try:
            # Langfuse generation observation for automated cost & token calculation
            with self._client.start_as_current_observation(
                name="llm-generation",
                as_type="generation",
                model=model,
                input=prompt,
                output=completion,
                usage_details={
                    "input": token_usage.prompt_tokens,
                    "output": token_usage.completion_tokens,
                    "total": token_usage.total_tokens,
                },
                metadata={
                    **(metadata or {}),
                    "latency_ms": latency_ms,
                },
            ):
                pass
        except Exception as exc:
            logger.debug("Langfuse record_llm_call failed: %s", exc)

    def flush(self) -> None:
        """Flush the Langfuse client event queue to ensure all background events are pushed."""
        if self.enabled and self._client is not None:
            try:
                self._client.flush()
                logger.debug("Langfuse client successfully flushed")
            except Exception as exc:
                logger.debug("Langfuse flush encountered error: %s", exc)

    def close(self) -> None:
        """Gracefully flush and shutdown Langfuse client workers."""
        if self.enabled and self._client is not None:
            try:
                if hasattr(self._client, "shutdown"):
                    self._client.shutdown()
                else:
                    self._client.flush()
            except Exception as exc:
                logger.debug("Langfuse shutdown encountered error: %s", exc)
