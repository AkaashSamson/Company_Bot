"""Tests for Session Memory (AK-1.3) and Telemetry Tracing (AB-6.2) in QueryOrchestrator."""
import pytest
from unittest.mock import MagicMock, patch

from app.use_cases.chat.query_orchestrator import QueryOrchestrator
from app.infrastructure.observability.pipeline_tracer import PipelineStage


@pytest.fixture
def mock_dependencies():
    mock_retrieval = MagicMock()
    mock_retrieval.retrieve.return_value = [
        {"text": "Employees receive 20 PTO days.", "metadata": {"source": "Handbook", "section": "Leave"}}
    ]
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "Employees receive 20 days of paid time off."
    mock_llm.get_last_tokens.return_value = {
        "prompt_tokens": 50,
        "completion_tokens": 25,
        "total_tokens": 75,
        "model": "llama-3.3-70b-versatile",
    }
    mock_memory = MagicMock()
    mock_memory.get_history.return_value = []
    
    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_tracer.trace_stage.return_value.__enter__.return_value = mock_span
    mock_tracer.trace_stage.return_value.__exit__.return_value = None

    with patch.object(QueryOrchestrator, "_faq_search", return_value=None):
        yield {
            "retrieval": mock_retrieval,
            "llm": mock_llm,
            "memory": mock_memory,
            "pipeline_tracer": mock_tracer,
        }


def test_answer_loads_history_from_memory_if_not_provided(mock_dependencies):
    mock_dependencies["memory"].get_history.return_value = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    orchestrator = QueryOrchestrator(
        retrieval=mock_dependencies["retrieval"],
        llm=mock_dependencies["llm"],
        memory=mock_dependencies["memory"],
        pipeline_tracer=mock_dependencies["pipeline_tracer"],
    )

    result = orchestrator.answer("What is the leave policy?", session_id="session-123")

    mock_dependencies["memory"].get_history.assert_called_once_with("session-123")
    mock_dependencies["memory"].add_turn.assert_called_once_with(
        "session-123",
        "What is the leave policy?",
        result["answer"],
    )


def test_answer_caller_supplied_history_takes_precedence(mock_dependencies):
    caller_history = [{"role": "user", "content": "Custom prior question"}]

    orchestrator = QueryOrchestrator(
        retrieval=mock_dependencies["retrieval"],
        llm=mock_dependencies["llm"],
        memory=mock_dependencies["memory"],
        pipeline_tracer=mock_dependencies["pipeline_tracer"],
    )

    orchestrator.answer(
        "What is the leave policy?",
        conversation_history=caller_history,
        session_id="session-123",
    )

    # If caller supplied history, get_history should not override it
    mock_dependencies["memory"].get_history.assert_not_called()
    mock_dependencies["memory"].add_turn.assert_called_once()


def test_answer_instruments_pipeline_stages_and_ends_trace(mock_dependencies, monkeypatch):
    monkeypatch.setattr("app.core.settings.CACHE_ENABLED", True)
    monkeypatch.setattr("app.core.settings.SEMANTIC_CACHE_ENABLED", True)
    mock_cache = MagicMock()
    mock_cache.get.return_value = None
    orchestrator = QueryOrchestrator(
        retrieval=mock_dependencies["retrieval"],
        llm=mock_dependencies["llm"],
        memory=mock_dependencies["memory"],
        pipeline_tracer=mock_dependencies["pipeline_tracer"],
        response_cache=mock_cache,
    )

    result = orchestrator.answer("What is the leave policy?", session_id="session-trace-test")

    mock_dependencies["pipeline_tracer"].start_trace.assert_called_once_with("What is the leave policy?")
    mock_dependencies["pipeline_tracer"].end_trace.assert_called_once()
    
    # Verify stages were traced
    traced_stages = [call.args[0] for call in mock_dependencies["pipeline_tracer"].trace_stage.call_args_list]
    assert PipelineStage.NORMALIZATION in traced_stages
    assert PipelineStage.CACHE_LOOKUP in traced_stages
    assert PipelineStage.VECTOR_RETRIEVAL in traced_stages
    assert PipelineStage.LLM_GENERATION in traced_stages


def test_answer_fast_path_negative_reply_ends_trace(mock_dependencies):
    orchestrator = QueryOrchestrator(
        retrieval=mock_dependencies["retrieval"],
        llm=mock_dependencies["llm"],
        memory=mock_dependencies["memory"],
        pipeline_tracer=mock_dependencies["pipeline_tracer"],
    )

    # Negative reply to decline reference expansion
    with patch("app.use_cases.chat.query_orchestrator._pending_citations", {"session-fast": ["citation1"]}):
        with patch("app.use_cases.chat.query_orchestrator._last_assistant_offered_references", return_value=True):
            orchestrator.answer("no thanks", session_id="session-fast")

    mock_dependencies["pipeline_tracer"].start_trace.assert_called_once_with("no thanks")
    mock_dependencies["pipeline_tracer"].end_trace.assert_called_once()


def test_answer_cache_hit_ends_trace(mock_dependencies, monkeypatch):
    monkeypatch.setattr("app.core.settings.CACHE_ENABLED", True)
    monkeypatch.setattr("app.core.settings.SEMANTIC_CACHE_ENABLED", True)
    mock_cache = MagicMock()
    mock_cache.get.return_value = {"answer": "Cached answer.", "citations": []}

    orchestrator = QueryOrchestrator(
        retrieval=mock_dependencies["retrieval"],
        llm=mock_dependencies["llm"],
        memory=mock_dependencies["memory"],
        pipeline_tracer=mock_dependencies["pipeline_tracer"],
        response_cache=mock_cache,
    )

    res = orchestrator.answer("What is PTO?", session_id="session-cache-test")

    assert res["cache_hit"] is True
    assert res["answer"] == "Cached answer."
    mock_dependencies["pipeline_tracer"].start_trace.assert_called_once_with("What is PTO?")
    mock_dependencies["pipeline_tracer"].end_trace.assert_called_once_with(
        cache_hit=True,
        total_tokens=0,
        final_response="Cached answer.",
    )
    # Memory should record the turn even on cache hit
    mock_dependencies["memory"].add_turn.assert_called_once_with("session-cache-test", "What is PTO?", "Cached answer.")
