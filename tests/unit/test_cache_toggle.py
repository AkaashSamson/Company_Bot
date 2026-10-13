import pytest
from unittest.mock import MagicMock
from app.use_cases.chat.query_orchestrator import QueryOrchestrator
from app.infrastructure.llm.fallback_llm_provider import FallbackLLMProvider
from app.infrastructure.observability.pipeline_tracer import PipelineTracer, PipelineStage


def test_orchestrator_skips_response_and_faq_cache_when_disabled(monkeypatch):
    monkeypatch.setattr("app.core.settings.CACHE_ENABLED", False)
    monkeypatch.setattr("app.core.settings.SEMANTIC_CACHE_ENABLED", False)
    monkeypatch.setattr("app.core.settings.FAQ_SIMILARITY_CACHE_ENABLED", False)
    
    mock_cache = MagicMock()
    orchestrator = QueryOrchestrator(
        response_cache=mock_cache,
    )
    # When CACHE_ENABLED/SEMANTIC_CACHE_ENABLED=False, response_cache must be deactivated/ignored
    assert orchestrator.response_cache is None
    assert orchestrator.faq_cache is None


def test_prompt_lru_cache_disabled_when_llm_cache_disabled(monkeypatch):
    monkeypatch.setattr("app.core.settings.CACHE_ENABLED", False)
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


def test_cache_lookup_span_not_recorded_when_cache_disabled(monkeypatch):
    """When cache is disabled, QueryOrchestrator must NEVER create a CACHE_LOOKUP span in PipelineTracer/Langfuse."""
    monkeypatch.setattr("app.core.settings.CACHE_ENABLED", False)
    monkeypatch.setattr("app.core.settings.SEMANTIC_CACHE_ENABLED", False)
    monkeypatch.setattr("app.core.settings.FAQ_SIMILARITY_CACHE_ENABLED", False)

    tracer = PipelineTracer.create_new(enable_tracing=True)
    mock_retrieval = MagicMock()
    mock_retrieval.retrieve.return_value = [{"text": "Company policy info.", "metadata": {"source": "Handbook.pdf"}}]
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "Here is the policy answer."
    mock_memory = MagicMock()

    orchestrator = QueryOrchestrator(
        retrieval=mock_retrieval,
        llm=mock_llm,
        memory=mock_memory,
        pipeline_tracer=tracer,
        response_cache=MagicMock(),  # explicitly passed, but must be discarded
    )
    assert orchestrator.response_cache is None
    assert orchestrator.faq_cache is None

    res = orchestrator.answer("What is the leave policy?", session_id="test-sess-nocache")
    assert res["cache_hit"] is False

    trace = tracer.get_recent_traces(limit=1)[0]
    recorded_stages = [span.stage for span in trace.spans]

    # NORMALIZATION and retrieval stages run, but CACHE_LOOKUP must NOT be recorded
    assert PipelineStage.NORMALIZATION in recorded_stages
    assert PipelineStage.CACHE_LOOKUP not in recorded_stages


def test_cache_lookup_span_recorded_when_cache_enabled(monkeypatch):
    """When cache is enabled, QueryOrchestrator must record the CACHE_LOOKUP span."""
    monkeypatch.setattr("app.core.settings.CACHE_ENABLED", True)
    monkeypatch.setattr("app.core.settings.SEMANTIC_CACHE_ENABLED", True)

    tracer = PipelineTracer.create_new(enable_tracing=True)
    mock_cache = MagicMock()
    mock_cache.get.return_value = None  # cache miss

    mock_retrieval = MagicMock()
    mock_retrieval.retrieve.return_value = [{"text": "Company policy info.", "metadata": {"source": "Handbook.pdf"}}]
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "Here is the policy answer."

    orchestrator = QueryOrchestrator(
        retrieval=mock_retrieval,
        llm=mock_llm,
        pipeline_tracer=tracer,
        response_cache=mock_cache,
    )
    assert orchestrator.response_cache is mock_cache

    res = orchestrator.answer("What is the leave policy?", session_id="test-sess-cache")
    assert res["cache_hit"] is False

    trace = tracer.get_recent_traces(limit=1)[0]
    recorded_stages = [span.stage for span in trace.spans]

    assert PipelineStage.CACHE_LOOKUP in recorded_stages


def test_master_cache_flag_overrides_env_sub_flags(monkeypatch):
    """Even if sub-flags are set to 'true' in environment variables, CACHE_ENABLED=false overrides and forces all to false."""
    import importlib
    from app.core import settings

    monkeypatch.setenv("CACHE_ENABLED", "false")
    monkeypatch.setenv("SEMANTIC_CACHE_ENABLED", "true")
    monkeypatch.setenv("FAQ_SIMILARITY_CACHE_ENABLED", "true")
    monkeypatch.setenv("LLM_CACHE_ENABLED", "true")
    monkeypatch.setenv("LLM_CACHE_SIZE", "256")

    importlib.reload(settings)

    assert settings.CACHE_ENABLED is False
    assert settings.SEMANTIC_CACHE_ENABLED is False
    assert settings.FAQ_SIMILARITY_CACHE_ENABLED is False
    assert settings.LLM_CACHE_ENABLED is False
    assert settings.LLM_CACHE_SIZE == 0

    # Clean up reload
    monkeypatch.delenv("CACHE_ENABLED", raising=False)
    monkeypatch.delenv("SEMANTIC_CACHE_ENABLED", raising=False)
    monkeypatch.delenv("FAQ_SIMILARITY_CACHE_ENABLED", raising=False)
    monkeypatch.delenv("LLM_CACHE_ENABLED", raising=False)
    monkeypatch.delenv("LLM_CACHE_SIZE", raising=False)
    importlib.reload(settings)

