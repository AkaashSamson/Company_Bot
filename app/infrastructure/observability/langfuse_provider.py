import datetime
import logging
import os
import threading
from typing import Any, Dict, Optional

from app.domain.ports.observability import (
    BaseObservabilityProvider,
    TokenUsage,
    TraceSpanPort,
)

logger = logging.getLogger(__name__)

# Optional Langfuse SDK import
try:
    from langfuse import Langfuse
    _HAS_LANGFUSE = True
except ImportError:
    Langfuse = None  # type: ignore
    _HAS_LANGFUSE = False


def _clean_env_val(val: Optional[str]) -> str:
    """Strip quotes and surrounding whitespace from environment variable strings."""
    if not val:
        return ""
    return val.strip("\"' \t\r\n")


def _resolve_observation_type(name: str) -> str:
    """Map observation name to Langfuse canonical observation types (Langfuse Best Practice).
    
    Valid types: 'span', 'generation', 'retriever', 'tool', 'agent', 'chain', 'guardrail'.
    """
    lower = name.lower()
    if "retrieval" in lower or "retriever" in lower or "vector" in lower:
        return "retriever"
    if "generation" in lower or "llm" in lower:
        return "generation"
    if "guardrail" in lower:
        return "guardrail"
    if "tool" in lower:
        return "tool"
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
        sdk_observation: Any = None,
    ) -> None:
        self.provider = provider
        self.name = name
        self.session_id = session_id
        self.user_id = user_id
        self.metadata = metadata or {}
        self._sdk_obs = sdk_observation
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
        meta = {**self.metadata, "duration_ms": duration_ms}
        if self.session_id:
            meta["session_id"] = self.session_id
        if self.user_id:
            meta["user_id"] = self.user_id

        # Update Langfuse observation if SDK active
        if self._sdk_obs is not None:
            try:
                self._sdk_obs.update(
                    output=outputs,
                    status_message=error,
                    level="ERROR" if error else "DEFAULT",
                    metadata=meta,
                )
                self._sdk_obs.end()
            except Exception as exc:
                logger.warning("Langfuse span end failed: %s", exc)

    def __enter__(self) -> "LangfuseSpan":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self.end(error=str(exc_val))
        else:
            self.end()


class LangfuseProvider(BaseObservabilityProvider):
    """Vendor adapter for Langfuse observability.
    
    Built according to the official Langfuse AI Skill best practices:
    - Automatically resolves credentials from args or env (LANGFUSE_BASE_URL, LANGFUSE_HOST).
    - Maps stages to correct observation types ('retriever', 'generation', 'span', 'guardrail').
    - Captures model name, token usage details (input/output/total), and latencies.
    - Captures session_id and user_id for multi-turn conversational tracing.
    - Flushes event queue before termination.
    - Fails safe with zero crashes if Langfuse is unreachable.
    """

    def __init__(
        self,
        public_key: str = "",
        secret_key: str = "",
        host: str = "",
        enabled: bool = True,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._lock = threading.Lock()

        # Resolve credentials with robust env fallback and quote stripping
        self.public_key = _clean_env_val(public_key or os.getenv("LANGFUSE_PUBLIC_KEY", ""))
        self.secret_key = _clean_env_val(secret_key or os.getenv("LANGFUSE_SECRET_KEY", ""))
        raw_host = host or os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com"
        self.host = _clean_env_val(raw_host).rstrip("/")

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
                    logger.warning("LangfuseProvider auth check failed for %s", self.host)
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

    def create_trace(
        self,
        name: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LangfuseSpan:
        obs_type = _resolve_observation_type(name)
        sdk_obs = None

        meta = dict(metadata or {})
        if session_id:
            meta["session_id"] = session_id
        if user_id:
            meta["user_id"] = user_id

        if self.enabled and self._client is not None:
            try:
                sdk_obs = self._client.start_observation(
                    name=name,
                    as_type=obs_type,
                    metadata=meta,
                )
            except Exception as exc:
                logger.warning("Langfuse start_observation failed: %s", exc)

        return LangfuseSpan(
            provider=self,
            name=name,
            session_id=session_id,
            user_id=user_id,
            metadata=meta,
            sdk_observation=sdk_obs,
        )

    def record_llm_call(
        self,
        model: str,
        token_usage: TokenUsage,
        latency_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log token consumption and latency as a Langfuse generation observation."""
        if not self.enabled or self._client is None:
            logger.debug("Langfuse dry-run recorded LLM call: %s (%d tokens)", model, token_usage.total_tokens)
            return

        try:
            gen = self._client.start_observation(
                name=f"llm_generation_{model}",
                as_type="generation",
                model=model,
                usage_details={
                    "input": token_usage.prompt_tokens,
                    "output": token_usage.completion_tokens,
                    "total": token_usage.total_tokens,
                },
                metadata={
                    **(metadata or {}),
                    "latency_ms": latency_ms,
                },
            )
            gen.end()
        except Exception as exc:
            logger.warning("Langfuse record_llm_call failed: %s", exc)

    def flush(self) -> None:
        """Flush the Langfuse client event queue to ensure all background events are pushed."""
        if self.enabled and self._client is not None:
            try:
                self._client.flush()
                logger.debug("Langfuse client successfully flushed")
            except Exception as exc:
                logger.warning("Langfuse flush encountered error: %s", exc)

    def close(self) -> None:
        """Gracefully flush and shutdown Langfuse client workers."""
        if self.enabled and self._client is not None:
            try:
                if hasattr(self._client, "shutdown"):
                    self._client.shutdown()
                else:
                    self._client.flush()
            except Exception as exc:
                logger.warning("Langfuse shutdown encountered error: %s", exc)
