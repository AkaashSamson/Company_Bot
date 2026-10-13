import pytest
from unittest.mock import MagicMock
from app.use_cases.chat.query_orchestrator import QueryOrchestrator
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider


def test_orchestrator_skips_response_and_faq_cache_when_disabled(monkeypatch):
    monkeypatch.setattr("app.core.settings.SEMANTIC_CACHE_ENABLED", False)
    monkeypatch.setattr("app.core.settings.FAQ_SIMILARITY_CACHE_ENABLED", False)
    
    mock_cache = MagicMock()
    orchestrator = QueryOrchestrator(
        response_cache=mock_cache,
    )
    # When SEMANTIC_CACHE_ENABLED=False, response_cache must be deactivated/ignored
    assert orchestrator.response_cache is None
    assert orchestrator.faq_cache is None


def test_prompt_lru_cache_disabled_when_llm_cache_disabled(monkeypatch):
    monkeypatch.setattr("app.core.settings.LLM_CACHE_ENABLED", False)
    monkeypatch.setattr("app.core.settings.LLM_CACHE_SIZE", 0)

    provider = FallbackLLMProvider(
        primary=MagicMock(),
        fallback=MagicMock(),
    )
    assert provider.cache.maxsize == 0
    # maxsize=0 must never store or return hits
    provider.cache.put([{"role": "user", "content": "hi"}], "hello")
    assert provider.cache.get([{"role": "user", "content": "hi"}]) is None
