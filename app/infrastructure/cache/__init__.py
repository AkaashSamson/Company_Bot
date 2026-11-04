"""
Cache Infrastructure Module

Provides swappable cache implementations adhering to SemanticCachePort:
- LangCacheAdapter: Redis LangCache cloud/distributed semantic cache
- DualCache: High-availability composite cache with local JSON fallback
- JSONLocalCache: File-based local cache for offline/isolated usage
- InMemoryQualityAwareCache: In-memory LRU with C.R.E.A.T.E. quality gates and RBAC
- create_cache, get_semantic_cache: Factory methods for dependency injection
"""

from app.domain.ports.cache import CacheEntryProtocol, SemanticCachePort
from app.infrastructure.cache.dual_cache import (
    DualCache,
    DualCacheEntry,
    JSONLocalCache,
    SemanticCache,
    get_dual_cache,
)
from app.infrastructure.cache.factory import (
    create_cache,
    get_semantic_cache,
    reset_cache_instance,
)
from app.infrastructure.cache.langcache_adapter import (
    LANGCACHE_SDK_AVAILABLE,
    LangCacheAdapter,
)
from app.infrastructure.cache.quality_aware_cache import (
    CacheEntry,
    CacheEntryMetadata,
    CacheEntrySource,
    CacheQualityValidator,
    InMemoryQualityAwareCache,
    QualityAwareCache,
    QualityAwareCacheEntry,
    get_quality_cache,
)

__all__ = [
    # Domain Port
    "SemanticCachePort",
    "CacheEntryProtocol",
    # Adapters
    "LangCacheAdapter",
    "DualCache",
    "DualCacheEntry",
    "JSONLocalCache",
    "SemanticCache",
    "InMemoryQualityAwareCache",
    "QualityAwareCache",
    "QualityAwareCacheEntry",
    "CacheEntry",
    "CacheEntryMetadata",
    "CacheEntrySource",
    "CacheQualityValidator",
    # Factories
    "create_cache",
    "get_semantic_cache",
    "get_dual_cache",
    "get_quality_cache",
    "reset_cache_instance",
    "LANGCACHE_SDK_AVAILABLE",
]
