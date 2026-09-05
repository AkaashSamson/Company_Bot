from unittest.mock import Mock

import pytest

from app.domain.services.llm_provider import (
    LLMProvider,
    LLMProviderError,
)
from app.infrastructure.llm.fallback_llm_provider import (
    FallbackLLMProvider,
)


def test_fallback_uses_primary_when_primary_succeeds():
    primary = Mock(spec=LLMProvider)
    fallback = Mock(spec=LLMProvider)

    primary.generate.return_value = "Primary response"

    provider = FallbackLLMProvider(
        primary=primary,
        fallback=fallback,
    )

    messages = [
        {"role": "user", "content": "Hello"},
    ]

    result = provider.generate(messages)

    assert result == "Primary response"
    primary.generate.assert_called_once_with(messages)
    fallback.generate.assert_not_called()


def test_fallback_uses_groq_when_primary_fails():
    primary = Mock(spec=LLMProvider)
    fallback = Mock(spec=LLMProvider)

    primary.generate.side_effect = LLMProviderError(
        "OpenRouter unavailable"
    )
    fallback.generate.return_value = "Fallback response"

    provider = FallbackLLMProvider(
        primary=primary,
        fallback=fallback,
    )

    messages = [
        {"role": "user", "content": "Hello"},
    ]

    result = provider.generate(messages)

    assert result == "Fallback response"

    primary.generate.assert_called_once_with(messages)
    fallback.generate.assert_called_once_with(messages)


def test_fallback_raises_when_both_providers_fail():
    primary = Mock(spec=LLMProvider)
    fallback = Mock(spec=LLMProvider)

    primary.generate.side_effect = LLMProviderError(
        "OpenRouter unavailable"
    )
    fallback.generate.side_effect = LLMProviderError(
        "Groq unavailable"
    )

    provider = FallbackLLMProvider(
        primary=primary,
        fallback=fallback,
    )

    messages = [
        {"role": "user", "content": "Hello"},
    ]

    with pytest.raises(LLMProviderError):
        provider.generate(messages)