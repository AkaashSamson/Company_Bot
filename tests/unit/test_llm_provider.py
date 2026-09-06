from unittest.mock import Mock
from unittest.mock import patch

import pytest

from app.domain.services.llm_provider import (
    LLMProvider,
    LLMProviderError,
)
from app.infrastructure.llm.fallback_llm_provider import (
    FallbackLLMProvider,
)
from app.infrastructure.llm.groq_client import GroqClient


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


def test_groq_error_includes_status_and_sanitized_response_body():
    response = Mock(
        status_code=404,
        is_error=True,
        text='{"error":"model not found", "token":"gsk_secret-value"}',
    )
    http_client = Mock()
    http_client.__enter__ = Mock(return_value=http_client)
    http_client.__exit__ = Mock(return_value=None)
    http_client.post.return_value = response

    with patch("app.infrastructure.llm.groq_client.httpx.Client", return_value=http_client):
        with pytest.raises(LLMProviderError, match=r"HTTP 404.*model not found") as error:
            GroqClient(api_key="test-key", model="missing-model").generate(
                [{"role": "user", "content": "Hello"}]
            )
    assert "gsk_secret-value" not in str(error.value)
    assert "[REDACTED_KEY]" in str(error.value)