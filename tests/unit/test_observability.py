from dataclasses import FrozenInstanceError
import pytest

from app.domain.ports.observability import (
    BaseObservabilityProvider,
    ObservabilityPort,
    TokenUsage,
    TraceSpanPort,
)
from app.infrastructure.observability.provider import (
    NullObservabilityProvider,
    NullSpan,
)


def test_token_usage_auto_calculates_total():
    usage = TokenUsage(prompt_tokens=15, completion_tokens=25)
    assert usage.prompt_tokens == 15
    assert usage.completion_tokens == 25
    assert usage.total_tokens == 40


def test_token_usage_preserves_explicit_total():
    usage = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=50)
    assert usage.total_tokens == 50


def test_token_usage_is_immutable():
    usage = TokenUsage(prompt_tokens=10, completion_tokens=20)
    with pytest.raises(FrozenInstanceError):
        usage.prompt_tokens = 99  # type: ignore[misc]


def test_null_span_manual_lifecycle():
    span = NullSpan(name="retrieval")
    assert span.is_ended is False

    span.end(outputs={"chunks": 4})
    assert span.is_ended is True
    assert span.outputs == {"chunks": 4}
    assert span.error is None


def test_null_span_context_manager_success():
    with NullSpan(name="llm_call") as span:
        # Simulate work
        pass

    assert span.is_ended is True
    assert span.error is None


def test_null_span_context_manager_captures_error():
    with pytest.raises(RuntimeError):
        with NullSpan(name="failing_step") as span:
            raise RuntimeError("API timeout")

    assert span.is_ended is True
    assert "API timeout" in str(span.error)


def test_null_provider_runs_safely():
    provider = NullObservabilityProvider()

    span = provider.create_trace(
        name="test_trace",
        session_id="session_123",
        user_id="user_456",
        metadata={"channel": "teams"},
    )
    assert isinstance(span, TraceSpanPort)
    span.end()

    # Record LLM call with token usage
    usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
    provider.record_llm_call(
        model="groq/llama-3.3-70b-versatile",
        token_usage=usage,
        latency_ms=250.5,
        metadata={"purpose": "query_resolution"},
    )

    # Flush
    provider.flush()


def test_custom_provider_matches_protocol():
    """Verify Open/Closed principle: custom vendor provider satisfies BaseObservabilityProvider protocol."""

    class MockCustomProvider(BaseObservabilityProvider):
        def __init__(self):
            self.logged_calls = []

        def create_trace(self, name, session_id=None, user_id=None, metadata=None):
            return NullSpan(name=name)

        def record_llm_call(self, model, token_usage, latency_ms=0.0, metadata=None):
            self.logged_calls.append({"model": model, "usage": token_usage, "latency_ms": latency_ms})

        def flush(self):
            pass

    provider = MockCustomProvider()
    assert isinstance(provider, BaseObservabilityProvider)
    assert isinstance(provider, ObservabilityPort)

    provider.record_llm_call("test-model", TokenUsage(5, 5), latency_ms=10.0)
    assert len(provider.logged_calls) == 1
    assert provider.logged_calls[0]["usage"].total_tokens == 10
