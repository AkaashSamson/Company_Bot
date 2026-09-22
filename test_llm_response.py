"""
Tests for LLM Response Standardization (AB-2, AB-7)

Tests standardized LLM response objects, provider enums,
and response aggregation.
"""

import pytest
import time
from app.infrastructure.llm.llm_response import (
    LLMResponse,
    LLMResponseBuilder,
    LLMProviderName,
    LLMResponseStatus,
    CacheEntrySource,
    LLMTokenUsage,
    ResponseAggregator,
    get_response_aggregator,
)


class TestLLMTokenUsage:
    """Test LLMTokenUsage dataclass."""
    
    def test_token_usage_creation(self):
        """Test creating token usage."""
        tokens = LLMTokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            cache_hit=False,
        )
        
        assert tokens.prompt_tokens == 100
        assert tokens.completion_tokens == 50
        assert tokens.total_tokens == 150
        assert tokens.cache_hit is False
    
    def test_token_usage_to_dict(self):
        """Test token usage serialization."""
        tokens = LLMTokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
        )
        
        d = tokens.to_dict()
        
        assert d["prompt_tokens"] == 100
        assert d["completion_tokens"] == 50
        assert d["total_tokens"] == 150


class TestLLMResponseStatus:
    """Test LLMResponseStatus enum."""
    
    def test_all_statuses_defined(self):
        """Verify all statuses are defined."""
        statuses = [
            LLMResponseStatus.SUCCESS,
            LLMResponseStatus.PARTIAL,
            LLMResponseStatus.CACHED,
            LLMResponseStatus.FAILED,
            LLMResponseStatus.TIMEOUT,
            LLMResponseStatus.RATE_LIMITED,
        ]
        
        assert len(statuses) == 6
    
    def test_status_values(self):
        """Verify status enum values."""
        assert LLMResponseStatus.SUCCESS.value == "success"
        assert LLMResponseStatus.CACHED.value == "cached"
        assert LLMResponseStatus.FAILED.value == "failed"


class TestLLMProviderName:
    """Test LLMProviderName enum."""
    
    def test_all_providers_defined(self):
        """Verify all providers are defined."""
        providers = [
            LLMProviderName.OPENROUTER,
            LLMProviderName.GROQ,
            LLMProviderName.UNKNOWN,
        ]
        
        assert len(providers) == 3
    
    def test_provider_values(self):
        """Verify provider enum values."""
        assert LLMProviderName.OPENROUTER.value == "openrouter"
        assert LLMProviderName.GROQ.value == "groq"


class TestLLMResponse:
    """Test suite for LLMResponse."""
    
    def test_response_creation(self):
        """Test creating a basic response."""
        response = LLMResponse(
            content="Hello, world!",
            status=LLMResponseStatus.SUCCESS,
            provider=LLMProviderName.OPENROUTER,
            model="claude-3.5-sonnet",
        )
        
        assert response.content == "Hello, world!"
        assert response.status == LLMResponseStatus.SUCCESS
        assert response.provider == LLMProviderName.OPENROUTER
    
    def test_is_successful(self):
        """Test success status check."""
        success_response = LLMResponse(
            content="Test",
            status=LLMResponseStatus.SUCCESS,
        )
        
        cached_response = LLMResponse(
            content="Test",
            status=LLMResponseStatus.CACHED,
        )
        
        failed_response = LLMResponse(
            content="Test",
            status=LLMResponseStatus.FAILED,
        )
        
        assert success_response.is_successful() is True
        assert cached_response.is_successful() is True
        assert failed_response.is_successful() is False
    
    def test_is_cached(self):
        """Test cache check."""
        normal_response = LLMResponse(
            content="Test",
            status=LLMResponseStatus.SUCCESS,
        )
        
        cached_response = LLMResponse(
            content="Test",
            status=LLMResponseStatus.CACHED,
        )
        
        assert normal_response.is_cached() is False
        assert cached_response.is_cached() is True
    
    def test_response_to_dict(self):
        """Test response serialization."""
        tokens = LLMTokenUsage(prompt_tokens=100, completion_tokens=50)
        
        response = LLMResponse(
            content="Test response",
            status=LLMResponseStatus.SUCCESS,
            provider=LLMProviderName.GROQ,
            model="llama-3.1-8b-instant",
            tokens=tokens,
            latency_ms=1500.0,
            citations=[{"source": "doc1"}],
        )
        
        d = response.to_dict()
        
        assert d["content"] == "Test response"
        assert d["status"] == "success"
        assert d["provider"] == "groq"
        assert d["tokens"]["total_tokens"] == 150
        assert len(d["citations"]) == 1
    
    def test_response_from_dict(self):
        """Test deserialization."""
        data = {
            "content": "Test response",
            "status": "success",
            "provider": "openrouter",
            "model": "claude-3.5-sonnet",
            "tokens": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "cache_hit": False,
            },
            "latency_ms": 1500.0,
            "citations": [],
            "metadata": {},
        }
        
        response = LLMResponse.from_dict(data)
        
        assert response.content == "Test response"
        assert response.status == LLMResponseStatus.SUCCESS
        assert response.provider == LLMProviderName.OPENROUTER
        assert response.tokens.total_tokens == 150
    
    def test_from_provider_response_factory(self):
        """Test factory method for provider responses."""
        tokens = LLMTokenUsage(prompt_tokens=200, completion_tokens=100)
        
        response = LLMResponse.from_provider_response(
            content="Generated response",
            provider=LLMProviderName.OPENROUTER,
            model="claude-3.5-sonnet",
            tokens=tokens,
            latency_ms=2000.0,
        )
        
        assert response.content == "Generated response"
        assert response.status == LLMResponseStatus.SUCCESS
        assert response.provider == LLMProviderName.OPENROUTER
        assert response.latency_ms == 2000.0
    
    def test_from_cache_factory(self):
        """Test factory method for cached responses."""
        response = LLMResponse.from_cache(
            content="Cached response",
            cache_source=CacheEntrySource.SEMANTIC_CACHE,
        )
        
        assert response.content == "Cached response"
        assert response.status == LLMResponseStatus.CACHED
        assert response.cache_source == CacheEntrySource.SEMANTIC_CACHE
        assert response.is_cached() is True
        assert response.tokens.cache_hit is True
    
    def test_error_response_factory(self):
        """Test factory method for error responses."""
        response = LLMResponse.error_response(
            error_message="Provider unavailable",
            status=LLMResponseStatus.TIMEOUT,
            provider=LLMProviderName.GROQ,
        )
        
        assert response.content == "Provider unavailable"
        assert response.status == LLMResponseStatus.TIMEOUT
        assert response.is_successful() is False


class TestCacheEntrySource:
    """Test CacheEntrySource enum."""
    
    def test_all_sources_defined(self):
        """Verify all sources are defined."""
        sources = [
            CacheEntrySource.RAG_GENERATED,
            CacheEntrySource.FAQ_MATCHED,
            CacheEntrySource.LLM_CACHED,
            CacheEntrySource.SEMANTIC_CACHE,
        ]
        
        assert len(sources) == 4
    
    def test_source_values(self):
        """Verify source values."""
        assert CacheEntrySource.RAG_GENERATED.value == "rag_generated"
        assert CacheEntrySource.SEMANTIC_CACHE.value == "semantic_cache"


class TestResponseAggregator:
    """Test suite for ResponseAggregator."""
    
    @pytest.fixture(autouse=True)
    def reset_aggregator(self):
        """Reset aggregator before each test."""
        agg = get_response_aggregator()
        agg.reset()
        yield
        agg.reset()
    
    def test_singleton_pattern(self):
        """Test aggregator is singleton."""
        agg1 = get_response_aggregator()
        agg2 = get_response_aggregator()
        
        assert agg1 is agg2
    
    def test_record_successful_response(self):
        """Test recording successful response."""
        agg = get_response_aggregator()
        
        response = LLMResponse(
            content="Test",
            status=LLMResponseStatus.SUCCESS,
            provider=LLMProviderName.OPENROUTER,
            tokens=LLMTokenUsage(prompt_tokens=100, completion_tokens=50),
            latency_ms=1000.0,
        )
        
        agg.record_response(response)
        
        stats = agg.get_provider_stats("openrouter")
        
        assert stats["total_requests"] == 1
        assert stats["success_count"] == 1
        assert stats["failure_count"] == 0
    
    def test_record_failed_response(self):
        """Test recording failed response."""
        agg = get_response_aggregator()
        
        response = LLMResponse(
            content="Error",
            status=LLMResponseStatus.FAILED,
            provider=LLMProviderName.GROQ,
        )
        
        agg.record_response(response)
        
        stats = agg.get_provider_stats("groq")
        
        assert stats["total_requests"] == 1
        assert stats["failure_count"] == 1
    
    def test_record_cached_response(self):
        """Test recording cached response."""
        agg = get_response_aggregator()
        
        response = LLMResponse(
            content="Cached",
            status=LLMResponseStatus.CACHED,
            provider=LLMProviderName.OPENROUTER,
        )
        
        agg.record_response(response)
        
        stats = agg.get_provider_stats("openrouter")
        
        assert stats["cache_hits"] == 1
        assert stats["cache_hit_rate"] == 100.0
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        agg = get_response_aggregator()
        
        # Add 3 successes, 1 failure
        for _ in range(3):
            agg.record_response(LLMResponse(
                content="Test",
                status=LLMResponseStatus.SUCCESS,
                provider=LLMProviderName.OPENROUTER,
            ))
        
        agg.record_response(LLMResponse(
            content="Test",
            status=LLMResponseStatus.FAILED,
            provider=LLMProviderName.OPENROUTER,
        ))
        
        stats = agg.get_provider_stats("openrouter")
        
        assert stats["success_rate"] == 75.0
    
    def test_global_stats(self):
        """Test global statistics."""
        agg = get_response_aggregator()
        
        agg.record_response(LLMResponse(
            content="Test",
            status=LLMResponseStatus.SUCCESS,
            provider=LLMProviderName.OPENROUTER,
            tokens=LLMTokenUsage(prompt_tokens=100, completion_tokens=50),
        ))
        
        agg.record_response(LLMResponse(
            content="Test",
            status=LLMResponseStatus.CACHED,
            provider=LLMProviderName.GROQ,
        ))
        
        global_stats = agg.get_global_stats()
        
        assert global_stats["total_requests"] == 2
        assert global_stats["total_success"] == 1
        assert global_stats["total_cache_hits"] == 1
    
    def test_average_latency(self):
        """Test average latency calculation."""
        agg = get_response_aggregator()
        
        agg.record_response(LLMResponse(
            content="Test",
            status=LLMResponseStatus.SUCCESS,
            provider=LLMProviderName.OPENROUTER,
            latency_ms=1000.0,
        ))
        
        agg.record_response(LLMResponse(
            content="Test",
            status=LLMResponseStatus.SUCCESS,
            provider=LLMProviderName.OPENROUTER,
            latency_ms=2000.0,
        ))
        
        stats = agg.get_provider_stats("openrouter")
        
        assert stats["avg_latency_ms"] == 1500.0
    
    def test_reset_provider(self):
        """Test resetting provider stats."""
        agg = get_response_aggregator()
        
        agg.record_response(LLMResponse(
            content="Test",
            status=LLMResponseStatus.SUCCESS,
            provider=LLMProviderName.OPENROUTER,
        ))
        
        agg.reset("openrouter")
        
        stats = agg.get_provider_stats("openrouter")
        
        assert stats == {}


class TestLLMResponseBuilder:
    """Test suite for LLMResponseBuilder."""
    
    def test_fluent_builder(self):
        """Test building LLMResponse using fluent builder methods."""
        builder = LLMResponseBuilder()
        response = (
            builder
            .with_content("Builder response")
            .with_provider(LLMProviderName.OPENROUTER)
            .with_model("claude-3.5-sonnet")
            .with_tokens(prompt_tokens=120, completion_tokens=80)
            .with_latency(1450.0)
            .with_status(LLMResponseStatus.SUCCESS)
            .with_citations([{"doc_id": "hr_01"}])
            .with_metadata({"custom_flag": True})
            .build()
        )
        
        assert response.content == "Builder response"
        assert response.provider == LLMProviderName.OPENROUTER
        assert response.model == "claude-3.5-sonnet"
        assert response.status == LLMResponseStatus.SUCCESS
        assert response.tokens.prompt_tokens == 120
        assert response.tokens.completion_tokens == 80
        assert response.tokens.total_tokens == 200
        assert response.latency_ms == 1450.0
        assert len(response.citations) == 1
        assert response.metadata["custom_flag"] is True
        assert response.is_successful() is True
    
    def test_fluent_builder_string_conversions(self):
        """Test builder accepts string representations of enums."""
        response = (
            LLMResponseBuilder()
            .with_content("Converted enums")
            .with_provider("groq")
            .with_status("cached")
            .with_cache_source("semantic_cache")
            .add_citation({"source": "handbook.pdf"})
            .add_metadata("key", "val")
            .build()
        )
        
        assert response.provider == LLMProviderName.GROQ
        assert response.status == LLMResponseStatus.CACHED
        assert response.cache_source == CacheEntrySource.SEMANTIC_CACHE
        assert len(response.citations) == 1
        assert response.metadata["key"] == "val"
        assert response.is_cached() is True

    def test_static_factory_success(self):
        """Test static factory success method."""
        response = LLMResponseBuilder.success(
            content="Static success",
            provider=LLMProviderName.GROQ,
            model="llama-3.1-8b-instant",
            latency_ms=350.0,
        )
        
        assert response.content == "Static success"
        assert response.status == LLMResponseStatus.SUCCESS
        assert response.provider == LLMProviderName.GROQ
        assert response.is_successful() is True

    def test_static_factory_cached(self):
        """Test static factory cached method."""
        response = LLMResponseBuilder.cached(
            content="Static cached",
            cache_source=CacheEntrySource.FAQ_MATCHED,
        )
        
        assert response.content == "Static cached"
        assert response.status == LLMResponseStatus.CACHED
        assert response.cache_source == CacheEntrySource.FAQ_MATCHED
        assert response.is_cached() is True
        assert response.tokens.cache_hit is True

    def test_static_factory_error(self):
        """Test static factory error method."""
        response = LLMResponseBuilder.error(
            error_message="Gateway timeout",
            status=LLMResponseStatus.TIMEOUT,
            provider=LLMProviderName.OPENROUTER,
        )
        
        assert response.content == "Gateway timeout"
        assert response.status == LLMResponseStatus.TIMEOUT
        assert response.provider == LLMProviderName.OPENROUTER
        assert response.is_successful() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])