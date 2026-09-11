"""
LangSmith tracing integration.

Usage
-----
Wrap any callable with trace_step() to create a named span in LangSmith:

    from app.infrastructure.observability.tracer import trace_step

    with trace_step("retrieval", inputs={"query": query}) as span:
        results = vector_store.query(query)
        span.end(outputs={"chunks": len(results)})

When LANGCHAIN_TRACING_V2=false or LANGCHAIN_API_KEY is missing,
all calls are no-ops — no errors, no overhead.
"""

import logging
from contextlib import contextmanager
from typing import Any, Generator

from app.core.settings import (
    LANGCHAIN_API_KEY,
    LANGCHAIN_ENDPOINT,
    LANGCHAIN_PROJECT,
    LANGCHAIN_TRACING_V2,
)

logger = logging.getLogger(__name__)

# Activate LangSmith by setting the env vars it reads.
# langsmith reads these directly from os.environ — set them once here.
import os
if LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_ENDPOINT"] = LANGCHAIN_ENDPOINT
    os.environ["LANGCHAIN_PROJECT"] = LANGCHAIN_PROJECT
    logger.info("LangSmith tracing enabled → project '%s'", LANGCHAIN_PROJECT)
else:
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    logger.info("LangSmith tracing disabled.")


class _NoOpSpan:
    """Returned when tracing is disabled — all methods are safe no-ops."""
    def end(self, outputs: dict | None = None, error: str | None = None) -> None:
        pass


@contextmanager
def trace_step(
    name: str,
    inputs: dict[str, Any] | None = None,
    run_type: str = "chain",
) -> Generator[Any, None, None]:
    """
    Context manager that creates a LangSmith span when tracing is enabled.

    Parameters
    ----------
    name : str
        Display name for the span in LangSmith.
    inputs : dict, optional
        Key/value pairs logged as the step's inputs.
    run_type : str
        LangSmith run type: "chain", "retriever", "llm", "tool", etc.

    Yields
    ------
    span
        Object with .end(outputs, error) method. Call it to close the span
        with output data. If you don't call it, the span closes automatically.
    """
    if not (LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY):
        yield _NoOpSpan()
        return

    try:
        from langsmith import Client
        from langsmith.run_helpers import get_current_run_tree

        client = Client()
        run = client.create_run(
            name=name,
            run_type=run_type,
            inputs=inputs or {},
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
    except ImportError:
        logger.warning("langsmith not installed — tracing skipped.")
        yield _NoOpSpan()
    except Exception as exc:
        logger.warning("LangSmith trace_step failed: %s", exc)
        yield _NoOpSpan()


def traceable(name: str | None = None, run_type: str = "chain"):
    """
    Decorator that wraps a function in a LangSmith span.

    Example
    -------
        @traceable(name="FAQ Cache Search", run_type="retriever")
        def search(question: str) -> dict | None:
            ...
    """
    if not (LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY):
        # Return identity decorator when tracing is off
        def _identity(fn):
            return fn
        return _identity

    try:
        from langsmith import traceable as _ls_traceable
        return _ls_traceable(name=name, run_type=run_type)
    except ImportError:
        def _identity(fn):
            return fn
        return _identity
