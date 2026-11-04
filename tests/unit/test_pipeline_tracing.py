"""
Tests for Pipeline Tracing (AB-6, AB-7)

Tests the 8-stage pipeline tracer with span tracking,
context manager integration, and observability callbacks.
"""

import threading
import pytest
from app.infrastructure.observability.pipeline_tracer import (
    PipelineTracer,
    PipelineStage,
    StageSpan,
    TraceContext,
    PipelineTrace,
    get_pipeline_tracer,
)


@pytest.fixture
def tracer():
    """Create a fresh tracer instance for testing."""
    # Reset singleton for testing
    PipelineTracer._instance = None
    
    # Create new instance
    tracer = PipelineTracer.__new__(PipelineTracer)
    tracer._initialized = False
    tracer.enable_tracing = True
    tracer.max_traces = 100
    tracer._traces = {}
    tracer._current_trace = None
    tracer._current_span = None
    tracer._lock = threading.RLock()
    tracer._observability_callback = None
    tracer._initialized = True
    
    yield tracer
    
    # Cleanup
    tracer._traces.clear()
    PipelineTracer._instance = None


class TestPipelineTracer:
    """Test suite for PipelineTracer."""
    
    def test_singleton_pattern(self):
        """Test that tracer is a singleton."""
        t1 = get_pipeline_tracer()
        t2 = get_pipeline_tracer()
        assert t1 is t2
    
    def test_start_trace(self, tracer):
        """Test starting a new trace."""
        trace = tracer.start_trace("test query", "test_trace_1")
        
        assert trace is not None
        assert trace.query == "test query"
        assert trace.trace_id == "test_trace_1"
        assert len(trace.spans) == 0
    
    def test_end_trace(self, tracer):
        """Test ending a trace."""
        tracer.start_trace("test query", "test_trace_1")
        
        # Add a span manually for the test
        import time
        span = StageSpan(
            stage=PipelineStage.LLM_GENERATION,
            start_time=time.time(),
            input_metadata={},
        )
        span.prompt_tokens = 50
        span.completion_tokens = 50
        span.tokens_used = 100
        tracer._current_trace.add_span(span)
        
        completed = tracer.end_trace(
            trace_id="test_trace_1",
            cache_hit=False,
            early_exit=False,
            total_tokens=100,
        )
        
        assert completed is not None
        assert completed.cache_hit is False
        assert completed.total_tokens == 100
        assert completed.total_duration_ms >= 0
    
    def test_trace_stage_context_manager(self, tracer):
        """Test context manager for tracing stages."""
        trace = tracer.start_trace("test query")
        
        with tracer.trace_stage(PipelineStage.RETRIEVAL, input_metadata={"query": "test"}):
            import time
            time.sleep(0.002)
        
        # Check span was added
        assert len(trace.spans) == 1
        assert trace.spans[0].stage == PipelineStage.RETRIEVAL
        assert trace.spans[0].duration_ms >= 0
    
    def test_multiple_stages(self, tracer):
        """Test tracing multiple sequential stages."""
        trace = tracer.start_trace("test query")
        
        stages = [
            PipelineStage.NORMALIZATION,
            PipelineStage.CACHE_CHECK,
            PipelineStage.RETRIEVAL,
            PipelineStage.LLM_GENERATION,
        ]
        
        for stage in stages:
            with tracer.trace_stage(stage):
                pass
        
        assert len(trace.spans) == 4
        assert all(s.duration_ms >= 0 for s in trace.spans)
    
    def test_stage_timing(self, tracer):
        """Test that stage timing is accurate."""
        import time
        
        trace = tracer.start_trace("test query")
        
        with tracer.trace_stage(PipelineStage.RETRIEVAL):
            time.sleep(0.05)  # 50ms
        
        span = trace.spans[0]
        assert span.duration_ms >= 45  # Allow some tolerance
        assert span.duration_ms < 100
    
    def test_error_tracking(self, tracer):
        """Test that errors in stages are captured."""
        trace = tracer.start_trace("test query")
        
        try:
            with tracer.trace_stage(PipelineStage.LLM_GENERATION):
                raise ValueError("Test error")
        except ValueError:
            pass
        
        span = trace.spans[0]
        assert span.error is not None
        assert "Test error" in span.error
    
    def test_token_recording(self, tracer):
        """Test recording token usage."""
        trace = tracer.start_trace("test query")
        
        with tracer.trace_stage(PipelineStage.LLM_GENERATION) as span:
            if span:
                span.prompt_tokens = 100
                span.completion_tokens = 50
                span.tokens_used = 150  # Set directly for test
        
        span = trace.spans[0]
        assert span.prompt_tokens == 100
        assert span.completion_tokens == 50
        assert span.tokens_used == 150
    
    def test_cache_hit_tracking(self, tracer):
        """Test cache hit is tracked in trace."""
        tracer.start_trace("test query", "trace_1")
        
        completed = tracer.end_trace(
            trace_id="trace_1",
            cache_hit=True,
        )
        
        assert completed.cache_hit is True
    
    def test_early_exit_tracking(self, tracer):
        """Test early exit is tracked in trace."""
        tracer.start_trace("test query", "trace_1")
        
        completed = tracer.end_trace(
            trace_id="trace_1",
            early_exit=True,
            exit_stage=PipelineStage.QUALITY_ASSESSMENT,
            exit_reason="Insufficient evidence",
        )
        
        assert completed.early_exit is True
        assert completed.exit_stage == PipelineStage.QUALITY_ASSESSMENT
        assert completed.exit_reason == "Insufficient evidence"
    
    def test_get_trace(self, tracer):
        """Test retrieving a specific trace."""
        tracer.start_trace("query1", "trace_1")
        tracer.start_trace("query2", "trace_2")
        
        trace = tracer.get_trace("trace_1")
        assert trace is not None
        assert trace.query == "query1"
    
    def test_get_recent_traces(self, tracer):
        """Test getting recent traces."""
        import time
        for i in range(5):
            tracer.start_trace(f"query_{i}", f"trace_{i}")
            time.sleep(0.002)
        
        recent = tracer.get_recent_traces(3)
        assert len(recent) == 3
        # Most recent should be first
        assert recent[0].query == "query_4"
    
    def test_statistics(self, tracer):
        """Test tracer statistics."""
        # Create some traces
        for i in range(3):
            t = tracer.start_trace(f"query_{i}")
            t.cache_hit = i == 0  # First one is cache hit
            if i == 2:
                t.early_exit = True
            t.finish(cache_hit=i==0, early_exit=i==2)
        
        stats = tracer.get_statistics()
        
        assert stats["total_traces"] == 3
        assert stats["cache_hit_rate"] > 0
        assert stats["early_exit_rate"] > 0
    
    def test_observability_callback(self, tracer):
        """Test observability callback integration."""
        callback_calls = []
        
        def callback(trace):
            callback_calls.append(trace.trace_id)
        
        tracer.set_observability_callback(callback)
        
        # Create and complete a trace
        tracer.start_trace("test query", "trace_1")
        tracer.end_trace("trace_1")
        
        assert "trace_1" in callback_calls
    
    def test_disabled_tracing(self):
        """Test that tracing can be disabled."""
        tracer = PipelineTracer(enable_tracing=False)
        
        trace = tracer.start_trace("test query")
        assert trace is None
        
        # Context manager should also be disabled
        with tracer.trace_stage(PipelineStage.RETRIEVAL) as span:
            assert span is None


class TestPipelineStage:
    """Test PipelineStage enum."""
    
    def test_all_stages_defined(self):
        """Verify all 8 stages are defined."""
        stages = [
            PipelineStage.NORMALIZATION,
            PipelineStage.CACHE_CHECK,
            PipelineStage.FAQ_CHECK,
            PipelineStage.QUERY_EXPANSION,
            PipelineStage.RETRIEVAL,
            PipelineStage.QUALITY_ASSESSMENT,
            PipelineStage.LLM_GENERATION,
            PipelineStage.CACHE_WRITE,
        ]
        
        assert len(stages) == 8
    
    def test_stage_values(self):
        """Verify stage enum values."""
        assert PipelineStage.NORMALIZATION.value == "normalization"
        assert PipelineStage.LLM_GENERATION.value == "llm_generation"


class TestStageSpan:
    """Test StageSpan dataclass."""
    
    def test_span_creation(self):
        """Test creating a span."""
        import time
        
        span = StageSpan(
            stage=PipelineStage.RETRIEVAL,
            start_time=time.time(),
            input_metadata={"query": "test"},
        )
        
        assert span.stage == PipelineStage.RETRIEVAL
        assert span.duration_ms == 0.0
    
    def test_span_finish(self):
        """Test finishing a span calculates duration."""
        import time
        
        span = StageSpan(
            stage=PipelineStage.RETRIEVAL,
            start_time=time.time(),
        )
        
        time.sleep(0.01)
        
        span.finish(output_metadata={"results": 5})
        
        assert span.duration_ms > 0
        assert span.output_metadata["results"] == 5
    
    def test_span_to_dict(self):
        """Test span serialization."""
        import time
        
        span = StageSpan(
            stage=PipelineStage.RETRIEVAL,
            start_time=time.time(),
            input_metadata={"query": "test"},
        )
        
        d = span.to_dict()
        
        assert d["stage"] == "retrieval"
        assert "input_metadata" in d


class TestTraceContext:
    """Test TraceContext context manager (Task AB-6.1)."""

    def test_trace_context_lifecycle_and_duration(self, tracer):
        """Verify TraceContext measures stage duration accurately."""
        import time

        trace = tracer.start_trace("context test")
        with TraceContext(stage=PipelineStage.VECTOR_RETRIEVAL, tracer=tracer) as ctx:
            time.sleep(0.02)  # 20ms
            ctx.set_output(candidates=5)

        assert ctx.duration_ms >= 15
        assert ctx.stage == PipelineStage.VECTOR_RETRIEVAL
        assert ctx.output_metadata["candidates"] == 5
        assert len(trace.spans) == 1
        assert trace.spans[0].duration_ms >= 15

    def test_trace_context_token_recording(self, tracer):
        """Verify TraceContext records token metrics."""
        trace = tracer.start_trace("token test")
        with TraceContext(stage=PipelineStage.LLM_GENERATION, tracer=tracer) as ctx:
            ctx.record_tokens(prompt_tokens=120, completion_tokens=80)

        assert ctx.prompt_tokens == 120
        assert ctx.completion_tokens == 80
        assert ctx.tokens_used == 200

        span = trace.spans[0]
        assert span.prompt_tokens == 120
        assert span.completion_tokens == 80
        assert span.tokens_used == 200

    def test_trace_context_captures_exceptions(self, tracer):
        """Verify TraceContext captures error without swallowing exception."""
        trace = tracer.start_trace("error test")
        with pytest.raises(RuntimeError, match="Database disconnected"):
            with TraceContext(stage=PipelineStage.VECTOR_RETRIEVAL, tracer=tracer) as ctx:
                raise RuntimeError("Database disconnected")

        assert ctx.error == "Database disconnected"
        assert trace.spans[0].error == "Database disconnected"

    def test_canonical_8_stages_defined(self):
        """Verify all 8 canonical stages from Task AB-6.1 are defined."""
        canonical_stages = [
            PipelineStage.CONTEXT_REWRITE,
            PipelineStage.NORMALIZATION,
            PipelineStage.CACHE_LOOKUP,
            PipelineStage.VECTOR_RETRIEVAL,
            PipelineStage.RERANKING,
            PipelineStage.QUALITY_GATE,
            PipelineStage.LLM_GENERATION,
            PipelineStage.POST_GUARDRAILS,
        ]
        assert len(canonical_stages) == 8
        assert PipelineStage.CONTEXT_REWRITE.value == "context_rewrite"
        assert PipelineStage.CACHE_LOOKUP.value == "cache_lookup"
        assert PipelineStage.VECTOR_RETRIEVAL.value == "vector_retrieval"
        assert PipelineStage.RERANKING.value == "reranking"
        assert PipelineStage.QUALITY_GATE.value == "quality_gate"
        assert PipelineStage.POST_GUARDRAILS.value == "post_guardrails"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])