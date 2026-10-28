"""
Cache Factory and Dependency Injection Module

Provides loosely-coupled creation and retrieval of cache implementations.
Decouples application use cases (such as QueryOrchestrator and API routes)
from concrete cache providers (LangCache, DualCache, InMemoryQualityAwareCache, JSONLocalCache).
"""

import logging
from typing import Any, Dict, Optional

from app.core.settings import (
    DUAL_CACHE_JSON_FALLBACK_ENABLED,
    DUAL_CACHE_JSON_FILE_PATH,
    DUAL_CACHE_SYNC_INTERVAL_SECONDS,
    DUAL_CACHE_SYNC_ON_WRITE,
    LANGCACHE_API_KEY,
    LANGCACHE_CACHE_ID,
    LANGCACHE_ENABLED,
    LANGCACHE_SERVER_URL,
    LANGCACHE_SIMILARITY_THRESHOLD,
    LANGCACHE_TIMEOUT_SECONDS,
    SEMANTIC_CACHE_ENABLED,
    SEMANTIC_CACHE_MAX_ENTRIES,
    SEMANTIC_CACHE_MIN_CONFIDENCE,
    SEMANTIC_CACHE_TTL_SECONDS,
)
from app.domain.ports.cache import SemanticCachePort
from app.infrastructure.cache.dual_cache import (
    DualCache,
    JSONLocalCache,
)
from app.infrastructure.cache.langcache_adapter import LangCacheAdapter
from app.infrastructure.cache.quality_aware_cache import InMemoryQualityAwareCache

logger = logging.getLogger(__name__)

# Global singleton cache instance
_cache_instance: Optional[Any] = None


def create_cache(
    backend: Optional[str] = None,
    langcache_server_url: Optional[str] = None,
    langcache_cache_id: Optional[str] = None,
    langcache_api_key: Optional[str] = None,
    similarity_threshold: Optional[float] = None,
    fallback_path: Optional[str] = None,
    enable_sync: bool = True,
    primary_adapter: Optional[Any] = None,
    fallback_adapter: Optional[Any] = None,
    **kwargs: Any,
) -> Any:
    """
    Factory method to create a cache instance based on backend type and settings.
    
    Supported backends:
    - 'dual' (default when LANGCACHE_ENABLED=true): LangCache primary + JSON fallback
    - 'langcache': Direct LangCacheAdapter
    - 'memory' / 'quality': InMemoryQualityAwareCache
    - 'json': JSONLocalCache
    
    Returns an instance adhering to SemanticCachePort.
    """
    if not SEMANTIC_CACHE_ENABLED:
        logger.info("create_cache: SEMANTIC_CACHE_ENABLED is False, cache disabled.")
        return None

    selected_backend = (backend or "").lower().strip()
    if not selected_backend:
        if LANGCACHE_ENABLED and (langcache_api_key or LANGCACHE_API_KEY):
            selected_backend = "dual"
        else:
            selected_backend = "quality"

    logger.info("create_cache backend=%s", selected_backend)

    if selected_backend in ("none", "disabled", "false"):
        return None

    if selected_backend == "langcache":
        return LangCacheAdapter(
            server_url=langcache_server_url or LANGCACHE_SERVER_URL,
            cache_id=langcache_cache_id or LANGCACHE_CACHE_ID,
            api_key=langcache_api_key or LANGCACHE_API_KEY,
            similarity_threshold=similarity_threshold or LANGCACHE_SIMILARITY_THRESHOLD,
            timeout_seconds=LANGCACHE_TIMEOUT_SECONDS,
        )

    elif selected_backend == "dual":
        primary = primary_adapter
        if primary is None:
            primary = LangCacheAdapter(
                server_url=langcache_server_url or LANGCACHE_SERVER_URL,
                cache_id=langcache_cache_id or LANGCACHE_CACHE_ID,
                api_key=langcache_api_key or LANGCACHE_API_KEY,
                similarity_threshold=similarity_threshold or LANGCACHE_SIMILARITY_THRESHOLD,
                timeout_seconds=LANGCACHE_TIMEOUT_SECONDS,
            )

        fallback = fallback_adapter
        if fallback is None and DUAL_CACHE_JSON_FALLBACK_ENABLED:
            target_path = fallback_path or DUAL_CACHE_JSON_FILE_PATH
            fallback = JSONLocalCache(file_path=target_path)

        return DualCache(
            primary_cache=primary,
            fallback_cache=fallback,
            enable_sync=enable_sync,
            sync_interval=DUAL_CACHE_SYNC_INTERVAL_SECONDS,
        )

    elif selected_backend == "json":
        target_path = fallback_path or DUAL_CACHE_JSON_FILE_PATH
        return JSONLocalCache(file_path=target_path)

    elif selected_backend in ("memory", "quality"):
        return InMemoryQualityAwareCache(
            max_entries=kwargs.get("max_entries", SEMANTIC_CACHE_MAX_ENTRIES),
            ttl_seconds=kwargs.get("ttl_seconds", SEMANTIC_CACHE_TTL_SECONDS),
            min_confidence_threshold=kwargs.get("min_confidence", SEMANTIC_CACHE_MIN_CONFIDENCE),
            semantic_similarity_threshold=kwargs.get("similarity_threshold", LANGCACHE_SIMILARITY_THRESHOLD),
        )

    else:
        raise ValueError(f"Unknown cache backend: {selected_backend}")


def get_semantic_cache(force_refresh: bool = False, **kwargs: Any) -> Any:
    """
    Get the global singleton semantic cache instance, creating it if needed.
    
    Adheres to SemanticCachePort and allows seamless swapping of cache backends.
    """
    global _cache_instance
    if _cache_instance is None or force_refresh:
        _cache_instance = create_cache(**kwargs)
    return _cache_instance


def reset_cache_instance() -> None:
    """Reset the singleton instance (useful for unit testing)."""
    global _cache_instance
    _cache_instance = None
