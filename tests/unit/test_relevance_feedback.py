import pytest
from unittest.mock import Mock

from app.use_cases.chat.query_orchestrator import (
    QueryOrchestrator,
    RELEVANCE_PROMPT,
    REFERENCES_CONFIRM_PROMPT,
    _pending_citations,
    _last_interaction,
    _alternative_answer_given,
    _asked_references_confirm,
)


@pytest.fixture(autouse=True)
def clean_orchestrator_state():
    _pending_citations.clear()
    _last_interaction.clear()
    _alternative_answer_given.clear()
    _asked_references_confirm.clear()
    yield
    _pending_citations.clear()
    _last_interaction.clear()
    _alternative_answer_given.clear()
    _asked_references_confirm.clear()


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
    """Verify that when user confirms response is relevant, bot asks if they want references, and provides them if confirmed."""
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
    assert REFERENCES_CONFIRM_PROMPT in second_res["answer"]

    # When user says Yes to references
    history.extend([
        {"role": "user", "content": "Yes, it was relevant"},
        {"role": "assistant", "content": second_res["answer"]},
    ])
    third_res = orchestrator.answer("Yes, please", conversation_history=history, session_id=session_id)
    assert "Here are the references from the documents:" in third_res["answer"]
    assert len(third_res["citations"]) >= 1
    assert RELEVANCE_PROMPT not in third_res["answer"]
    assert third_res.get("action_type") is None


def test_user_satisfied_declines_references_shows_thank_you():
    """Verify that when user confirms satisfaction and declines references, a thank you message is displayed."""
    retrieval_mock = Mock()
    retrieval_mock.retrieve.return_value = [
        {
            "text": "Employees can carry forward up to 5 unused leave days.",
            "metadata": {"source": "HR_Policy.pdf", "section": "Leave Section 4"},
        }
    ]
    llm_mock = Mock()
    llm_mock.generate.return_value = f"You can carry forward 5 days.\n\n{RELEVANCE_PROMPT}"

    orchestrator = QueryOrchestrator(
        retrieval=retrieval_mock,
        llm=llm_mock,
    )

    session_id = "sess-rel-decline"
    first_res = orchestrator.answer("Can I carry forward leave?", session_id=session_id, defer_citations=True)

    history = [
        {"role": "user", "content": "Can I carry forward leave?"},
        {"role": "assistant", "content": first_res["answer"]},
    ]

    # User is satisfied
    second_res = orchestrator.answer("I am satisfied, thanks", conversation_history=history, session_id=session_id)
    assert REFERENCES_CONFIRM_PROMPT in second_res["answer"]

    # User declines references
    history.extend([
        {"role": "user", "content": "I am satisfied, thanks"},
        {"role": "assistant", "content": second_res["answer"]},
    ])
    third_res = orchestrator.answer("No thanks", conversation_history=history, session_id=session_id)
    assert "Thank you!" in third_res["answer"]
    assert third_res["citations"] == []
    assert RELEVANCE_PROMPT not in third_res["answer"]
    assert third_res.get("action_type") is None


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

    # User says it was not relevant (not satisfied)
    second_res = orchestrator.answer("No, not relevant", conversation_history=history, session_id=session_id)

    # 1. Verify caches were cleared
    mock_response_cache.clear.assert_called_once()
    mock_llm_cache.clear.assert_called_once()

    # 2. Verify alternative answer was generated by LLM
    assert llm_mock.generate.call_count == 2
    assert "Primary caregivers receive 12 weeks" in second_res["answer"]
    assert second_res["answer"].endswith(RELEVANCE_PROMPT)

    # 3. Now user says Yes to the alternative answer -> asks if they want references
    history.extend([
        {"role": "user", "content": "No, not relevant"},
        {"role": "assistant", "content": second_res["answer"]},
    ])
    third_res = orchestrator.answer("Yes", conversation_history=history, session_id=session_id)
    assert REFERENCES_CONFIRM_PROMPT in third_res["answer"]

    # 3b. Verify the confirmed answer was cached
    assert mock_response_cache.put.called, "Alternative answer should be cached after user confirms satisfaction"

    # 4. User confirms references
    history.extend([
        {"role": "user", "content": "Yes"},
        {"role": "assistant", "content": third_res["answer"]},
    ])
    fourth_res = orchestrator.answer("Yes, show references", conversation_history=history, session_id=session_id)
    assert "Here are the references from the documents:" in fourth_res["answer"]
    assert len(fourth_res["citations"]) >= 1


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


def test_cached_response_not_relevant_retrieves_and_generates_alternative():
    """Verify that when a cached response without evidence is rejected, fresh retrieval occurs and an alternative LLM answer is generated."""
    retrieval_mock = Mock()
    retrieval_mock.retrieve.return_value = [
        {
            "text": "Key design principles: 1. Separation of Responsibilities 2. Authentication 3. Authorization.",
            "metadata": {"source": "Architecture.md", "section": "Principles"},
        }
    ]

    llm_mock = Mock()
    llm_mock.generate.return_value = f"Here is an alternative explanation of design principles.\n\n{RELEVANCE_PROMPT}"

    mock_cache = Mock()
    mock_cache.search.return_value = None
    mock_cache.get.return_value = {
        "response": "Cached principles response.",
        "citations": [],
        "cache_id": "cch_test_123",
    }

    orchestrator = QueryOrchestrator(
        retrieval=retrieval_mock,
        llm=llm_mock,
        response_cache=mock_cache,
    )

    session_id = "sess-cache-test"
    # 1. First query: cache hit with empty citations
    first_res = orchestrator.answer("what is the key design principles?", session_id=session_id, defer_citations=True)
    assert first_res["cache_hit"] is True
    assert first_res["answer"].endswith(RELEVANCE_PROMPT)

    history = [
        {"role": "user", "content": "what is the key design principles?"},
        {"role": "assistant", "content": first_res["answer"]},
    ]

    # 2. User says 'no' -> evicts cache, retrieves fresh documents, and generates alternative from LLM
    second_res = orchestrator.answer("no", conversation_history=history, session_id=session_id)
    assert mock_cache.delete.called or mock_cache.invalidate.called or mock_cache.clear.called
    assert retrieval_mock.retrieve.called, "Fresh retrieval should be executed when cache evidence was empty"
    assert llm_mock.generate.called, "LLM should be called to generate alternative answer"
    assert "alternative explanation of design principles" in second_res["answer"]
    assert second_res["answer"].endswith(RELEVANCE_PROMPT)

    # 3. User is still not satisfied -> second 'no' gives formatted references
    history.extend([
        {"role": "user", "content": "no"},
        {"role": "assistant", "content": second_res["answer"]},
    ])
    third_res = orchestrator.answer("no", conversation_history=history, session_id=session_id)
    assert "Here are the references from the documents" in third_res["answer"]
    assert len(third_res["citations"]) == 1
    assert third_res["citations"][0]["source"] == "Architecture.md"


def test_query2_is_not_hijacked_as_feedback_for_query1():
    """Verify that a subsequent query (query 2) is executed fresh and not mistaken for feedback on query 1."""
    retrieval_mock = Mock()
    retrieval_mock.retrieve.side_effect = [
        [{"text": "Design principle: Separation of Responsibilities.", "metadata": {"source": "Architecture.md"}}],
        [{"text": "Remote work policy allows 2 days per week from home.", "metadata": {"source": "RemoteWork.md"}}],
    ]

    llm_mock = Mock()
    llm_mock.generate.side_effect = [
        f"Answer to query 1.\n\n{RELEVANCE_PROMPT}",
        f"Answer to query 2: remote work.\n\n{RELEVANCE_PROMPT}",
    ]

    faq_mock = Mock()
    faq_mock.search.return_value = None

    orchestrator = QueryOrchestrator(
        retrieval=retrieval_mock,
        llm=llm_mock,
        faq_cache=faq_mock,
    )

    session_id = "sess-q1-q2"
    # 1. User asks Query 1
    res1 = orchestrator.answer("what is the key design principles?", session_id=session_id)
    assert "Answer to query 1" in res1["answer"]
    assert res1["answer"].endswith(RELEVANCE_PROMPT)

    history = [
        {"role": "user", "content": "what is the key design principles?"},
        {"role": "assistant", "content": res1["answer"]},
    ]

    # 2. User asks Query 2 (contains 'please' and 'show', which previously might have triggered feedback)
    res2 = orchestrator.answer("please show the remote work policy", conversation_history=history, session_id=session_id)
    assert "Answer to query 2" in res2["answer"]
    assert res2["answer"].endswith(RELEVANCE_PROMPT)
    # Ensure retrieval was called for Query 2, not treated as feedback for Query 1
    assert retrieval_mock.retrieve.call_count == 2


def test_access_denied_response_does_not_append_relevance_prompt():
    """Verify that an RBAC access denied response stops cleanly without asking for relevance."""
    retrieval_mock = Mock()
    retrieval_mock.retrieve.return_value = []
    retrieval_mock.detect_unauthorized_relevance.return_value = [
        {"project_id": "proj-1", "document_id": "DOC-999"}
    ]
    orchestrator = QueryOrchestrator(
        retrieval=retrieval_mock,
        llm=Mock(),
        project_contact_lookup=lambda pid: {"project_name": "Project X", "manager_name": "Alice"},
    )
    res = orchestrator.answer("what are the confidential specs?", session_id="sess-rbac")
    assert "Relevant information exists in a project document" in res["answer"]
    assert RELEVANCE_PROMPT not in res["answer"]
    assert res.get("action_type") is None

