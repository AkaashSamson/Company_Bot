"""Unit tests for Groq token standardization to LLMTokenUsage (Task AK-3.3).

Verifies that GroqClient parses OpenAI-compatible usage payloads into
LLMTokenUsage value objects, supports both generate() and generate_with_response(),
and returns None rather than dummy zero tokens when usage data is missing.
"""

import pytest
from app.infrastructure.llm.llm_response import LLMTokenUsage, LLMResponseStatus
from app.infrastructure.llm.groq_client import GroqClient


def test_groq_client_populates_llm_token_usage_on_generate(monkeypatch):
    client = GroqClient(api_key="test-key", model="llama-3.3-70b-versatile")
    fake_response_data = {
        "choices": [{"message": {"content": "Test response"}}],
        "usage": {
            "prompt_tokens": 42,
            "completion_tokens": 18,
            "total_tokens": 60,
        },
    }

    class FakeResponse:
        status_code = 200
        is_error = False
        text = '{"fake": true}'

        def json(self):
            return fake_response_data

    monkeypatch.setattr(client._client, "post", lambda *args, **kwargs: FakeResponse())

    content = client.generate([{"role": "user", "content": "Hello"}])
    assert content == "Test response"

    tokens = client.get_last_token_usage()
    assert tokens is not None
    assert isinstance(tokens, LLMTokenUsage)
    assert tokens.prompt_tokens == 42
    assert tokens.completion_tokens == 18
    assert tokens.total_tokens == 60

    # Backwards compatibility check
    legacy_tokens = client.get_last_tokens()
    assert legacy_tokens == {
        "prompt_tokens": 42,
        "completion_tokens": 18,
        "total_tokens": 60,
        "model": "llama-3.3-70b-versatile",
    }


def test_groq_client_populates_llm_token_usage_on_generate_with_response(monkeypatch):
    client = GroqClient(api_key="test-key", model="llama-3.3-70b-versatile")
    fake_response_data = {
        "choices": [{"message": {"content": "Structured response"}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        },
    }

    class FakeResponse:
        status_code = 200
        is_error = False
        text = '{"fake": true}'

        def json(self):
            return fake_response_data

    monkeypatch.setattr(client._client, "post", lambda *args, **kwargs: FakeResponse())

    res = client.generate_with_response([{"role": "user", "content": "Hello"}])
    assert res.content == "Structured response"
    assert res.status == LLMResponseStatus.SUCCESS

    # 1. Primary accessor: directly from LLMResponse object
    assert res.tokens is not None
    assert isinstance(res.tokens, LLMTokenUsage)
    assert res.tokens.prompt_tokens == 100
    assert res.tokens.completion_tokens == 50
    assert res.tokens.total_tokens == 150

    # 2. State accessor: client state is in sync with response
    assert client.get_last_token_usage() == res.tokens


def test_groq_client_returns_none_when_usage_missing(monkeypatch):
    client = GroqClient(api_key="test-key", model="llama-3.3-70b-versatile")
    fake_response_data = {
        "choices": [{"message": {"content": "Response without usage"}}],
    }

    class FakeResponse:
        status_code = 200
        is_error = False
        text = '{"fake": true}'

        def json(self):
            return fake_response_data

    monkeypatch.setattr(client._client, "post", lambda *args, **kwargs: FakeResponse())

    # Test generate()
    client.generate([{"role": "user", "content": "Hello"}])
    assert client.get_last_token_usage() is None
    assert client.get_last_tokens() is None

    # Test generate_with_response()
    res = client.generate_with_response([{"role": "user", "content": "Hello"}])
    assert res.tokens is None
    assert client.get_last_token_usage() is None
    assert client.get_last_tokens() is None


def test_groq_client_resets_token_usage_on_error(monkeypatch):
    client = GroqClient(api_key="test-key", model="llama-3.3-70b-versatile")

    class FakeErrorResponse:
        status_code = 500
        is_error = True
        text = "Internal Server Error"

        def json(self):
            return {}

    monkeypatch.setattr(client._client, "post", lambda *args, **kwargs: FakeErrorResponse())

    res = client.generate_with_response([{"role": "user", "content": "Hello"}])
    assert res.status == LLMResponseStatus.FAILED
    assert res.tokens is None
    assert client.get_last_token_usage() is None
