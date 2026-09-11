from unittest.mock import Mock

import pytest

from app.domain.services.llm_provider import LLMProvider, LLMProviderError
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.llm.prompt_cache import PromptLRUCache
from app.infrastructure.llm.json_semantic_cache import JsonSemanticResponseCache


def embed_key(key):
    if "annual leave" in key or "vacation days" in key:
        return [1.0, 0.0, 0.0]
    if "first" in key:
        return [0.0, 1.0, 0.0]
    if "second" in key:
        return [0.0, 0.0, 1.0]
    if "third" in key:
        return [1.0, 1.0, 0.0]
    return [0.0, 0.0, 1.0]


def test_prompt_cache_reuses_successful_response():
    primary = Mock(spec=LLMProvider)
    fallback = Mock(spec=LLMProvider)
    primary.generate.return_value = "cached response"
    provider = FallbackLLMProvider(primary, fallback, cache=PromptLRUCache(maxsize=2, embedder=embed_key))
    messages = [{"role": "user", "content": "Hello"}]

    assert provider.generate(messages) == "cached response"
    assert provider.generate(messages) == "cached response"
    primary.generate.assert_called_once_with(messages)
    fallback.generate.assert_not_called()
    assert provider.cache.hits == 1
    assert provider.cache.misses == 1


def test_prompt_cache_reports_capacity_and_hit_rate_inputs():
    cache = PromptLRUCache(maxsize=2, embedder=embed_key)
    first = [{"role": "user", "content": "first"}]
    second = [{"role": "user", "content": "second"}]
    third = [{"role": "user", "content": "third"}]

    assert cache.get(first) is None
    cache.put(first, "one")
    cache.put(second, "two")
    assert cache.get(first) == "one"
    cache.put(third, "three")

    assert cache.size == 2
    assert cache.hits == 1
    assert cache.misses == 1
    assert cache.get(second) is None
    assert cache.misses == 2


def test_prompt_cache_evicts_least_recently_used_response():
    cache = PromptLRUCache(maxsize=2, embedder=embed_key)
    first = [{"role": "user", "content": "first"}]
    second = [{"role": "user", "content": "second"}]
    third = [{"role": "user", "content": "third"}]

    cache.put(first, "one")
    cache.put(second, "two")
    assert cache.get(first) == "one"
    cache.put(third, "three")

    assert cache.get(first) == "one"
    assert cache.get(second) is None
    assert cache.get(third) == "three"


def test_prompt_cache_can_be_disabled():
    cache = PromptLRUCache(maxsize=0, embedder=embed_key)
    messages = [{"role": "user", "content": "Hello"}]

    cache.put(messages, "response")

    assert cache.get(messages) is None


def test_failed_provider_calls_are_not_cached():
    primary = Mock(spec=LLMProvider)
    fallback = Mock(spec=LLMProvider)
    primary.generate.side_effect = LLMProviderError("primary unavailable")
    fallback.generate.side_effect = LLMProviderError("fallback unavailable")
    provider = FallbackLLMProvider(primary, fallback, cache=PromptLRUCache(maxsize=2, embedder=embed_key))
    messages = [{"role": "user", "content": "Hello"}]

    with pytest.raises(LLMProviderError):
        provider.generate(messages)
    with pytest.raises(LLMProviderError):
        provider.generate(messages)

    assert primary.generate.call_count == 2
    assert fallback.generate.call_count == 2


def test_semantically_similar_prompt_reuses_cached_response():
    primary = Mock(spec=LLMProvider)
    fallback = Mock(spec=LLMProvider)
    primary.generate.return_value = "18 days"
    provider = FallbackLLMProvider(
        primary,
        fallback,
        cache=PromptLRUCache(
            maxsize=2,
            similarity_threshold=0.95,
            embedder=embed_key,
        ),
    )

    original = [{"role": "user", "content": "How many annual leave days do I get?"}]
    rephrased = [{"role": "user", "content": "How many vacation days do I receive?"}]
    unrelated = [{"role": "user", "content": "What is the expense policy?"}]

    assert provider.generate(original) == "18 days"
    assert provider.generate(rephrased) == "18 days"
    assert provider.generate(unrelated) == "18 days"
    assert primary.generate.call_count == 2


def test_json_cache_persists_vector_and_exact_output(tmp_path):
    cache_path = tmp_path / "response_cache.json"
    first_cache = JsonSemanticResponseCache(
        cache_path,
        maxsize=2,
        similarity_threshold=0.95,
        embedder=embed_key,
    )
    messages = [{"role": "user", "content": "How many annual leave days do I get?"}]
    output = '{"answer":"18 days","citations":[{"source":"policy.docx"}]}'

    first_cache.put(messages, output)
    second_cache = JsonSemanticResponseCache(
        cache_path,
        maxsize=2,
        similarity_threshold=0.95,
        embedder=embed_key,
    )

    cached = second_cache.get([
        {"role": "user", "content": "How many vacation days do I receive?"}
    ])

    assert cached == output
    stored = __import__("json").loads(cache_path.read_text(encoding="utf-8"))
    assert stored["entries"][0]["input"] == "How many annual leave days do I get?"
    assert stored["entries"][0]["vector"] == [1.0, 0.0, 0.0]
    assert stored["entries"][0]["output"] == output