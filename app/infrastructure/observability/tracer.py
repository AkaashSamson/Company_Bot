"""
Unified Tracing Integration (Langfuse & LangSmith).

Provides vendor-neutral `@traceable` decorator and `trace_step()` context manager.
Automatically dispatches to Langfuse when OBSERVABILITY_PROVIDER=langfuse,
to LangSmith when LANGCHAIN_TRACING_V2=true, or safe no-op otherwise.
"""

import functools
import inspect
import logging
import os
from contextlib import contextmanager
from typing import Any, Callable, Dict, Generator, Optional

from app.core import settings
from app.core.settings import (
    LANGCHAIN_API_KEY,
    LANGCHAIN_ENDPOINT,
    LANGCHAIN_PROJECT,
    LANGCHAIN_TRACING_V2,
)

logger = logging.getLogger(__name__)

# Activate LangSmith if enabled
if LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_ENDPOINT"] = LANGCHAIN_ENDPOINT
    os.environ["LANGCHAIN_PROJECT"] = LANGCHAIN_PROJECT
    logger.info("LangSmith tracing enabled → project '%s'", LANGCHAIN_PROJECT)
else:
    os.environ["LANGCHAIN_TRACING_V2"] = "false"


class _NoOpSpan:
    """Returned when tracing is disabled — all methods are safe no-ops."""
    def end(self, outputs: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
        pass

    def update(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


def _is_langfuse_active() -> bool:
    provider = getattr(settings, "OBSERVABILITY_PROVIDER", "").lower()
    return provider == "langfuse"


def _sanitize_inputs(func: Callable, args: tuple, kwargs: dict) -> Dict[str, Any]:
    """Extract clean, user-meaningful inputs without leaking 'self' or sensitive keys."""
    sensitive_keys = {"api_key", "secret", "password", "token", "auth", "authorization", "secret_key"}
    cleaned: Dict[str, Any] = {}

    try:
        sig = inspect.signature(func)
        bound = sig.bind_partial(*args, **kwargs)
        for name, val in bound.arguments.items():
            if name in ("self", "cls"):
                continue
            if any(s in name.lower() for s in sensitive_keys):
                cleaned[name] = "[REDACTED]"
            elif isinstance(val, (str, int, float, bool, list, dict)) or val is None:
                cleaned[name] = val
            else:
                cleaned[name] = str(val)[:200]
    except Exception:
        # Fallback if binding fails
        for k, v in kwargs.items():
            if any(s in k.lower() for s in sensitive_keys):
                cleaned[k] = "[REDACTED]"
            elif isinstance(v, (str, int, float, bool)):
                cleaned[k] = v
        if args and len(args) > 1 and isinstance(args[1], str):
            cleaned["query"] = args[1]
        elif args and len(args) > 0 and isinstance(args[0], str):
            cleaned["query"] = args[0]

    return cleaned


def _sanitize_output(result: Any) -> Any:
    """Sanitize output object for trace display."""
    if isinstance(result, dict):
        # Exclude massive internal objects, keep user-facing text
        clean = {}
        for k, v in result.items():
            if k in ("answer", "question", "cache_hit", "tokens", "is_latest", "model", "latency_ms"):
                clean[k] = v
            elif k == "citations" and isinstance(v, list):
                clean[k] = [
                    {"document": getattr(c, "document_name", str(c)), "page": getattr(c, "page_number", None)}
                    if hasattr(c, "document_name") else str(c)[:100]
                    for c in v[:5]
                ]
            elif isinstance(v, (str, int, float, bool)):
                clean[k] = v
        return clean
    elif isinstance(result, str):
        return result
    return str(result)[:500]


@contextmanager
def trace_step(
    name: str,
    inputs: Optional[Any] = None,
    run_type: str = "chain",
    metadata: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Generator[Any, None, None]:
    """Context manager for tracing an internal pipeline step."""
    # 1. Langfuse Dispatch
    if _is_langfuse_active():
        try:
            from app.infrastructure.observability.manager import get_observability_manager
            mgr = get_observability_manager()
            with mgr.trace_step(
                name=name,
                inputs=inputs,
                run_type=run_type,
                metadata=metadata,
                session_id=session_id,
                user_id=user_id,
            ) as span:
                yield span
            return
        except Exception as exc:
            logger.debug("Langfuse trace_step dispatch error: %s", exc)
            yield _NoOpSpan()
            return

    # 2. LangSmith Dispatch
    if LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY:
        try:
            from langsmith import Client
            client = Client()
            run = client.create_run(
                name=name,
                run_type=run_type,
                inputs=inputs if isinstance(inputs, dict) else {"input": inputs},
                project_name=LANGCHAIN_PROJECT,
            )
            try:
                yield run
            except Exception as exc:
                run.end(error=str(exc))
                client.update_run(run.id, error=str(exc))
                raise
            else:
                client.update_run(run.id)
            return
        except Exception as exc:
            logger.debug("LangSmith trace_step failed: %s", exc)
            yield _NoOpSpan()
            return

    # 3. No-op
    yield _NoOpSpan()


def traceable(name: Optional[str] = None, run_type: str = "chain") -> Callable:
    """Decorator that wraps a function or method in a trace span.
    
    Compatible with Langfuse v4 canonical types and LangSmith.
    """
    def decorator(fn: Callable) -> Callable:
        span_name = name or fn.__name__

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not (_is_langfuse_active() or (LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY)):
                    return await fn(*args, **kwargs)

                clean_in = _sanitize_inputs(fn, args, kwargs)
                with trace_step(name=span_name, inputs=clean_in, run_type=run_type) as span:
                    try:
                        res = await fn(*args, **kwargs)
                        if hasattr(span, "update"):
                            span.update(output=_sanitize_output(res))
                        return res
                    except Exception as exc:
                        if hasattr(span, "end"):
                            span.end(error=str(exc))
                        raise
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not (_is_langfuse_active() or (LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY)):
                    return fn(*args, **kwargs)

                clean_in = _sanitize_inputs(fn, args, kwargs)
                with trace_step(name=span_name, inputs=clean_in, run_type=run_type) as span:
                    try:
                        res = fn(*args, **kwargs)
                        if hasattr(span, "update"):
                            span.update(output=_sanitize_output(res))
                        return res
                    except Exception as exc:
                        if hasattr(span, "end"):
                            span.end(error=str(exc))
                        raise
            return sync_wrapper

    return decorator
