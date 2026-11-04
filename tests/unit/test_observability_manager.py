from typing import Generator
import pytest

from app.domain.ports.observability import (
    BaseObservabilityProvider,
    ObservabilityPort,
    TokenUsage,
    TraceSpanPort,
)
from app.infrastructure.observability.langfuse_provider import LangfuseProvider, LangfuseSpan
from app.infrastructure.observability.manager import (
    ObservabilityManager,
    get_observability_manager,
    reset_observability_manager,
)
from app.infrastructure.observability.null_provider import (
    NullObservabilityProvider,
    NullSpan,
)
from app.infrastructure.observability.phoenix_provider import (
    PhoenixProvider,
    PhoenixSpan,
)


@pytest.fixture(autouse=True)
def clean_manager_singleton() -> Generator[None, None, None]:
    """Ensure singleton is reset before and after every test."""
    reset_observability_manager()
    yield
    reset_observability_manager()


class TestObservabilityManager:
    """Verifies ObservabilityManager routing, protocol compliance, and dynamic switching."""

    def test_manager_adheres_to_base_observability_provider_protocol(self) -> None:
        manager = ObservabilityManager()
        assert isinstance(manager, BaseObservabilityProvider)
        assert isinstance(manager, ObservabilityPort)

    def test_default_initializes_to_null_provider_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core import settings
        monkeypatch.setattr(settings, "OBSERVABILITY_PROVIDER", "null")
        manager = ObservabilityManager()
        assert isinstance(manager.active_provider, NullObservabilityProvider)

    def test_switch_provider_to_langfuse(self) -> None:
        manager = ObservabilityManager()
        manager.switch_provider("langfuse")
        assert isinstance(manager.active_provider, LangfuseProvider)
        assert isinstance(manager.active_provider, BaseObservabilityProvider)

    def test_switch_provider_to_phoenix(self) -> None:
        manager = ObservabilityManager()
        manager.switch_provider("phoenix")
        assert isinstance(manager.active_provider, PhoenixProvider)
        assert isinstance(manager.active_provider, BaseObservabilityProvider)

    def test_switch_provider_back_to_null(self) -> None:
        manager = ObservabilityManager()
        manager.switch_provider("phoenix")
        manager.switch_provider("null")
        assert isinstance(manager.active_provider, NullObservabilityProvider)

    def test_switch_provider_unknown_defaults_safely_to_null(self) -> None:
        manager = ObservabilityManager()
        manager.switch_provider("unsupported_telemetry_vendor_xyz")
        assert isinstance(manager.active_provider, NullObservabilityProvider)

    def test_custom_provider_injection(self) -> None:
        custom_provider = PhoenixProvider(project_name="custom-test")
        manager = ObservabilityManager(provider=custom_provider)
        assert manager.active_provider is custom_provider

        # Test manual setter
        null_prov = NullObservabilityProvider()
        manager.set_provider(null_prov)
        assert manager.active_provider is null_prov

    def test_singleton_get_and_reset(self) -> None:
        mgr1 = get_observability_manager()
        mgr2 = get_observability_manager()
        assert mgr1 is mgr2

        reset_observability_manager()
        mgr3 = get_observability_manager()
        assert mgr3 is not mgr1

    def test_delegated_span_creation_and_context_management(self) -> None:
        manager = ObservabilityManager()
        manager.switch_provider("phoenix")

        with manager.create_trace("test_pipeline_run", session_id="sess_123") as span:
            assert isinstance(span, TraceSpanPort)
            assert isinstance(span, PhoenixSpan)
            assert span.is_ended is False

        assert span.is_ended is True

    def test_delegated_llm_token_recording(self) -> None:
        phoenix = PhoenixProvider()
        manager = ObservabilityManager(provider=phoenix)

        usage = TokenUsage(prompt_tokens=150, completion_tokens=50)
        manager.record_llm_call(
            model="groq/llama-3.1-8b-instant",
            token_usage=usage,
            latency_ms=320.5,
            metadata={"caller": "test"},
        )

        stats = phoenix.get_stats()
        assert stats["recorded_llm_calls"] == 1

        manager.flush()
        assert phoenix.get_stats()["recorded_llm_calls"] == 0


class TestLangfuseProvider:
    """Verifies LangfuseProvider behavior in offline / mock mode."""

    def test_langfuse_implements_protocol(self) -> None:
        provider = LangfuseProvider()
        assert isinstance(provider, BaseObservabilityProvider)

    def test_langfuse_span_lifecycle(self) -> None:
        provider = LangfuseProvider(enabled=False)
        span = provider.create_trace(
            name="query_flow",
            session_id="session_abc",
            user_id="user_xyz",
            metadata={"step": "vector_search"},
        )
        assert isinstance(span, LangfuseSpan)
        assert isinstance(span, TraceSpanPort)
        assert span.is_ended is False

        with span:
            pass
        assert span.is_ended is True

    def test_langfuse_record_llm_call(self) -> None:
        provider = LangfuseProvider(enabled=False)
        usage = TokenUsage(prompt_tokens=80, completion_tokens=20)
        provider.record_llm_call("claude-3-5-sonnet", usage, latency_ms=450.0)
        # Should flush gracefully with zero errors in dry-run mode
        provider.flush()


class TestPhoenixProvider:
    """Verifies PhoenixProvider span recording and OpenInference attributes."""

    def test_phoenix_implements_protocol(self) -> None:
        provider = PhoenixProvider()
        assert isinstance(provider, BaseObservabilityProvider)

    def test_phoenix_span_lifecycle_and_stats(self) -> None:
        provider = PhoenixProvider(project_name="test-project")
        with provider.create_trace("chat_turn") as span:
            assert isinstance(span, PhoenixSpan)
            assert isinstance(span, TraceSpanPort)

        stats = provider.get_stats()
        assert stats["active_spans"] == 1
        assert stats["project_name"] == "test-project"

        provider.flush()
        assert provider.get_stats()["active_spans"] == 0

    def test_phoenix_openinference_attributes(self) -> None:
        provider = PhoenixProvider()
        usage = TokenUsage(prompt_tokens=200, completion_tokens=100)
        provider.record_llm_call("llama-3", usage, latency_ms=210.0)

        # Inspect recorded call internal data
        assert len(provider._llm_calls) == 1
        call_record = provider._llm_calls[0]
        assert call_record["openinference_attributes"]["llm.token_count.total"] == 300
        assert call_record["openinference_attributes"]["llm.model_name"] == "llama-3"
