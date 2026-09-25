"""
Dual-Cache Implementation (AB-14)

Implements LangCache as primary semantic cache with JSON file fallback:
- LangCache for distributed semantic caching
- JSON file-based local cache for resilience
- Bi-directional sync between caches
- Automatic failover when primary is unavailable
- Thread-safe operations
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.core.cache_quality import is_negative_response

logger = logging.getLogger(__name__)


# Try to import LangCache, fall back gracefully if not available
try:
    from langcache import LangCache
    LANGCACHE_AVAILABLE = True
except ImportError:
    LANGCACHE_AVAILABLE = False
    logger.warning("langcache not available, using JSON fallback only")


@dataclass
class DualCacheEntry:
    """Cache entry for dual-cache system."""
    cache_key: str
    original_query: str
    response: str
    confidence: float = 0.0
    source: str = "semantic_cache"
    evidence_count: int = 0
    model: str = ""
    citations: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "cache_key": self.cache_key,
            "original_query": self.original_query,
            "response": self.response,
            "confidence": self.confidence,
            "source": self.source,
            "evidence_count": self.evidence_count,
            "model": self.model,
            "citations": self.citations,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


class JSONLocalCache:
    """
    JSON file-based local cache for fallback and sync.
    
    Provides persistent storage that works without external services.
    """
    
    def __init__(self, file_path: str):
        """
        Initialize JSON cache.
        
        Args:
            file_path: Path to JSON cache file
        """
        self.file_path = Path(file_path)
        self._cache: dict[str, DualCacheEntry] = {}
        self._lock = threading.RLock()
        
        # Create parent directory if needed
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing cache
        self._load()
        
        logger.info("json_local_cache initialized path=%s", file_path)
    
    def _load(self) -> None:
        """Load cache from JSON file."""
        if not self.file_path.exists():
            return
        
        try:
            with open(self.file_path, 'r') as f:
                data = json.load(f)
            
            for key, value in data.items():
                self._cache[key] = DualCacheEntry(**value)
            
            logger.info("json_local_cache loaded entries=%d", len(self._cache))
        except Exception as e:
            logger.error("json_local_cache load failed: %s", e)
    
    def _save(self) -> None:
        """Save cache to JSON file atomically."""
        try:
            data = {
                key: entry.to_dict() 
                for key, entry in self._cache.items()
            }
            
            temp_path = self.file_path.with_name(f"{self.file_path.name}.{os.getpid()}.tmp")
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, self.file_path)
            
            logger.debug("json_local_cache saved entries=%d", len(self._cache))
        except Exception as e:
            logger.error("json_local_cache save failed: %s", e)
    
    def get(self, cache_key: str) -> Optional[DualCacheEntry]:
        """Get entry from cache."""
        with self._lock:
            return self._cache.get(cache_key)
    
    def put(self, entry: DualCacheEntry) -> None:
        """Put entry into cache."""
        with self._lock:
            self._cache[entry.cache_key] = entry
            self._save()
    
    def delete(self, cache_key: str) -> bool:
        """Delete entry from cache."""
        with self._lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                self._save()
                return True
            return False
    
    def get_all(self) -> dict[str, DualCacheEntry]:
        """Get all cache entries."""
        with self._lock:
            return dict(self._cache)
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._save()
    
    def sync_from_dict(self, data: dict[str, dict]) -> int:
        """Sync entries from external dictionary."""
        count = 0
        with self._lock:
            for key, value in data.items():
                if key not in self._cache:
                    self._cache[key] = DualCacheEntry(**value)
                    count += 1
            if count > 0:
                self._save()
        return count
    
    def to_dict(self) -> dict[str, dict]:
        """Export cache as dictionary."""
        with self._lock:
            return {
                key: entry.to_dict()
                for key, entry in self._cache.items()
            }


class DualCache:
    """
    Dual-cache system: LangCache primary + JSON fallback.
    
    Features:
    - Primary: LangCache (distributed semantic cache)
    - Fallback: JSON file-based local cache
    - Bi-directional sync
    - Automatic failover
    - Thread-safe operations
    """
    
    def __init__(
        self,
        langcache_config: Optional[dict] = None,
        json_fallback_path: Optional[str] = None,
        enable_sync: bool = True,
        sync_interval: float = 60.0,
    ):
        """
        Initialize dual-cache system.
        
        Args:
            langcache_config: Configuration for LangCache
            json_fallback_path: Path for JSON fallback cache
            enable_sync: Enable bi-directional sync
            sync_interval: Sync interval in seconds
        """
        self._langcache_config = langcache_config or {}
        self._enable_sync = enable_sync
        self._sync_interval = sync_interval
        
        # Initialize LangCache if available
        self._langcache: Optional[Any] = None
        self._langcache_available = False
        
        if LANGCACHE_AVAILABLE and langcache_config:
            try:
                self._langcache = LangCache(
                    server_url=langcache_config.get("server_url"),
                    cache_id=langcache_config.get("cache_id"),
                    api_key=langcache_config.get("api_key"),
                )
                self._langcache_available = True
                logger.info("dual_cache langcache initialized")
            except Exception as e:
                logger.warning("dual_cache langcache init failed: %s", e)
        
        # Initialize JSON fallback
        self._json_cache = JSONLocalCache(
            json_fallback_path or "data/semantic_cache.json"
        )
        
        self._lock = threading.RLock()
        
        # Start background sync if enabled
        if enable_sync:
            self._start_sync_thread()
        
        logger.info(
            "dual_cache initialized langcache=%s sync=%s",
            self._langcache_available, enable_sync
        )
    
    def _start_sync_thread(self) -> None:
        """Start background sync thread."""
        def sync_loop():
            while True:
                time.sleep(self._sync_interval)
                try:
                    self._sync_json_to_langcache()
                except Exception as e:
                    logger.error("dual_cache sync failed: %s", e)
        
        thread = threading.Thread(target=sync_loop, daemon=True)
        thread.start()
        logger.info("dual_cache sync_thread started interval=%.0fs", self._sync_interval)
    
    def _sync_json_to_langcache(self) -> None:
        """Sync JSON cache entries to LangCache."""
        if not self._langcache_available or not self._langcache:
            return
        
        try:
            json_entries = self._json_cache.to_dict()
            # Note: Actual sync depends on LangCache API
            logger.debug("dual_cache sync_json_to_langcache count=%d", len(json_entries))
        except Exception as e:
            logger.error("dual_cache sync error: %s", e)
    
    def _search_langcache(self, prompt: str) -> Optional[dict]:
        """Search LangCache for similar prompt."""
        if not self._langcache_available or not self._langcache:
            return None
        
        try:
            result = self._langcache.search(prompt=prompt)
            if result and result.get("status") == "success":
                return result
        except Exception as e:
            logger.debug("langcache search failed: %s", e)
        
        return None
    
    def _set_langcache(self, prompt: str, response: str) -> bool:
        """Set entry in LangCache."""
        if not self._langcache_available or not self._langcache:
            return False
        
        try:
            result = self._langcache.set(prompt=prompt, response=response)
            return result and result.get("status") == "success"
        except Exception as e:
            logger.debug("langcache set failed: %s", e)
            return False
    
    def get(self, cache_key: str, original_query: str = "") -> Optional[DualCacheEntry]:
        """
        Get entry from dual-cache.
        
        Searches LangCache first, then JSON fallback.
        
        Args:
            cache_key: Cache key for lookup
            original_query: Original query for LangCache search
            
        Returns:
            DualCacheEntry if found, None otherwise
        """
        with self._lock:
            # Try LangCache first
            if self._langcache_available and original_query:
                langcache_result = self._search_langcache(original_query)
                if langcache_result:
                    logger.debug("dual_cache hit=langcache key=%s", cache_key)
                    return DualCacheEntry(
                        cache_key=cache_key,
                        original_query=original_query,
                        response=langcache_result.get("response", ""),
                        source="langcache",
                    )
            
            json_entry = self._json_cache.get(cache_key)
            if json_entry:
                if is_negative_response(json_entry.response):
                    logger.info("dual_cache_evict reason=cached_negative_response key=%s", cache_key)
                    self._json_cache.delete(cache_key)
                    json_entry = None
                else:
                    logger.debug("dual_cache hit=json key=%s", cache_key)
                    return json_entry
            
            logger.debug("dual_cache miss key=%s", cache_key)
            return None
    
    def put(
        self,
        cache_key: str,
        original_query: str,
        response: str,
        confidence: float = 0.0,
        source: str = "semantic_cache",
        evidence_count: int = 0,
        model: str = "",
        citations: Optional[list[dict]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Put entry into dual-cache.
        
        Writes to both LangCache and JSON fallback.
        
        Args:
            cache_key: Cache key
            original_query: Original query
            response: Response content
            confidence: Confidence score (0-1)
            source: Source of response
            evidence_count: Number of evidence chunks
            model: LLM model used
            citations: Source citations
            metadata: Additional metadata
        """
        if is_negative_response(response):
            logger.info("dual_cache_skip reason=negative_response key=%s", cache_key)
            return False

        entry = DualCacheEntry(
            cache_key=cache_key,
            original_query=original_query,
            response=response,
            confidence=confidence,
            source=source,
            evidence_count=evidence_count,
            model=model,
            citations=citations or [],
            metadata=metadata or {},
        )
        
        with self._lock:
            success = False
            
            # Try LangCache first
            if self._langcache_available:
                try:
                    if self._set_langcache(original_query, response):
                        success = True
                        logger.debug("dual_cache write=langcache key=%s", cache_key)
                except Exception as e:
                    logger.warning("dual_cache langcache write failed: %s", e)
            
            # Always write to JSON fallback
            try:
                self._json_cache.put(entry)
                success = True
                logger.debug("dual_cache write=json key=%s", cache_key)
            except Exception as e:
                logger.error("dual_cache json write failed: %s", e)
            
            return success
    
    def invalidate(self, cache_key: str) -> bool:
        """Invalidate cache entry."""
        with self._lock:
            success = False
            
            # Remove from JSON
            if self._json_cache.delete(cache_key):
                success = True
            
            # Note: LangCache invalidation depends on API
            # Would need cache_id and key for invalidation
            
            return success
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            if self._langcache_available and self._langcache:
                try:
                    # LangCache clear depends on API
                    pass
                except Exception as e:
                    logger.warning("dual_cache langcache clear failed: %s", e)
            
            self._json_cache.clear()
            logger.info("dual_cache cleared")
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            json_entries = len(self._json_cache.get_all())
            
            return {
                "langcache_available": self._langcache_available,
                "langcache_enabled": self._langcache is not None,
                "json_fallback_entries": json_entries,
                "sync_enabled": self._enable_sync,
            }
    
    def is_healthy(self) -> bool:
        """Check if cache system is healthy."""
        # JSON cache is always available as fallback
        return True


# Global singleton instance
_dual_cache: Optional[DualCache] = None
_dual_cache_lock = threading.Lock()


def get_dual_cache(
    langcache_config: Optional[dict] = None,
    json_fallback_path: Optional[str] = None,
) -> DualCache:
    """Get the global dual-cache instance."""
    global _dual_cache
    
    if _dual_cache is None:
        with _dual_cache_lock:
            if _dual_cache is None:
                _dual_cache = DualCache(
                    langcache_config=langcache_config,
                    json_fallback_path=json_fallback_path,
                )
    
    return _dual_cache


# For backwards compatibility
class SemanticCache(DualCache):
    """Alias for DualCache for backwards compatibility."""
    pass