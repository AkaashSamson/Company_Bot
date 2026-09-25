from unittest.mock import MagicMock
import pytest

from app.domain.services.employee_id_provider import EmployeeIdProvider
from app.infrastructure.llm.fallback_llm_provider import LLMProviderError
from app.use_cases.chat.query_orchestrator import QueryOrchestrator


class DummyRetrieval:
    def __init__(self, evidence=None):
        self.evidence = evidence if evidence is not None else [{"text": "Leave policy is 20 days."}]

    def retrieve(self, query, top_k):
        return self.evidence


class DummyProvenance:
    def build_citations(self, evidence):
        return [{"source": "HR Handbook", "text": e["text"]} for e in evidence]


class DummyResolver:
    def resolve(self, question, history):
        return question


class DummyLLM:
    def __init__(self, answer="You have 20 days of leave."):
        self.answer = answer

    def generate(self, messages):
        return self.answer


class FailingLLM:
    def generate(self, messages):
        raise LLMProviderError("All providers failed")


def test_orchestrator_logs_conversation_on_successful_answer():
    """Verify logger is called after successful answer and citation generation."""
    mock_logger = MagicMock()
    orchestrator = QueryOrchestrator(
        retrieval=DummyRetrieval(),
        provenance=DummyProvenance(),
        llm=DummyLLM("You have 20 days of leave."),
        query_resolver=DummyResolver(),
        conversation_logger=mock_logger,
    )

    history = [{"role": "user", "content": "Prior question"}]
    result = orchestrator.answer(
        question="How many days?",
        conversation_history=history,
        session_id="test-session-42",
        user_context={"employee_id": "MSS001"},
    )

    # Response is normal
    assert result["answer"] == "You have 20 days of leave."
    assert len(result["citations"]) == 1

    # Logger was called once
    mock_logger.log_conversation.assert_called_once()
    call_kwargs = mock_logger.log_conversation.call_args.kwargs
    assert call_kwargs["session_id"] == "test-session-42"
    assert call_kwargs["user_context"] == {"employee_id": "MSS001"}

    # Messages include prior history, current question, and assistant answer
    messages = call_kwargs["messages"]
    messages = call_kwargs["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "How many days?"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "You have 20 days of leave."


def test_orchestrator_fallback_on_llm_failure():
    """Verify that if answer generation fails, orchestrator gracefully falls back to document text."""
    mock_logger = MagicMock()
    orchestrator = QueryOrchestrator(
        retrieval=DummyRetrieval(),
        provenance=DummyProvenance(),
        llm=FailingLLM(),
        query_resolver=DummyResolver(),
        conversation_logger=mock_logger,
    )

    result = orchestrator.answer("Any leave?", session_id="fail-session")
    assert "Leave policy is 20 days." in result["answer"]
    assert mock_logger.log_conversation.called


def test_orchestrator_isolates_logging_failure_from_chat_response():
    """Verify that logging exception does not affect or crash the chat response."""
    mock_logger = MagicMock()
    mock_logger.log_conversation.side_effect = RuntimeError("Disk error in logger")

    orchestrator = QueryOrchestrator(
        retrieval=DummyRetrieval(),
        provenance=DummyProvenance(),
        llm=DummyLLM("Standard answer"),
        query_resolver=DummyResolver(),
        conversation_logger=mock_logger,
    )

    # Should execute and return normally despite logger raising RuntimeError
    result = orchestrator.answer("What is the policy?", session_id="robust-session")
    assert result["answer"] == "Standard answer"
    assert len(result["citations"]) == 1


def test_orchestrator_logs_information_not_found_response():
    """Verify that when no evidence is found, the completion is still logged safely."""
    mock_logger = MagicMock()
    orchestrator = QueryOrchestrator(
        retrieval=DummyRetrieval(evidence=[]),
        provenance=DummyProvenance(),
        llm=DummyLLM(),
        query_resolver=DummyResolver(),
        conversation_logger=mock_logger,
    )

    result = orchestrator.answer("Completely unknown question", session_id="empty-session")
    assert "could not find" in result["answer"].lower()
    assert result["citations"] == []

    # Safe logging was invoked
    mock_logger.log_conversation.assert_called_once()
    call_kwargs = mock_logger.log_conversation.call_args.kwargs
    assert call_kwargs["session_id"] == "empty-session"
    assert "could not find" in call_kwargs["messages"][-1]["content"].lower()


def test_orchestrator_does_not_duplicate_trailing_user_question():
    """Verify that if trailing history already contains current question, it is not duplicated."""
    mock_logger = MagicMock()
    orchestrator = QueryOrchestrator(
        retrieval=DummyRetrieval(),
        provenance=DummyProvenance(),
        llm=DummyLLM("Standard answer"),
        query_resolver=DummyResolver(),
        conversation_logger=mock_logger,
    )

    history = [
        {"role": "user", "content": "Initial question"},
        {"role": "assistant", "content": "Initial answer"},
        {"role": "user", "content": "Current question"},
    ]

    orchestrator.answer("Current question", conversation_history=history)

    call_messages = mock_logger.log_conversation.call_args.kwargs["messages"]
    assert len(call_messages) == 2
    assert [m["content"] for m in call_messages] == [
        "Current question",
        "Standard answer",
    ]

