"""
Standardized LLM Response Objects

Provides unified response structures across all LLM providers:
- LLMResponse: Standardized response with status, metadata, and tokens
- LLMProviderName enum: Consistent provider identification
- LLMResponseStatus enum: Standard response states
- ResponseAggregator: Cross-provider statistics and aggregation
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LLMProviderName(Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    GROQ = "groq"
    UNKNOWN = "unknown"


class LLMResponseStatus(Enum):
    """Standard response status codes."""
    SUCCESS = "success"
    PARTIAL = "partial"
    CACHED = "cached"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"


class CacheEntrySource(Enum):
    """Source of cached response."""
    RAG_GENERATED = "rag_generated"
    FAQ_MATCHED = "faq_matched"
    LLM_CACHED = "llm_cached"
    SEMANTIC_CACHE = "semantic_cache"


@dataclass
class LLMTokenUsage:
    """Token usage information from LLM response."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_hit: bool = False
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        total = self.total_tokens
        if total == 0:
            total = self.prompt_tokens + self.completion_tokens
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": total,
            "cache_hit": self.cache_hit,
        }


@dataclass
class LLMResponse:
    """
    Standardized LLM response object.
    
    Provides consistent structure across all providers with:
    - Response content and status
    - Token usage tracking
    - Provider identification
    - Timing information
    - Metadata for debugging
    """
    content: str
    status: LLMResponseStatus = LLMResponseStatus.SUCCESS
    provider: LLMProviderName = LLMProviderName.UNKNOWN
    model: str = ""
    tokens: Optional[LLMTokenUsage] = None
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    cache_source: Optional[CacheEntrySource] = None
    citations: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def is_successful(self) -> bool:
        """Check if response was successful."""
        return self.status in (
            LLMResponseStatus.SUCCESS,
            LLMResponseStatus.CACHED,
        )
    
    def is_cached(self) -> bool:
        """Check if response came from cache."""
        return self.status == LLMResponseStatus.CACHED
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "content": self.content,
            "status": self.status.value,
            "provider": self.provider.value,
            "model": self.model,
            "tokens": self.tokens.to_dict() if self.tokens else None,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
            "cache_source": self.cache_source.value if self.cache_source else None,
            "citations": self.citations,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'LLMResponse':
        """Create LLMResponse from dictionary."""
        tokens_data = data.get("tokens")
        tokens = None
        if tokens_data:
            tokens = LLMTokenUsage(**tokens_data)
        
        cache_source = data.get("cache_source")
        if cache_source:
            cache_source = CacheEntrySource(cache_source)
        
        return cls(
            content=data.get("content", ""),
            status=LLMResponseStatus(data.get("status", "success")),
            provider=LLMProviderName(data.get("provider", "unknown")),
            model=data.get("model", ""),
            tokens=tokens,
            latency_ms=data.get("latency_ms", 0.0),
            timestamp=data.get("timestamp", time.time()),
            cache_source=cache_source,
            citations=data.get("citations", []),
            metadata=data.get("metadata", {}),
        )
    
    @classmethod
    def from_provider_response(
        cls,
        content: str,
        provider: LLMProviderName,
        model: str,
        tokens: Optional[LLMTokenUsage] = None,
        latency_ms: float = 0.0,
        **kwargs,
    ) -> 'LLMResponse':
        """Factory method to create response from provider output."""
        return cls(
            content=content,
            status=LLMResponseStatus.SUCCESS,
            provider=provider,
            model=model,
            tokens=tokens,
            latency_ms=latency_ms,
            **kwargs,
        )
    
    @classmethod
    def from_cache(
        cls,
        content: str,
        cache_source: CacheEntrySource,
        **kwargs,
    ) -> 'LLMResponse':
        """Factory method to create cached response."""
        tokens = LLMTokenUsage(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cache_hit=True,
        )
        return cls(
            content=content,
            status=LLMResponseStatus.CACHED,
            provider=LLMProviderName.UNKNOWN,
            tokens=tokens,
            cache_source=cache_source,
            latency_ms=0.0,
            **kwargs,
        )
    
    @classmethod
    def error_response(
        cls,
        error_message: str,
        status: LLMResponseStatus = LLMResponseStatus.FAILED,
        provider: LLMProviderName = LLMProviderName.UNKNOWN,
        **kwargs,
    ) -> 'LLMResponse':
        """Factory method to create error response."""
        return cls(
            content=error_message,
            status=status,
            provider=provider,
            **kwargs,
        )


class LLMResponseBuilder:
    """
    Builder and factory for LLMResponse objects.
    
    Supports both fluent builder chaining and static factory shortcuts:
    - Fluent: LLMResponseBuilder().with_content(...).with_provider(...).build()
    - Static: LLMResponseBuilder.success(...), LLMResponseBuilder.cached(...), LLMResponseBuilder.error(...)
    """

    def __init__(self):
        self._content: str = ""
        self._status: LLMResponseStatus = LLMResponseStatus.SUCCESS
        self._provider: LLMProviderName = LLMProviderName.UNKNOWN
        self._model: str = ""
        self._tokens: Optional[LLMTokenUsage] = None
        self._latency_ms: float = 0.0
        self._timestamp: float = time.time()
        self._cache_source: Optional[CacheEntrySource] = None
        self._citations: list[dict] = []
        self._metadata: dict[str, Any] = {}

    def with_content(self, content: str) -> 'LLMResponseBuilder':
        self._content = content
        return self

    def with_status(self, status: LLMResponseStatus | str) -> 'LLMResponseBuilder':
        if isinstance(status, str):
            status = LLMResponseStatus(status)
        self._status = status
        return self

    def with_provider(self, provider: LLMProviderName | str) -> 'LLMResponseBuilder':
        if isinstance(provider, str):
            provider = LLMProviderName(provider)
        self._provider = provider
        return self

    def with_model(self, model: str) -> 'LLMResponseBuilder':
        self._model = model
        return self

    def with_tokens(
        self,
        tokens: Optional[LLMTokenUsage] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        cache_hit: bool = False,
    ) -> 'LLMResponseBuilder':
        if tokens is not None:
            self._tokens = tokens
        else:
            self._tokens = LLMTokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens or (prompt_tokens + completion_tokens),
                cache_hit=cache_hit,
            )
        return self

    def with_latency(self, latency_ms: float) -> 'LLMResponseBuilder':
        self._latency_ms = latency_ms
        return self

    def with_timestamp(self, timestamp: float) -> 'LLMResponseBuilder':
        self._timestamp = timestamp
        return self

    def with_cache_source(self, cache_source: Optional[CacheEntrySource | str]) -> 'LLMResponseBuilder':
        if isinstance(cache_source, str):
            cache_source = CacheEntrySource(cache_source)
        self._cache_source = cache_source
        return self

    def with_citations(self, citations: list[dict]) -> 'LLMResponseBuilder':
        self._citations = list(citations)
        return self

    def add_citation(self, citation: dict) -> 'LLMResponseBuilder':
        self._citations.append(citation)
        return self

    def with_metadata(self, metadata: dict[str, Any]) -> 'LLMResponseBuilder':
        self._metadata = dict(metadata)
        return self

    def add_metadata(self, key: str, value: Any) -> 'LLMResponseBuilder':
        self._metadata[key] = value
        return self

    def build(self) -> LLMResponse:
        return LLMResponse(
            content=self._content,
            status=self._status,
            provider=self._provider,
            model=self._model,
            tokens=self._tokens,
            latency_ms=self._latency_ms,
            timestamp=self._timestamp,
            cache_source=self._cache_source,
            citations=self._citations,
            metadata=self._metadata,
        )

    # Static factory convenience methods
    @staticmethod
    def success(
        content: str,
        provider: LLMProviderName = LLMProviderName.UNKNOWN,
        model: str = "",
        tokens: Optional[LLMTokenUsage] = None,
        latency_ms: float = 0.0,
        citations: Optional[list[dict]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> LLMResponse:
        """Create a successful response."""
        return LLMResponse(
            content=content,
            status=LLMResponseStatus.SUCCESS,
            provider=provider,
            model=model,
            tokens=tokens,
            latency_ms=latency_ms,
            citations=citations or [],
            metadata=metadata or {},
        )

    @staticmethod
    def cached(
        content: str,
        cache_source: CacheEntrySource = CacheEntrySource.SEMANTIC_CACHE,
        citations: Optional[list[dict]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> LLMResponse:
        """Create a cached response."""
        return LLMResponse.from_cache(
            content=content,
            cache_source=cache_source,
            citations=citations or [],
            metadata=metadata or {},
        )

    @staticmethod
    def error(
        error_message: str,
        status: LLMResponseStatus = LLMResponseStatus.FAILED,
        provider: LLMProviderName = LLMProviderName.UNKNOWN,
        metadata: Optional[dict[str, Any]] = None,
    ) -> LLMResponse:
        """Create an error response."""
        return LLMResponse.error_response(
            error_message=error_message,
            status=status,
            provider=provider,
            metadata=metadata or {},
        )

    @staticmethod
    def from_provider_response(
        content: str,
        provider: LLMProviderName,
        model: str,
        tokens: Optional[LLMTokenUsage] = None,
        latency_ms: float = 0.0,
        **kwargs,
    ) -> LLMResponse:
        return LLMResponse.from_provider_response(
            content=content,
            provider=provider,
            model=model,
            tokens=tokens,
            latency_ms=latency_ms,
            **kwargs,
        )

    @staticmethod
    def from_cache(
        content: str,
        cache_source: CacheEntrySource,
        **kwargs,
    ) -> LLMResponse:
        return LLMResponse.from_cache(
            content=content,
            cache_source=cache_source,
            **kwargs,
        )

    @staticmethod
    def error_response(
        error_message: str,
        status: LLMResponseStatus = LLMResponseStatus.FAILED,
        provider: LLMProviderName = LLMProviderName.UNKNOWN,
        **kwargs,
    ) -> LLMResponse:
        return LLMResponse.error_response(
            error_message=error_message,
            status=status,
            provider=provider,
            **kwargs,
        )


@dataclass 
class ResponseAggregator:
    """
    Aggregates response statistics across multiple LLM calls.
    
    Tracks:
    - Total requests by provider
    - Success/failure counts
    - Token usage totals and averages
    - Latency statistics
    - Cache hit rates
    """
    
    _instance = None
    
    def __new__(cls) -> 'ResponseAggregator':
        """Singleton pattern for global aggregation."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._provider_stats: dict[str, dict] = {}
        self._total_requests = 0
        self._total_success = 0
        self._total_failure = 0
        self._total_cache_hits = 0
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._total_latency_ms = 0.0
        self._initialized = True
        
        logger.info("response_aggregator initialized")
    
    def record_response(self, response: LLMResponse) -> None:
        """Record a response for aggregation."""
        provider = response.provider.value
        
        # Initialize provider stats if needed
        if provider not in self._provider_stats:
            self._provider_stats[provider] = {
                "requests": 0,
                "success": 0,
                "failure": 0,
                "cache_hits": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_latency_ms": 0.0,
            }
        
        stats = self._provider_stats[provider]
        stats["requests"] += 1
        self._total_requests += 1
        
        if response.status == LLMResponseStatus.SUCCESS:
            stats["success"] += 1
            self._total_success += 1
        elif response.status == LLMResponseStatus.CACHED:
            # Cached is a "success" but not counted in total_success for global stats
            stats["cache_hits"] += 1
            self._total_cache_hits += 1
        elif response.is_successful():
            stats["success"] += 1
            self._total_success += 1
        else:
            stats["failure"] += 1
            self._total_failure += 1
        
        if response.tokens:
            stats["prompt_tokens"] += response.tokens.prompt_tokens
            stats["completion_tokens"] += response.tokens.completion_tokens
            self._total_prompt_tokens += response.tokens.prompt_tokens
            self._total_completion_tokens += response.tokens.completion_tokens
        
        stats["total_latency_ms"] += response.latency_ms
        self._total_latency_ms += response.latency_ms
    
    def get_provider_stats(self, provider: str) -> dict:
        """Get aggregated stats for a specific provider."""
        stats = self._provider_stats.get(provider, {})
        if not stats:
            return {}
        
        requests = stats.get("requests", 0)
        return {
            "provider": provider,
            "total_requests": requests,
            "success_count": stats.get("success", 0),
            "failure_count": stats.get("failure", 0),
            "cache_hits": stats.get("cache_hits", 0),
            "success_rate": (stats.get("success", 0) / requests * 100) if requests > 0 else 0,
            "cache_hit_rate": (stats.get("cache_hits", 0) / requests * 100) if requests > 0 else 0,
            "total_prompt_tokens": stats.get("prompt_tokens", 0),
            "total_completion_tokens": stats.get("completion_tokens", 0),
            "total_tokens": stats.get("prompt_tokens", 0) + stats.get("completion_tokens", 0),
            "avg_latency_ms": stats.get("total_latency_ms", 0) / requests if requests > 0 else 0,
        }
    
    def get_global_stats(self) -> dict:
        """Get global aggregated stats."""
        if self._total_requests == 0:
            return {
                "total_requests": 0,
                "total_success": 0,
                "total_failure": 0,
                "total_cache_hits": 0,
                "success_rate": 0.0,
                "cache_hit_rate": 0.0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "avg_latency_ms": 0.0,
            }
        
        return {
            "total_requests": self._total_requests,
            "total_success": self._total_success,
            "total_failure": self._total_failure,
            "total_cache_hits": self._total_cache_hits,
            "success_rate": (self._total_success / self._total_requests * 100) if self._total_requests > 0 else 0,
            "cache_hit_rate": (self._total_cache_hits / self._total_requests * 100) if self._total_requests > 0 else 0,
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens,
            "total_tokens": self._total_prompt_tokens + self._total_completion_tokens,
            "avg_latency_ms": self._total_latency_ms / self._total_requests if self._total_requests > 0 else 0,
        }
    
    def get_all_provider_stats(self) -> list[dict]:
        """Get stats for all providers."""
        return [
            self.get_provider_stats(provider)
            for provider in self._provider_stats.keys()
        ]
    
    def reset(self, provider: Optional[str] = None) -> None:
        """Reset aggregated stats."""
        if provider:
            self._provider_stats.pop(provider, None)
        else:
            self._provider_stats.clear()
            self._total_requests = 0
            self._total_success = 0
            self._total_failure = 0
            self._total_cache_hits = 0
            self._total_prompt_tokens = 0
            self._total_completion_tokens = 0
            self._total_latency_ms = 0.0
        
        logger.info("response_stats_reset provider=%s", provider or "all")


# Global singleton instance
_response_aggregator: Optional[ResponseAggregator] = None


def get_response_aggregator() -> ResponseAggregator:
    """Get the global response aggregator instance."""
    global _response_aggregator
    if _response_aggregator is None:
        _response_aggregator = ResponseAggregator()
    return _response_aggregator