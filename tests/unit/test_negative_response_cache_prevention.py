import pytest
from unittest.mock import Mock

from app.core.cache_quality import is_negative_response
from app.use_cases.chat.query_orchestrator import QueryOrchestrator
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.llm.prompt_cache import PromptLRUCache
from app.infrastructure.cache.quality_aware_cache import (
    CacheQualityValidator,
    QualityGateDecision,
    CacheEntrySource,
)
from app.infrastructure.cache.dual_cache import JSONLocalCache, DualCache


def test_is_negative_response_classification():
    """Verify that all negative response variations are correctly detected."""
    negative_cases = [
        "No information regarding this topic was found ",
        "No information regarding this topic was found",
        "No information was found regarding this topic.",
        "No information about this policy was found.",
        "No relevant information was found in the documents.",
        "I could not find that information in the available documents.",
        "I could not find the requested information in the available documents.",
        "I was unable to find any information regarding appraisals.",
        "The policy does not contain information about leaves.",
        "This is not mentioned in the available documents.",
        "This information is not covered in the handbook.",
        "No specific document references are available for that query.",
        "Relevant information exists in a document that you do not currently have access to.",
        "   ",
        "",
    ]
    for text in negative_cases:
        assert is_negative_response(text) is True, f"Failed to detect negative response: {text!r}"

    positive_cases = [
        "Regular full-time employees are entitled to 18 days of annual leave each year.",
        "Bereavement leave is 5 days for immediate family members.",
        "Medical insurance covers hospitalization up to $50,000 with a valid claim receipt.",
        "Work from home is allowed up to 2 days per week upon manager approval.",
    ]
    for text in positive_cases:
        assert is_negative_response(text) is False, f"False positive on valid response: {text!r}"


def test_query_orchestrator_never_caches_negative_responses():
    """Verify QueryOrchestrator does not write negative responses to response_cache or faq_store."""
    mock_retrieval = Mock()
    mock_retrieval.retrieve.return_value = [
        {"text": "General HR overview without specific details.", "metadata": {"source": "Handbook.pdf"}}
    ]

    mock_llm = Mock()
    mock_llm.generate.return_value = "No information regarding this topic was found in the documents."

    mock_response_cache = Mock()
    mock_response_cache.get.return_value = None
    mock_faq_store = Mock()

    orchestrator = QueryOrchestrator(
        retrieval=mock_retrieval,
        llm=mock_llm,
        response_cache=mock_response_cache,
        faq_store=mock_faq_store,
    )

    result = orchestrator.answer("What is the appraisal policy?", session_id="test-negative-cache")

    assert "No information regarding this topic was found" in result["answer"]
    # Semantic cache put and set must NOT be called for negative responses
    mock_response_cache.put.assert_not_called()
    mock_response_cache.set.assert_not_called()
    # FAQ store save must NOT be called for negative responses
    mock_faq_store.save.assert_not_called()


def test_query_orchestrator_evicts_and_ignores_cached_negative_response():
    """Verify that if a negative response exists in cache, QueryOrchestrator evicts it and runs live retrieval."""
    mock_response_cache = Mock()
    # Simulate a poisoned cache entry containing a negative response
    mock_response_cache.get.return_value = {
        "answer": "No information regarding this topic was found",
        "citations": [],
    }

    mock_retrieval = Mock()
    mock_retrieval.retrieve.return_value = [
        {"text": "Appraisal policy: Annual performance reviews occur in December.", "metadata": {"source": "Appraisal.pdf"}}
    ]

    mock_llm = Mock()
    mock_llm.generate.return_value = "Annual performance reviews occur every December."

    orchestrator = QueryOrchestrator(
        retrieval=mock_retrieval,
        llm=mock_llm,
        response_cache=mock_response_cache,
    )

    result = orchestrator.answer("What is the appraisal policy?", session_id="test-evict-negative")

    # Cache hit must be False because the negative cached response was ignored
    assert result["cache_hit"] is False
    assert "Annual performance reviews" in result["answer"]
    # Retrieval and LLM were executed
    mock_retrieval.retrieve.assert_called_once()
    mock_llm.generate.assert_called_once()


def test_fallback_llm_provider_never_caches_negative_responses():
    """Verify FallbackLLMProvider does not cache negative responses into prompt cache."""
    primary_mock = Mock()
    primary_mock.generate.return_value = "No information regarding this topic was found."
    fallback_mock = Mock()

    cache = PromptLRUCache(maxsize=10)
    provider = FallbackLLMProvider(
        primary=primary_mock,
        fallback=fallback_mock,
        cache=cache,
    )

    messages = [{"role": "user", "content": "Tell me about alien policies."}]
    res = provider.generate(messages)

    assert "No information regarding this topic was found" in res
    # Cache must NOT store the negative response
    assert cache.get(messages) is None


def test_cache_quality_validator_fails_negative_responses():
    """Verify CacheQualityValidator explicitly fails negative responses under rule 7."""
    validator = CacheQualityValidator()

    result = validator.validate(
        query="What is the severance package?",
        response="No information regarding this topic was found.",
        confidence=0.95,
        evidence_count=2,
        source=CacheEntrySource.RAG_GENERATED,
    )

    assert result.is_valid is False
    assert result.decision == QualityGateDecision.FAIL
    assert "Negative/unverified response cannot be cached" in result.reason


def test_dual_cache_rejects_negative_responses(tmp_path):
    """Verify DualCache rejects caching negative responses in put()."""
    cache_file = tmp_path / "dual_cache.json"
    dual_cache = DualCache(json_fallback_path=str(cache_file), enable_sync=False)

    success = dual_cache.put(
        cache_key="query_key",
        original_query="What is the appraisal policy?",
        response="No information regarding this topic was found",
        confidence=0.9,
    )

    assert success is False
    assert dual_cache.get("query_key") is None
