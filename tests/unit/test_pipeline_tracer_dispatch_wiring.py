import pytest
from unittest.mock import MagicMock
from app.infrastructure.observability.pipeline_tracer import (
    PipelineTracer,
    PipelineStage,
    get_pipeline_tracer,
)
from app.infrastructure.observability.manager import (
    get_observability_manager,
    reset_observability_manager,
)


@pytest.fixture(autouse=True)
def clean_state():
    reset_observability_manager()
    tracer = get_pipeline_tracer()
    tracer.enable_tracing = True
    tracer._traces.clear()
    tracer._current_trace = None
    tracer._observability_callback = None
    yield
    reset_observability_manager()
    tracer.enable_tracing = True
    tracer._traces.clear()
    tracer._current_trace = None
    tracer._observability_callback = None


def test_end_trace_automatically_dispatches_to_observability_manager(monkeypatch):
    manager = get_observability_manager()
    mock_dispatch = MagicMock()
    monkeypatch.setattr(manager, "dispatch_trace", mock_dispatch)

    tracer = get_pipeline_tracer()
    tracer.enable_tracing = True

    trace = tracer.start_trace(query="Test query", trace_id="trace-auto-1")
    tracer.end_trace(trace_id="trace-auto-1", cache_hit=True, total_tokens=0)

    mock_dispatch.assert_called_once()
    dispatched_trace = mock_dispatch.call_args[0][0]
    assert dispatched_trace.trace_id == "trace-auto-1"
    assert dispatched_trace.query == "Test query"
    assert dispatched_trace.cache_hit is True


def test_custom_observability_callback_takes_precedence_if_set():
    tracer = get_pipeline_tracer()
    tracer.enable_tracing = True
    custom_cb = MagicMock()
    tracer.set_observability_callback(custom_cb)

    trace = tracer.start_trace(query="Callback query", trace_id="trace-cb-1")
    tracer.end_trace(trace_id="trace-cb-1")

    custom_cb.assert_called_once()


def test_disabled_tracing_does_not_dispatch(monkeypatch):
    manager = get_observability_manager()
    mock_dispatch = MagicMock()
    monkeypatch.setattr(manager, "dispatch_trace", mock_dispatch)

    tracer = get_pipeline_tracer()
    tracer.enable_tracing = False

    trace = tracer.start_trace(query="Disabled query", trace_id="trace-disabled-1")
    assert trace is None
    ended = tracer.end_trace(trace_id="trace-disabled-1")
    assert ended is None

    mock_dispatch.assert_not_called()
