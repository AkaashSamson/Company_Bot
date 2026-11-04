import pytest
from unittest.mock import MagicMock

from app.use_cases.chat.query_normalizer import QueryNormalizer
from app.use_cases.chat.query_orchestrator import QueryOrchestrator, _pending_citations
from app.infrastructure.llm.prompt_cache import PromptLRUCache


class FakeRetrieval:
    def __init__(self, evidence=None):
        self.evidence = evidence or [{"text": "Company payment policy stipulates monthly bank transfers."}]
        self.last_query = None

    def retrieve(self, query, top_k=5):
        self.last_query = query
        return self.evidence


class FakeProvenance:
    def build_citations(self, evidence):
        return [{"source": "HR Policy", "section": "Payments", "text": e["text"]} for e in evidence]


class FakeLLM:
    def __init__(self):
        self.last_messages = None

    def generate(self, messages):
        self.last_messages = messages
        return "Payments are processed on the 30th of each month."


def test_query_normalizer_dynamic_spellchecker_new_words():
    """Verify spelling checker corrects unseen/new words and domain terms."""
    normalizer = QueryNormalizer()
    
    # Domain words with typos
    res1 = normalizer.normalize("Tell me about pyment poilcy")
    assert res1.normalized_query == "tell me about payment policy"
    
    res2 = normalizer.normalize("What is my annul leve?")
    assert res2.normalized_query == "what is my annual leave"
    
    res3 = normalizer.normalize("How do I request reimbursment?")
    assert res3.normalized_query == "how do i request reimbursement"

    # Preserves valid non-domain words
    res4 = normalizer.normalize("Hello world project details")
    assert "world" in res4.normalized_query


def test_orchestrator_handles_negative_reference_follow_up():
    """Verify that responding 'no' or 'no thanks' to a reference prompt does not search documents."""
    retrieval = FakeRetrieval()
    orchestrator = QueryOrchestrator(
        retrieval=retrieval,
        provenance=FakeProvenance(),
        llm=FakeLLM(),
        response_cache=PromptLRUCache(maxsize=10),
    )

    session_id = "test-negative-session"
    _pending_citations[session_id] = [{"source": "HR Handbook", "section": "Leave", "text": "Some text"}]

    history = [
        {"role": "user", "content": "How does leave work?"},
        {"role": "assistant", "content": "You get 20 days. Would you like to see the references for this?"},
    ]

    result = orchestrator.answer("no thanks", conversation_history=history, session_id=session_id)

    assert "Understood!" in result["answer"]
    assert result["citations"] == []
    # Verify retrieval was NOT called for "no thanks"
    assert retrieval.last_query is None
    # Verify pending citations were cleared
    assert session_id not in _pending_citations


def test_orchestrator_dual_cache_hit():
    """Verify that cached responses can be retrieved via normalized or raw question."""
    retrieval = FakeRetrieval()
    llm = FakeLLM()
    cache = PromptLRUCache(maxsize=10)
    orchestrator = QueryOrchestrator(
        retrieval=retrieval,
        provenance=FakeProvenance(),
        llm=llm,
        response_cache=cache,
    )

    # First query
    res1 = orchestrator.answer("What is the payment policy?", session_id="s1")
    assert res1["cache_hit"] is False

    # Second query with different casing and whitespace
    res2 = orchestrator.answer("what is the payment policy?", session_id="s1")
    assert res2["cache_hit"] is True
    assert res2["answer"] == res1["answer"]
