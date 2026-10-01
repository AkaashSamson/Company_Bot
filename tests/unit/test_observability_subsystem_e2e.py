import pytest
from unittest.mock import MagicMock
from app.domain.ports.observability import TokenUsage
from app.infrastructure.llm.groq_client import GroqClient
from app.infrastructure.llm.llm_response import LLMTokenUsage
from app.infrastructure.observability.pipeline_tracer import (
    get_pipeline_tracer,
    PipelineStage,
)
from app.infrastructure.observability.manager import (
    get_observability_manager,
    reset_observability_manager,
)


@pytest.fixture(autouse=True)
def reset_singletons():
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


def test_full_observability_subsystem_turn_lifecycle(monkeypatch):
    # 1. Setup mock observability backend
    manager = get_observability_manager()
    mock_provider = MagicMock()
    mock_root_span = MagicMock()
    mock_provider.create_trace.return_value = mock_root_span
    manager.set_provider(mock_provider)

    tracer = get_pipeline_tracer()

    # 2. Simulate Groq client call producing LLMTokenUsage
    groq = GroqClient(api_key="test-key", model="llama-3.3-70b-versatile")
    fake_response_data = {
        "choices": [{"message": {"content": "Vacation policy details."}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160},
    }

    class FakeResponse:
        status_code = 200
        is_error = False

        def json(self):
            return fake_response_data

    monkeypatch.setattr(groq._client, "post", lambda *args, **kwargs: FakeResponse())
    llm_res = groq.generate_with_response([{"role": "user", "content": "How much vacation do I get?"}])
    assert llm_res.tokens is not None
    assert isinstance(llm_res.tokens, LLMTokenUsage)
    assert llm_res.tokens.total_tokens == 160
    assert groq.get_last_token_usage() == llm_res.tokens

    # 3. Simulate multi-stage pipeline trace
    trace = tracer.start_trace(query="How much vacation do I get?", trace_id="turn-e2e-999")

    # Stage: Normalization
    with tracer.trace_stage(PipelineStage.NORMALIZATION) as s:
        if s:
            s.output_metadata = {"normalized_query": "how much vacation do i get", "cache_key": "vacation_policy"}

    # Stage: Retrieval
    with tracer.trace_stage(PipelineStage.VECTOR_RETRIEVAL) as s:
        if s:
            s.output_metadata = {
                "chunks_count": 1,
                "chunks": [{"source": "HR_Policy.pdf", "score": 0.22, "snippet": "Employees receive 20 days..."}],
            }

    # Stage: LLM Generation
    with tracer.trace_stage(PipelineStage.LLM_GENERATION, input_metadata={"model": groq.model}) as s:
        if s:
            s.record_tokens(llm_res.tokens.prompt_tokens, llm_res.tokens.completion_tokens)
            s.output_metadata = {"completion": llm_res.content, "tokens": llm_res.tokens}

    # 4. Finish turn (triggers auto-dispatch to ObservabilityManager)
    tracer.end_trace(trace_id="turn-e2e-999", total_tokens=llm_res.tokens.total_tokens)

    # 5. Verify ObservabilityManager converted LLMTokenUsage -> TokenUsage and forwarded
    mock_provider.create_trace.assert_called_once_with(
        name="QueryOrchestrator.answer",
        session_id="turn-e2e-999",
        user_id=None,
        metadata={
            "query": "How much vacation do I get?",
            "total_duration_ms": trace.total_duration_ms,
            "cache_hit": False,
            "early_exit": False,
            "exit_stage": None,
            "exit_reason": None,
            "total_tokens": 160,
        },
    )

    mock_provider.record_llm_call.assert_called_once_with(
        model="llama-3.3-70b-versatile",
        token_usage=TokenUsage(prompt_tokens=120, completion_tokens=40, total_tokens=160),
        latency_ms=pytest.approx(trace.get_stage_duration(PipelineStage.LLM_GENERATION), rel=0.1),
        metadata={"completion": "Vacation policy details.", "tokens": llm_res.tokens},
    )

    mock_provider.flush.assert_called_once()
    mock_root_span.end.assert_called_once()
