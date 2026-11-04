"""Tests for Langfuse Pipeline Trace Export, Timestamps, and Stage Span Hierarchy."""
import pytest
from unittest.mock import MagicMock

from app.infrastructure.observability.pipeline_tracer import PipelineTrace, StageSpan, PipelineStage
from app.infrastructure.observability.langfuse_provider import LangfuseProvider
from app.infrastructure.observability.manager import ObservabilityManager


@pytest.fixture
def sample_pipeline_trace():
    t_start = 1727700000.0
    trace = PipelineTrace(
        trace_id="trace-abc-123",
        query="how many sick leaves I have?",
        start_time=t_start,
        metadata={"user_id": "emp-001", "session_id": "session-xyz"},
    )
    # 1. Normalization span
    span_norm = StageSpan(
        stage=PipelineStage.NORMALIZATION,
        start_time=t_start,
        end_time=t_start + 0.05,
        duration_ms=50.0,
        input_metadata={"raw_query": "how many sick leaves I have?"},
        output_metadata={"normalized_query": "how many sick leaves i have"},
    )
    trace.add_span(span_norm)

    # 2. Retrieval span
    span_retrieval = StageSpan(
        stage=PipelineStage.VECTOR_RETRIEVAL,
        start_time=t_start + 0.05,
        end_time=t_start + 0.35,
        duration_ms=300.0,
        input_metadata={"query": "how many sick leaves i have"},
        output_metadata={
            "chunks_count": 3,
            "sources": ["leave_policy.pdf"],
            "documents": [
                {
                    "content": "Employees get 12 sick leaves annually.",
                    "source": "leave_policy.pdf",
                    "score": 0.15,
                    "chunk_id": "chunk-1",
                }
            ],
        },
    )
    trace.add_span(span_retrieval)

    # 3. LLM generation span
    sample_messages = [{"role": "user", "content": "how many sick leaves I have?"}]
    span_llm = StageSpan(
        stage=PipelineStage.LLM_GENERATION,
        start_time=t_start + 0.35,
        end_time=t_start + 1.25,
        duration_ms=900.0,
        input_metadata={"model": "llama-3.3-70b-versatile", "messages": sample_messages},
        output_metadata={"finish_reason": "stop", "completion": "You have 12 sick leaves remaining."},
        prompt_tokens=500,
        completion_tokens=201,
        tokens_used=701,
    )
    trace.add_span(span_llm)

    # Finish trace with final response
    trace.finish(
        cache_hit=False,
        total_tokens=701,
        final_response="You have 12 sick leaves remaining.",
    )
    trace.end_time = t_start + 1.25
    trace.total_duration_ms = 1250.0
    return trace


def test_pipeline_trace_captures_final_response(sample_pipeline_trace):
    assert sample_pipeline_trace.final_response == "You have 12 sick leaves remaining."
    assert sample_pipeline_trace.total_tokens == 701
    assert len(sample_pipeline_trace.spans) == 3


def test_observability_manager_delegates_to_export_pipeline_trace(sample_pipeline_trace):
    manager = ObservabilityManager()
    mock_provider = MagicMock(spec=LangfuseProvider)
    manager.set_provider(mock_provider)

    manager.dispatch_trace(sample_pipeline_trace)

    mock_provider.export_pipeline_trace.assert_called_once_with(sample_pipeline_trace)


def test_langfuse_provider_exports_root_and_child_spans_with_timestamps(sample_pipeline_trace):
    provider = LangfuseProvider(public_key="pk-dummy", secret_key="sk-dummy", host="http://localhost:3000")
    provider.enabled = True
    mock_client = MagicMock()

    # Root observation mock
    mock_root_obs = MagicMock()
    mock_root_obs._otel_span = MagicMock()
    mock_root_obs._otel_span._start_time = 0

    # Child observation mock
    mock_child_obs = MagicMock()
    mock_child_obs._otel_span = MagicMock()
    mock_child_obs._otel_span._start_time = 0

    mock_client.start_observation.return_value = mock_root_obs
    mock_root_obs.start_observation.return_value = mock_child_obs
    provider._client = mock_client

    provider.export_pipeline_trace(sample_pipeline_trace)

    # 1. Verify Root Observation has correct input, output, and metadata
    mock_client.start_observation.assert_called_once()
    root_call = mock_client.start_observation.call_args[1]
    assert root_call["name"] == "QueryOrchestrator.answer"
    assert root_call["as_type"] == "chain"
    assert root_call["input"] == "how many sick leaves I have?"
    assert root_call["output"] == {"final_response": "You have 12 sick leaves remaining."}
    assert root_call["metadata"]["session_id"] == "session-xyz"
    assert root_call["metadata"]["user_id"] == "emp-001"

    # Verify Root timestamps injected into Otel span
    assert mock_root_obs._otel_span._start_time == int(sample_pipeline_trace.start_time * 1e9)
    mock_root_obs.end.assert_called_once_with(end_time=int(sample_pipeline_trace.end_time * 1e9))

    # 2. Verify Child Stage observations nested under root
    assert mock_root_obs.start_observation.call_count == 3
    child_calls = mock_root_obs.start_observation.call_args_list

    # Child 1: Normalization
    assert child_calls[0][1]["name"] == "NORMALIZATION"
    assert child_calls[0][1]["as_type"] == "span"
    assert child_calls[0][1]["input"] == {"raw_query": "how many sick leaves I have?"}

    # Child 2: Vector Retrieval
    assert child_calls[1][1]["name"] == "VECTOR_RETRIEVAL"
    assert child_calls[1][1]["as_type"] == "retriever"
    assert child_calls[1][1]["input"] == {"query": "how many sick leaves i have"}
    assert child_calls[1][1]["output"]["chunks_count"] == 3
    assert len(child_calls[1][1]["output"]["documents"]) == 1
    assert child_calls[1][1]["output"]["documents"][0]["content"] == "Employees get 12 sick leaves annually."

    # Child 3: LLM Generation
    assert child_calls[2][1]["name"] == "LLM_GENERATION"
    assert child_calls[2][1]["as_type"] == "generation"
    assert child_calls[2][1]["usage_details"] == {"input": 500, "output": 201, "total": 701}
    assert child_calls[2][1]["model"] == "llama-3.3-70b-versatile"
    assert child_calls[2][1]["input"] == [{"role": "user", "content": "how many sick leaves I have?"}]
    assert child_calls[2][1]["output"] == "You have 12 sick leaves remaining."

    mock_client.flush.assert_called_once()
