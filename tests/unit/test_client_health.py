import pytest
from unittest.mock import Mock, patch
import httpx

from app.infrastructure.llm.provider_health import (
    ProviderHealthMonitor,
    ProviderType,
    HealthStatus,
)
from app.infrastructure.llm.groq_client import GroqClient
from app.infrastructure.llm.openrouter_client import OpenRouterClient
from app.infrastructure.llm.llm_response import (
    LLMResponse,
    LLMResponseStatus,
    LLMProviderName,
)
from app.domain.services.llm_provider import LLMProviderError


@pytest.fixture
def health_monitor():
    """Create a fresh isolated ProviderHealthMonitor."""
    monitor = ProviderHealthMonitor()
    monitor.reset_all()
    return monitor


def test_groq_client_records_success(health_monitor):
    """Verify GroqClient.generate records success and latency in ProviderHealthMonitor."""
    client = GroqClient(api_key="gsk-test", health_monitor=health_monitor)

    mock_resp = Mock()
    mock_resp.is_error = False
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Groq answer"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    with patch.object(client._client, "post", return_value=mock_resp):
        res = client.generate([{"role": "user", "content": "Hello"}])

    assert res == "Groq answer"
    metrics = health_monitor.get_metrics(ProviderType.GROQ.value)
    assert metrics.total_requests == 1
    assert metrics.successful_requests == 1
    assert metrics.failed_requests == 0
    assert metrics.consecutive_successes == 1
    assert metrics.average_latency_ms >= 0
    assert client.get_last_tokens() == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "model": client.model,
    }


def test_groq_client_records_failure_and_trips_breaker(health_monitor):
    """Verify consecutive failures trip the circuit breaker."""
    client = GroqClient(api_key="gsk-test", health_monitor=health_monitor)

    mock_resp = Mock()
    mock_resp.is_error = True
    mock_resp.status_code = 503
    mock_resp.text = "Service Unavailable"

    with patch.object(client._client, "post", return_value=mock_resp):
        for _ in range(5):
            with pytest.raises(LLMProviderError):
                client.generate([{"role": "user", "content": "Hello"}])

    metrics = health_monitor.get_metrics(ProviderType.GROQ.value)
    assert metrics.failed_requests == 5
    assert metrics.consecutive_failures == 5
    assert health_monitor.get_health_status(ProviderType.GROQ.value) == HealthStatus.DEGRADED

    # Additional 5 failures transitions to UNHEALTHY / OPEN
    with patch.object(client._client, "post", return_value=mock_resp):
        for _ in range(5):
            with pytest.raises(LLMProviderError):
                client.generate([{"role": "user", "content": "Hello"}])

    assert health_monitor.get_health_status(ProviderType.GROQ.value) == HealthStatus.UNHEALTHY
    assert health_monitor.is_provider_available(ProviderType.GROQ.value) is False


def test_groq_client_generate_with_response(health_monitor):
    """Verify generate_with_response returns structured LLMResponse."""
    client = GroqClient(api_key="gsk-test", health_monitor=health_monitor)

    mock_resp = Mock()
    mock_resp.is_error = False
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Structured answer"}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
    }

    with patch.object(client._client, "post", return_value=mock_resp):
        response: LLMResponse = client.generate_with_response([{"role": "user", "content": "Hello"}])

    assert isinstance(response, LLMResponse)
    assert response.status == LLMResponseStatus.SUCCESS
    assert response.content == "Structured answer"
    assert response.provider == LLMProviderName.GROQ
    assert response.tokens.total_tokens == 30


def test_openrouter_client_records_success(health_monitor):
    """Verify OpenRouterClient.generate records success in ProviderHealthMonitor."""
    client = OpenRouterClient(api_key="sk-or-test", health_monitor=health_monitor)

    mock_resp = Mock()
    mock_resp.is_error = False
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "OpenRouter answer"}}],
        "usage": {"prompt_tokens": 15, "completion_tokens": 25, "total_tokens": 40},
    }

    with patch.object(client._client, "post", return_value=mock_resp):
        res = client.generate([{"role": "user", "content": "Hi"}])

    assert res == "OpenRouter answer"
    metrics = health_monitor.get_metrics(ProviderType.OPENROUTER.value)
    assert metrics.total_requests == 1
    assert metrics.successful_requests == 1
    assert metrics.failed_requests == 0


def test_openrouter_client_generate_with_response(health_monitor):
    """Verify OpenRouterClient.generate_with_response returns structured LLMResponse."""
    client = OpenRouterClient(api_key="sk-or-test", health_monitor=health_monitor)

    mock_resp = Mock()
    mock_resp.is_error = False
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Reasoning models output"}}],
        "usage": {"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45},
    }

    with patch.object(client._client, "post", return_value=mock_resp):
        response = client.generate_with_response([{"role": "user", "content": "Hi"}])

    assert isinstance(response, LLMResponse)
    assert response.status == LLMResponseStatus.SUCCESS
    assert response.content == "Reasoning models output"
    assert response.provider == LLMProviderName.OPENROUTER
    assert response.tokens.total_tokens == 45
