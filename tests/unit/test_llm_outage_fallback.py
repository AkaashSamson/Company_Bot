import pytest
from unittest.mock import Mock

from app.domain.services.llm_provider import LLMProviderError
from app.use_cases.chat.query_orchestrator import QueryOrchestrator
from app.infrastructure.llm.prompt_cache import PromptLRUCache


def test_llm_outage_returns_clean_message_with_citations():
    """Verify that when the LLM provider fails, a clean notification is returned and citations are populated for collapsible UI."""
    retrieval_mock = Mock()
    retrieval_mock.retrieve.return_value = [
        {
            "text": "Regular full-time employees are entitled to 18 days of annual leave each year.",
            "metadata": {"source": "HR_Policy_Handbook.pdf", "section": "Leave Policy 3.1"},
        },
        {
            "text": "Salary claims and reimbursements must be submitted through the payroll portal by the 25th.",
            "metadata": {"source": "Finance_Payroll_Guide.pdf", "section": "Expense & Salary Claims"},
        },
    ]

    llm_mock = Mock()
    llm_mock.generate.side_effect = LLMProviderError("OpenRouter request timed out / unavailable")

    orchestrator = QueryOrchestrator(
        retrieval=retrieval_mock,
        llm=llm_mock,
        response_cache=PromptLRUCache(maxsize=10),
    )

    result = orchestrator.answer("how do I claim my salary?", session_id="test-session")

    # Assert response structure
    assert result is not None
    assert result["cache_hit"] is False
    assert result["tokens"] is None
    # Citations list is populated so UI can render them collapsibly
    assert len(result["citations"]) == 2
    assert result["citations"][0]["source"] == "HR_Policy_Handbook.pdf"
    assert result["citations"][1]["source"] == "Finance_Payroll_Guide.pdf"

    # Assert that the answer is a clean polite notice without dumping raw chunk text
    answer = result["answer"]
    assert "trouble reaching the AI provider" in answer
    assert "relevant information was found in the company policy documents" in answer
    assert "Finance_Payroll_Guide.pdf" not in answer
    assert "Salary claims and reimbursements must be submitted" not in answer


def test_llm_outage_bypasses_citation_deferral():
    """Verify that defer_citations is bypassed during an outage so users get references immediately."""
    retrieval_mock = Mock()
    retrieval_mock.retrieve.return_value = [
        {
            "text": "Casual leave must be applied at least 2 days in advance.",
            "metadata": {"source": "Leave_Policy.docx", "section": "Casual Leave"},
        }
    ]

    llm_mock = Mock()
    llm_mock.generate.side_effect = Exception("Connection refused by provider")

    orchestrator = QueryOrchestrator(
        retrieval=retrieval_mock,
        llm=llm_mock,
    )

    # Ask with defer_citations=True
    result = orchestrator.answer("how to apply for casual leave?", defer_citations=True)

    # Citations must be immediately attached despite defer_citations=True
    assert len(result["citations"]) == 1
    assert result["citations"][0]["source"] == "Leave_Policy.docx"
    assert "trouble reaching the AI provider" in result["answer"]


def test_llm_outage_does_not_poison_response_cache():
    """Verify that outage fallback answers are not saved into the semantic cache."""
    cache = PromptLRUCache(maxsize=10)
    retrieval_mock = Mock()
    retrieval_mock.retrieve.return_value = [
        {
            "text": "Medical insurance policy covers hospitalization up to $50,000.",
            "metadata": {"source": "Insurance.pdf", "section": "Health Benefits"},
        }
    ]

    llm_mock = Mock()
    llm_mock.generate.side_effect = LLMProviderError("Service Unavailable 503")

    orchestrator = QueryOrchestrator(
        retrieval=retrieval_mock,
        llm=llm_mock,
        response_cache=cache,
    )

    orchestrator.answer("what is the medical insurance coverage?")

    # Cache should remain empty because LLM failed
    assert cache.get("what is the medical insurance coverage?") is None
