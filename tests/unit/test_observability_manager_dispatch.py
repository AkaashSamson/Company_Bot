import pytest
import time
from unittest.mock import MagicMock
from app.domain.ports.observability import TokenUsage
from app.infrastructure.llm.llm_response import LLMTokenUsage
from app.infrastructure.observability.manager import (
    ObservabilityManager,
    reset_observability_manager,
    to_token_usage,
)
from app.infrastructure.observability.pipeline_tracer import (
    PipelineTrace,
    PipelineStage,
    StageSpan,
)


@pytest.fixture(autouse=True)
def clean_manager():
    reset_observability_manager()
    yield
    reset_observability_manager()


def test_to_token_usage_converts_llm_token_usage():
    llm_tokens = LLMTokenUsage(prompt_tokens=50, completion_tokens=25, total_tokens=75)
    token_vo = to_token_usage(llm_tokens)
    assert isinstance(token_vo, TokenUsage)
    assert token_vo.prompt_tokens == 50
    assert token_vo.completion_tokens == 25
    assert token_vo.total_tokens == 75


def test_to_token_usage_converts_dict():
    raw_dict = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    token_vo = to_token_usage(raw_dict)
    assert isinstance(token_vo, TokenUsage)
    assert token_vo.total_tokens == 15


def test_to_token_usage_returns_none_for_none():
    assert to_token_usage(None) is None


def test_dispatch_trace_creates_root_trace_and_dispatches_spans():
    manager = ObservabilityManager()
    mock_provider = MagicMock()
    mock_span = MagicMock()
    mock_provider.create_trace.return_value = mock_span
    manager.set_provider(mock_provider)

    now = time.time()
    trace = PipelineTrace(
        trace_id="test-trace-123",
        query="What is 401k?",
        start_time=now,
    )
    span_retrieval = StageSpan(
        stage=PipelineStage.VECTOR_RETRIEVAL,
        start_time=now,
        end_time=now + 0.1,
        duration_ms=100.0,
        input_metadata={"query": "What is 401k?"},
        output_metadata={"chunks_count": 2},
    )
    span_llm = StageSpan(
        stage=PipelineStage.LLM_GENERATION,
        start_time=now + 0.1,
        end_time=now + 0.5,
        duration_ms=400.0,
        input_metadata={"model": "llama-3.3-70b-versatile"},
        output_metadata={"completion": "401k is retirement..."},
        prompt_tokens=40,
        completion_tokens=20,
        tokens_used=60,
    )
    trace.add_span(span_retrieval)
    trace.add_span(span_llm)
    trace.finish(total_tokens=60, cache_hit=False)

    manager.dispatch_trace(trace)

    # 1. Root trace created with correct metadata
    mock_provider.create_trace.assert_any_call(
        name="QueryOrchestrator.answer",
        session_id="test-trace-123",
        user_id=None,
        metadata={
            "query": "What is 401k?",
            "total_duration_ms": trace.total_duration_ms,
            "cache_hit": False,
            "early_exit": False,
            "exit_stage": None,
            "exit_reason": None,
            "total_tokens": 60,
        },
    )

    # 2. LLM call recorded using converted TokenUsage VO
    mock_provider.record_llm_call.assert_called_once_with(
        model="llama-3.3-70b-versatile",
        token_usage=TokenUsage(prompt_tokens=40, completion_tokens=20, total_tokens=60),
        latency_ms=400.0,
        metadata={"completion": "401k is retirement..."},
    )

    # 3. Provider flushed
    mock_provider.flush.assert_called_once()
    mock_span.end.assert_called_once()


def test_dispatch_trace_handles_missing_end_time_gracefully():
    manager = ObservabilityManager()
    mock_provider = MagicMock()
    mock_span = MagicMock()
    mock_provider.create_trace.return_value = mock_span
    manager.set_provider(mock_provider)

    trace = PipelineTrace(trace_id="test-incomplete", query="Q")
    # Incomplete span with end_time=None
    span = StageSpan(stage=PipelineStage.CACHE_LOOKUP, start_time=time.time(), end_time=None, duration_ms=5.0)
    trace.add_span(span)
    trace.finish()

    # Must execute cleanly without throwing TypeError
    manager.dispatch_trace(trace)
    mock_provider.create_trace.assert_called_once()
