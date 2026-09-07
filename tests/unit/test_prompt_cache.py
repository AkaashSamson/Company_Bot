from unittest.mock import Mock

import pytest

from app.domain.services.llm_provider import LLMProvider, LLMProviderError
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.llm.prompt_cache import PromptLRUCache


def test_prompt_cache_reuses_successful_response():
    primary = Mock(spec=LLMProvider)
    fallback = Mock(spec=LLMProvider)
    primary.generate.return_value = "cached response"
    provider = FallbackLLMProvider(primary, fallback, cache=PromptLRUCache(maxsize=2))
    messages = [{"role": "user", "content": "Hello"}]

    assert provider.generate(messages) == "cached response"
    assert provider.generate(messages) == "cached response"
    primary.generate.assert_called_once_with(messages)
    fallback.generate.assert_not_called()


def test_prompt_cache_evicts_least_recently_used_response():
    cache = PromptLRUCache(maxsize=2)
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
    cache = PromptLRUCache(maxsize=0)
    messages = [{"role": "user", "content": "Hello"}]

    cache.put(messages, "response")

    assert cache.get(messages) is None


def test_failed_provider_calls_are_not_cached():
    primary = Mock(spec=LLMProvider)
    fallback = Mock(spec=LLMProvider)
    primary.generate.side_effect = LLMProviderError("primary unavailable")
    fallback.generate.side_effect = LLMProviderError("fallback unavailable")
    provider = FallbackLLMProvider(primary, fallback, cache=PromptLRUCache(maxsize=2))
    messages = [{"role": "user", "content": "Hello"}]

    with pytest.raises(LLMProviderError):
        provider.generate(messages)
    with pytest.raises(LLMProviderError):
        provider.generate(messages)

    assert primary.generate.call_count == 2
    assert fallback.generate.call_count == 2