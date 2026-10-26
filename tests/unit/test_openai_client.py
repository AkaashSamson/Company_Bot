import pytest
from unittest.mock import MagicMock, Mock, patch

from openai import APIError, APITimeoutError, RateLimitError

from app.domain.services.llm_provider import LLMProviderError
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.llm.llm_response import (
    LLMProviderName,
    LLMResponse,
    LLMResponseStatus,
)
from app.infrastructure.llm.openai_client import OpenAIClient, _extract_usage, _strip_reasoning
from app.infrastructure.llm.provider_health import ProviderHealthMonitor, ProviderType
from app.use_cases.chat.query_orchestrator import QueryOrchestrator


@pytest.fixture
def health_monitor():
    monitor = ProviderHealthMonitor()
    monitor.reset_all()
    return monitor


def _create_mock_completion(content="Paris is wonderful.", prompt_tokens=10, completion_tokens=20):
    choice = Mock()
    choice.message.content = content
    completion = Mock()
    completion.choices = [choice]
    completion.usage = Mock()
    completion.usage.prompt_tokens = prompt_tokens
    completion.usage.completion_tokens = completion_tokens
    completion.usage.total_tokens = prompt_tokens + completion_tokens
    return completion


def test_strip_reasoning_removes_think_tags_and_headers():
    raw = "<think>I need to think about this.</think>\n1. Analysis: Here is some reasoning.\nParis is the capital of France."
    cleaned = _strip_reasoning(raw)
    assert cleaned == "Paris is the capital of France."


def test_extract_usage_handles_both_objects_and_dicts():
    p, c, t = _extract_usage({"prompt_tokens": 12, "completion_tokens": 18, "total_tokens": 30})
    assert (p, c, t) == (12, 18, 30)

    mock_obj = Mock(prompt_tokens=5, completion_tokens=15, total_tokens=20)
    p2, c2, t2 = _extract_usage(mock_obj)
    assert (p2, c2, t2) == (5, 15, 20)

    p3, c3, t3 = _extract_usage(None)
    assert (p3, c3, t3) == (0, 0, 0)


def test_openai_client_initializes_azure(health_monitor):
    with patch("app.infrastructure.llm.openai_client.AzureOpenAI") as mock_azure:
        client = OpenAIClient(
            api_key="test-key",
            endpoint="https://pcsazureopenai.openai.azure.com/",
            api_version="2024-12-01-preview",
            deployment="gpt-4o",
            health_monitor=health_monitor,
        )
        assert mock_azure.called
        assert client.effective_model == "gpt-4o"


def test_openai_client_initializes_standard_openai(health_monitor):
    with patch("app.infrastructure.llm.openai_client.OpenAI") as mock_openai:
        client = OpenAIClient(
            api_key="test-key",
            endpoint="",
            api_version="",
            deployment="",
            model="gpt-4o",
            health_monitor=health_monitor,
        )
        assert mock_openai.called
        assert client.effective_model == "gpt-4o"


def test_openai_client_handles_missing_api_key(health_monitor):
    client = OpenAIClient(api_key="", health_monitor=health_monitor)
    assert client._client is None

    with pytest.raises(LLMProviderError, match="not configured"):
        client.generate([{"role": "user", "content": "Hi"}])

    metrics = health_monitor.get_metrics(ProviderType.OPENAI.value)
    assert metrics.failed_requests == 1


def test_openai_client_generate_success(health_monitor):
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.return_value = _create_mock_completion(
        content="Visit the Eiffel Tower.",
        prompt_tokens=15,
        completion_tokens=25,
    )

    client = OpenAIClient(
        api_key="test-key",
        client=mock_sdk_client,
        health_monitor=health_monitor,
    )

    result = client.generate([{"role": "user", "content": "What should I see?"}])
    assert result == "Visit the Eiffel Tower."

    # Check metrics
    metrics = health_monitor.get_metrics(ProviderType.OPENAI.value)
    assert metrics.total_requests == 1
    assert metrics.successful_requests == 1
    assert metrics.failed_requests == 0

    # Check token tracking
    last_tokens = client.get_last_tokens()
    assert last_tokens is not None
    assert last_tokens["prompt_tokens"] == 15
    assert last_tokens["completion_tokens"] == 25
    assert last_tokens["total_tokens"] == 40


def test_openai_client_generate_empty_content_raises(health_monitor):
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.return_value = _create_mock_completion(content="")

    client = OpenAIClient(
        api_key="test-key",
        client=mock_sdk_client,
        health_monitor=health_monitor,
    )

    with pytest.raises(LLMProviderError, match="empty message content"):
        client.generate([{"role": "user", "content": "Hi"}])

    metrics = health_monitor.get_metrics(ProviderType.OPENAI.value)
    assert metrics.failed_requests == 1


def test_openai_client_generate_rate_limit(health_monitor):
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.side_effect = RateLimitError(
        message="Rate limit exceeded",
        response=Mock(status_code=429, headers={}),
        body=None,
    )

    client = OpenAIClient(
        api_key="test-key",
        client=mock_sdk_client,
        health_monitor=health_monitor,
    )

    with pytest.raises(LLMProviderError, match="rate limited"):
        client.generate([{"role": "user", "content": "Hi"}])

    metrics = health_monitor.get_metrics(ProviderType.OPENAI.value)
    assert metrics.failed_requests == 1


def test_openai_client_generate_with_response_success(health_monitor):
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.return_value = _create_mock_completion(
        content="The Louvre museum is iconic.",
        prompt_tokens=20,
        completion_tokens=30,
    )

    client = OpenAIClient(
        api_key="test-key",
        client=mock_sdk_client,
        health_monitor=health_monitor,
    )

    response = client.generate_with_response([{"role": "user", "content": "Recommend a museum"}])

    assert isinstance(response, LLMResponse)
    assert response.status == LLMResponseStatus.SUCCESS
    assert response.content == "The Louvre museum is iconic."
    assert response.provider == LLMProviderName.OPENAI
    assert response.tokens.total_tokens == 50


def test_openai_client_generate_with_response_rate_limited(health_monitor):
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.side_effect = RateLimitError(
        message="Rate limit exceeded",
        response=Mock(status_code=429, headers={}),
        body=None,
    )

    client = OpenAIClient(
        api_key="test-key",
        client=mock_sdk_client,
        health_monitor=health_monitor,
    )

    response = client.generate_with_response([{"role": "user", "content": "Hi"}])

    assert isinstance(response, LLMResponse)
    assert response.status == LLMResponseStatus.RATE_LIMITED
    assert response.provider == LLMProviderName.OPENAI


def test_openai_client_generate_with_response_timeout(health_monitor):
    mock_sdk_client = MagicMock()
    mock_sdk_client.chat.completions.create.side_effect = APITimeoutError(request=Mock())

    client = OpenAIClient(
        api_key="test-key",
        client=mock_sdk_client,
        health_monitor=health_monitor,
    )

    response = client.generate_with_response([{"role": "user", "content": "Hi"}])

    assert isinstance(response, LLMResponse)
    assert response.status == LLMResponseStatus.TIMEOUT
    assert response.provider == LLMProviderName.OPENAI


def test_fallback_integration_openai_primary_groq_fallback():
    mock_openai = Mock()
    mock_openai.generate.side_effect = LLMProviderError("Azure OpenAI service unavailable")

    mock_groq = Mock()
    mock_groq.generate.return_value = "Groq fallback answer"
    mock_groq.get_last_tokens.return_value = {"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25}

    provider = FallbackLLMProvider(primary=mock_openai, fallback=mock_groq)

    result = provider.generate([{"role": "user", "content": "Hello"}])
    assert result == "Groq fallback answer"
    assert mock_openai.generate.called
    assert mock_groq.generate.called


def test_query_orchestrator_defaults_to_openai_as_primary():
    orchestrator = QueryOrchestrator(
        retrieval=Mock(),
        faq_store=Mock(),
        conversation_logger=Mock(),
    )
    assert isinstance(orchestrator.llm, FallbackLLMProvider)
    assert isinstance(orchestrator.llm.primary, OpenAIClient)
