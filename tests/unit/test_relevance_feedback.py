import pytest
from unittest.mock import Mock

from app.use_cases.chat.query_orchestrator import (
    QueryOrchestrator,
    RELEVANCE_PROMPT,
    _pending_citations,
    _last_interaction,
    _alternative_answer_given,
)


@pytest.fixture(autouse=True)
def clean_orchestrator_state():
    _pending_citations.clear()
    _last_interaction.clear()
    _alternative_answer_given.clear()
    yield
    _pending_citations.clear()
    _last_interaction.clear()
    _alternative_answer_given.clear()


def test_response_ends_with_relevance_prompt():
    """Verify that generated responses end with 'Was this response relevant to your question?'"""
    retrieval_mock = Mock()
    retrieval_mock.retrieve.return_value = [
        {
            "text": "Full-time employees receive 18 days of annual leave.",
            "metadata": {"source": "HR_Policy.pdf", "section": "Leave Section 3.1"},
        }
    ]
    llm_mock = Mock()
    llm_mock.generate.return_value = "Employees receive 18 days of annual leave."

    orchestrator = QueryOrchestrator(
        retrieval=retrieval_mock,
        llm=llm_mock,
    )

    result = orchestrator.answer("What is the annual leave entitlement?", session_id="sess-1")
    assert result["answer"].endswith(RELEVANCE_PROMPT)
    assert RELEVANCE_PROMPT in result["answer"]


def test_user_confirms_relevant_returns_formatted_references():
    """Verify that when user confirms response is relevant, document references are returned."""
    retrieval_mock = Mock()
    retrieval_mock.retrieve.return_value = [
        {
            "text": "Eligible employees receive 18 days of annual leave.",
            "metadata": {"source": "HR_Policy.pdf", "section": "Leave Section 3.1"},
        }
    ]
    llm_mock = Mock()
    llm_mock.generate.return_value = f"Employees receive 18 days of annual leave.\n\n{RELEVANCE_PROMPT}"

    orchestrator = QueryOrchestrator(
        retrieval=retrieval_mock,
        llm=llm_mock,
    )

    session_id = "sess-rel-1"
    first_res = orchestrator.answer("How many annual leave days do I get?", session_id=session_id, defer_citations=True)
    assert first_res["citations"] == []  # Deferred

    history = [
        {"role": "user", "content": "How many annual leave days do I get?"},
        {"role": "assistant", "content": first_res["answer"]},
    ]

    second_res = orchestrator.answer("Yes, it was relevant", conversation_history=history, session_id=session_id)
    assert "Here are the references from the documents:" in second_res["answer"]
    assert len(second_res["citations"]) >= 1


def test_user_reports_not_relevant_clears_cache_and_generates_alternative():
    """Verify that when user says 'not relevant', caches are cleared and a new alternative LLM answer is generated."""
    retrieval_mock = Mock()
    retrieval_mock.retrieve.return_value = [
        {
            "text": "Parental leave covers 12 weeks of paid leave for primary caregivers.",
            "metadata": {"source": "Parental_Policy.pdf", "section": "Parental Benefits"},
        }
    ]

    mock_response_cache = Mock()
    mock_response_cache.get.return_value = None  # Cache miss
    mock_llm_cache = Mock()
    llm_mock = Mock()
    llm_mock.cache = mock_llm_cache
    llm_mock.generate.side_effect = [
        f"General leave is available.\n\n{RELEVANCE_PROMPT}",
        f"Primary caregivers receive 12 weeks of fully paid parental leave.\n\n{RELEVANCE_PROMPT}",
    ]

    orchestrator = QueryOrchestrator(
        retrieval=retrieval_mock,
        llm=llm_mock,
        response_cache=mock_response_cache,
    )

    session_id = "sess-not-rel-1"
    first_res = orchestrator.answer("How long is parental leave?", session_id=session_id, defer_citations=True)
    assert "General leave is available" in first_res["answer"]

    history = [
        {"role": "user", "content": "How long is parental leave?"},
        {"role": "assistant", "content": first_res["answer"]},
    ]

    # User says it was not relevant
    second_res = orchestrator.answer("No, not relevant", conversation_history=history, session_id=session_id)

    # 1. Verify caches were cleared
    mock_response_cache.clear.assert_called_once()
    mock_llm_cache.clear.assert_called_once()

    # 2. Verify alternative answer was generated
    assert llm_mock.generate.call_count == 2
    assert "Primary caregivers receive 12 weeks" in second_res["answer"]
    assert second_res["answer"].endswith(RELEVANCE_PROMPT)

    # 3. Now user says Yes to the alternative answer -> receives citations
    history.extend([
        {"role": "user", "content": "No, not relevant"},
        {"role": "assistant", "content": second_res["answer"]},
    ])
    third_res = orchestrator.answer("Yes", conversation_history=history, session_id=session_id)
    assert "Here are the references from the documents:" in third_res["answer"]
    assert len(third_res["citations"]) >= 1


def test_second_not_relevant_gives_formatted_references():
    """Verify that if user says not relevant after the alternative answer has already been given, references are provided."""
    retrieval_mock = Mock()
    retrieval_mock.retrieve.return_value = [
        {
            "text": "Medical reimbursement requires official receipts within 30 days.",
            "metadata": {"source": "Medical_Policy.pdf", "section": "Claims"},
        }
    ]

    llm_mock = Mock()
    llm_mock.generate.side_effect = [
        f"First answer.\n\n{RELEVANCE_PROMPT}",
        f"Alternative answer.\n\n{RELEVANCE_PROMPT}",
    ]

    orchestrator = QueryOrchestrator(
        retrieval=retrieval_mock,
        llm=llm_mock,
    )

    session_id = "sess-repeat-no"
    r1 = orchestrator.answer("how to claim medical?", session_id=session_id, defer_citations=True)

    history = [
        {"role": "user", "content": "how to claim medical?"},
        {"role": "assistant", "content": r1["answer"]},
    ]
    # First "no" -> gets alternative
    r2 = orchestrator.answer("no", conversation_history=history, session_id=session_id)
    assert "Alternative answer" in r2["answer"]

    history.extend([
        {"role": "user", "content": "no"},
        {"role": "assistant", "content": r2["answer"]},
    ])
    # Second "no" -> gives direct references
    r3 = orchestrator.answer("no, still not relevant", conversation_history=history, session_id=session_id)
    assert "Here are the references from the documents for your review:" in r3["answer"]
    assert len(r3["citations"]) >= 1


def test_citation_number_stripping():
    """Verify that numbers and bullet points are stripped from citation text and section headers."""
    from app.use_cases.chat.provenance_service import ProvenanceService, _strip_numbering, _clean_section

    # Test individual string cleaner
    assert _strip_numbering("1. Employees receive 18 days leave.") == "Employees receive 18 days leave."
    assert _strip_numbering("1.2.3 Sick Leave Policy") == "Sick Leave Policy"
    assert _strip_numbering("(1) Parental leave is available.") == "Parental leave is available."
    assert _strip_numbering("- 1. Annual leave requires manager approval.") == "Annual leave requires manager approval."
    assert _strip_numbering("Section 3.1: Leave Entitlement") == "Leave Entitlement"
    assert _strip_numbering("1 - Employees must notify HR.") == "Employees must notify HR."
    assert _strip_numbering("a. First condition\nb. Second condition") == "First condition\nSecond condition"

    # Test section header cleaner
    assert _clean_section("Section 3.1 Leave Policy") == "Leave Policy"
    assert _clean_section("3.1 Casual Leave") == "Casual Leave"

    # Test full build_citations
    service = ProvenanceService()
    results = [
        {
            "text": "1. Casual leave may be availed up to 12 days per calendar year.\n2. Prior approval is mandatory.",
            "metadata": {"source": "Handbook.docx", "section": "Section 4.1 Leave Rules"},
        }
    ]
    citations = service.build_citations(results)
    assert len(citations) == 1
    assert citations[0]["section"] == "Leave Rules"
    assert citations[0]["text"] == "Casual leave may be availed up to 12 days per calendar year.\nPrior approval is mandatory."


def test_no_evidence_response_ends_with_relevance_prompt():
    """Verify that when no evidence is found, response still offers relevance prompt and handles feedback."""
    retrieval_mock = Mock()
    retrieval_mock.retrieve.return_value = []

    orchestrator = QueryOrchestrator(
        retrieval=retrieval_mock,
    )

    session_id = "sess-no-evidence"
    res = orchestrator.answer("What is the extraterrestrial policy?", session_id=session_id)
    assert res["answer"].endswith(RELEVANCE_PROMPT)

    history = [
        {"role": "user", "content": "What is the extraterrestrial policy?"},
        {"role": "assistant", "content": res["answer"]},
    ]

    # Feedback: user says not relevant
    res2 = orchestrator.answer("No, not relevant", conversation_history=history, session_id=session_id)
    assert res2["answer"].endswith(RELEVANCE_PROMPT)
    assert "could not find" in res2["answer"].lower() or "searched" in res2["answer"].lower()
