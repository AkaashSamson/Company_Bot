import time
from unittest.mock import MagicMock
from app.infrastructure.observability.pipeline_tracer import PipelineTracer, PipelineStage, TraceContext, StageSpan
from app.infrastructure.observability.langfuse_provider import LangfuseProvider
from unittest.mock import patch

def test_stage_span_high_precision_duration():
    span = StageSpan(stage=PipelineStage.NORMALIZATION, start_time=time.time())
    # Sub-millisecond sleep
    time.sleep(0.001)
    span.finish()
    assert span.duration_ms > 0.0, "duration_ms must be non-zero even for short operations"

def test_trace_context_high_precision_duration():
    tracer = PipelineTracer.create_new(enable_tracing=True)
    trace = tracer.start_trace("test query")
    with TraceContext(stage=PipelineStage.CACHE_LOOKUP, tracer=tracer) as ctx:
        time.sleep(0.0005)
    
    assert ctx.duration_ms > 0.0
    assert trace.spans[0].duration_ms > 0.0

@patch("app.infrastructure.observability.langfuse_provider.Langfuse")
def test_langfuse_child_span_timestamps_non_zero(mock_langfuse_cls):
    mock_client = MagicMock()
    mock_root = MagicMock()
    mock_child = MagicMock()
    mock_client.start_observation.return_value = mock_root
    mock_root.start_observation.return_value = mock_child
    mock_child._otel_span = MagicMock()

    provider = LangfuseProvider(public_key="pk-test", secret_key="sk-test", host="http://mock")
    provider._client = mock_client

    tracer = PipelineTracer.create_new(enable_tracing=True)
    trace = tracer.start_trace("test query")
    with TraceContext(stage=PipelineStage.NORMALIZATION, tracer=tracer):
        pass
    trace.finish(final_response="test response")

    provider.export_pipeline_trace(trace)
    assert mock_child.end.called
    end_kwargs = mock_child.end.call_args.kwargs
    assert "end_time" in end_kwargs
    # Verify child_end is strictly greater than child_start
    child_start_ns = mock_child._otel_span._start_time
    assert end_kwargs["end_time"] > child_start_ns
