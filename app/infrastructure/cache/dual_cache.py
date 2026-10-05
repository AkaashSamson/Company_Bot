"""
Dual-Cache Implementation (AB-14)

Implements LangCache as primary semantic cache with JSON file fallback:
- LangCache for distributed semantic caching
- JSON file-based local cache for resilience
- Bi-directional sync between caches
- Automatic failover when primary is unavailable
- Thread-safe operations
- Loosely coupled architecture implementing SemanticCachePort
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.core.cache_quality import is_negative_response
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
)
from app.domain.ports.cache import CacheEntryProtocol, SemanticCachePort
from app.infrastructure.cache.langcache_adapter import (
    LANGCACHE_SDK_AVAILABLE,
    LangCacheAdapter,
)

logger = logging.getLogger(__name__)

# Backward-compatible flag
LANGCACHE_AVAILABLE = LANGCACHE_SDK_AVAILABLE


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
    cache_id: str = ""
    assigned_role: Optional[str] = None
    document_ids: list[str] = field(default_factory=list)
    project_ids: list[str] = field(default_factory=list)
    is_public: bool = False

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return self.metadata.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            val = getattr(self, key)
            return val if val is not None else default
        return self.metadata.get(key, default)

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
            "cache_id": self.cache_id,
            "assigned_role": self.assigned_role,
            "document_ids": self.document_ids,
            "project_ids": self.project_ids,
            "is_public": self.is_public,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DualCacheEntry":
        """Instantiate from dictionary."""
        return cls(
            cache_key=data.get("cache_key", ""),
            original_query=data.get("original_query", ""),
            response=data.get("response", ""),
            confidence=float(data.get("confidence", 0.0)),
            source=data.get("source", "semantic_cache"),
            evidence_count=int(data.get("evidence_count", 0)),
            model=data.get("model", ""),
            citations=data.get("citations", []),
            created_at=float(data.get("created_at", time.time())),
            metadata=data.get("metadata", {}),
            cache_id=data.get("cache_id", ""),
            assigned_role=data.get("assigned_role"),
            document_ids=data.get("document_ids", []),
            project_ids=data.get("project_ids", []),
            is_public=bool(data.get("is_public", False)),
        )


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
        if not self.file_path.exists() or self.file_path.stat().st_size == 0:
            return
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for key, value in data.items():
                self._cache[key] = DualCacheEntry.from_dict(value)
            
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
    
    def get(self, cache_key: str, **kwargs: Any) -> Optional[DualCacheEntry]:
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
                    self._cache[key] = DualCacheEntry.from_dict(value)
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
    - Primary: LangCache (distributed semantic cache via LangCacheAdapter)
    - Fallback: JSON file-based local cache (JSONLocalCache)
    - Bi-directional sync
    - Automatic failover
    - Thread-safe operations
    - Loosely coupled architecture implementing SemanticCachePort
    """
    
    def __init__(
        self,
        langcache_config: Optional[dict] = None,
        json_fallback_path: Optional[str] = None,
        enable_sync: bool = True,
        sync_interval: float = 60.0,
        primary_cache: Optional[Any] = None,
        fallback_cache: Optional[Any] = None,
    ):
        """
        Initialize dual-cache system.
        
        Args:
            langcache_config: Optional dict for LangCache configuration
            json_fallback_path: Path for JSON fallback cache
            enable_sync: Enable bi-directional sync
            sync_interval: Sync interval in seconds
            primary_cache: Optional pre-configured primary cache adapter
            fallback_cache: Optional pre-configured fallback cache adapter
        """
        self._langcache_config = langcache_config
        self._enable_sync = enable_sync
        self._sync_interval = sync_interval
        self._lock = threading.RLock()
        
        # 1. Initialize Primary Cache (LangCacheAdapter)
        if primary_cache is not None:
            self._primary_adapter = primary_cache
        elif langcache_config is not None and not langcache_config:
            # Explicitly empty dict passed -> skip LangCache
            self._primary_adapter = LangCacheAdapter(server_url="", cache_id="", api_key="")
        elif langcache_config:
            self._primary_adapter = LangCacheAdapter(
                server_url=langcache_config.get("server_url"),
                cache_id=langcache_config.get("cache_id"),
                api_key=langcache_config.get("api_key"),
                similarity_threshold=langcache_config.get("similarity_threshold", LANGCACHE_SIMILARITY_THRESHOLD),
                timeout_seconds=langcache_config.get("timeout_seconds", LANGCACHE_TIMEOUT_SECONDS),
            )
        elif LANGCACHE_ENABLED:
            self._primary_adapter = LangCacheAdapter(
                server_url=LANGCACHE_SERVER_URL,
                cache_id=LANGCACHE_CACHE_ID,
                api_key=LANGCACHE_API_KEY,
                similarity_threshold=LANGCACHE_SIMILARITY_THRESHOLD,
                timeout_seconds=LANGCACHE_TIMEOUT_SECONDS,
            )
        else:
            self._primary_adapter = LangCacheAdapter(server_url="", cache_id="", api_key="")

        # 2. Initialize Fallback Cache (JSONLocalCache)
        if fallback_cache is not None:
            self._json_cache = fallback_cache
        else:
            fallback_file = json_fallback_path or DUAL_CACHE_JSON_FILE_PATH
            self._json_cache = JSONLocalCache(fallback_file)

        # Start background sync if enabled
        if enable_sync:
            self._start_sync_thread()
        
        logger.info(
            "dual_cache initialized langcache_available=%s sync=%s",
            self.langcache_available, enable_sync
        )

    @property
    def _langcache_available(self) -> bool:
        """Backward compatible property for checking LangCache availability."""
        if hasattr(self._primary_adapter, "is_available"):
            return bool(self._primary_adapter.is_available)
        return False

    @property
    def langcache_available(self) -> bool:
        """Return True if LangCache primary adapter is available."""
        return self._langcache_available

    @property
    def _langcache(self) -> Optional[Any]:
        """Access underlying LangCache client if present."""
        return getattr(self._primary_adapter, "_client", None)
    
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
        if not self.langcache_available:
            return
        
        try:
            json_entries = self._json_cache.get_all()
            synced = 0
            for key, entry in json_entries.items():
                if entry.source != "langcache":
                    ok = self._primary_adapter.put(
                        cache_key=entry.cache_key,
                        original_query=entry.original_query,
                        response=entry.response,
                        confidence=entry.confidence,
                        source=entry.source,
                        model=entry.model,
                        citations=entry.citations,
                        cache_id=entry.cache_id,
                        assigned_role=entry.assigned_role,
                        document_ids=entry.document_ids,
                        project_ids=entry.project_ids,
                    )
                    if ok:
                        synced += 1
            if synced > 0:
                logger.info("dual_cache sync_json_to_langcache synced=%d", synced)
        except Exception as e:
            logger.error("dual_cache sync error: %s", e)
    
    def get(
        self,
        cache_key: str,
        original_query: str = "",
        role: Optional[str] = None,
        roles: Optional[Sequence[str]] = None,
        project_ids: Optional[Sequence[str]] = None,
        document_ids: Optional[Sequence[str]] = None,
        is_admin: bool = False,
        **kwargs: Any,
    ) -> Optional[DualCacheEntry]:
        """
        Get entry from dual-cache.
        
        Searches LangCache first, then JSON fallback.
        """
        query_prompt = original_query or cache_key
        
        with self._lock:
            # 1. Try LangCache first
            if self.langcache_available and query_prompt:
                try:
                    langcache_entry = self._primary_adapter.get(
                        cache_key=cache_key,
                        original_query=query_prompt,
                        role=role,
                        roles=roles,
                        project_ids=project_ids,
                        document_ids=document_ids,
                        is_admin=is_admin,
                        **kwargs,
                    )
                    if langcache_entry is not None:
                        logger.debug("dual_cache hit=langcache key=%s", cache_key)
                        entry = DualCacheEntry(
                            cache_key=cache_key,
                            original_query=query_prompt,
                            response=langcache_entry.response,
                            confidence=langcache_entry.confidence,
                            source="langcache",
                            cache_id=langcache_entry.cache_id,
                            assigned_role=langcache_entry.assigned_role,
                            document_ids=langcache_entry.document_ids,
                            project_ids=langcache_entry.project_ids,
                            model=langcache_entry.model,
                            citations=langcache_entry.citations,
                            metadata=langcache_entry.metadata,
                        )
                        # Write-through to JSON cache for offline resilience
                        if DUAL_CACHE_SYNC_ON_WRITE:
                            try:
                                self._json_cache.put(entry)
                            except Exception:
                                pass
                        return entry
                except Exception as e:
                    logger.warning("dual_cache primary lookup failed, falling back to local: %s", e)

            # 2. Local JSON cache fallback
            json_entry = self._json_cache.get(cache_key)
            if json_entry:
                if is_negative_response(json_entry.response):
                    logger.info("dual_cache_evict reason=cached_negative_response key=%s", cache_key)
                    self._json_cache.delete(cache_key)
                    json_entry = None
                else:
                    # Validate RBAC on JSON entry
                    if not self._check_rbac(
                        json_entry,
                        role=role,
                        roles=roles,
                        project_ids=project_ids,
                        document_ids=document_ids,
                        is_admin=is_admin,
                    ):
                        logger.debug("dual_cache json rbac_denied key=%s", cache_key)
                        return None
                    
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
        cache_id: str = "",
        assigned_role: Optional[str] = None,
        document_ids: Optional[Sequence[str]] = None,
        project_ids: Optional[Sequence[str]] = None,
        ttl_seconds: Optional[float] = None,
        **kwargs: Any,
    ) -> bool:
        """
        Put entry into dual-cache.
        
        Writes to both LangCache and JSON fallback.
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
            cache_id=cache_id,
            assigned_role=assigned_role,
            document_ids=list(document_ids) if document_ids else [],
            project_ids=list(project_ids) if project_ids else [],
        )
        
        with self._lock:
            success = False
            
            # 1. Try LangCache primary
            if self.langcache_available:
                try:
                    primary_ok = self._primary_adapter.put(
                        cache_key=cache_key,
                        original_query=original_query,
                        response=response,
                        confidence=confidence,
                        source=source,
                        evidence_count=evidence_count,
                        model=model,
                        citations=citations,
                        metadata=metadata,
                        cache_id=cache_id,
                        assigned_role=assigned_role,
                        document_ids=document_ids,
                        project_ids=project_ids,
                        ttl_seconds=ttl_seconds,
                    )
                    if primary_ok:
                        success = True
                        logger.debug("dual_cache write=langcache key=%s", cache_key)
                except Exception as e:
                    logger.warning("dual_cache langcache write failed: %s", e)
            
            # 2. Always write to JSON fallback
            try:
                self._json_cache.put(entry)
                success = True
                logger.debug("dual_cache write=json key=%s", cache_key)
            except Exception as e:
                logger.error("dual_cache json write failed: %s", e)
            
            return success
    
    def invalidate(self, cache_key: str) -> bool:
        """Invalidate cache entry across both layers."""
        with self._lock:
            success = False
            if self._json_cache.delete(cache_key):
                success = True
            if self.langcache_available:
                try:
                    if self._primary_adapter.delete(cache_key):
                        success = True
                except Exception as e:
                    logger.debug("dual_cache langcache invalidate failed: %s", e)
            return success

    def delete(self, cache_key: str) -> bool:
        """Alias for invalidate (satisfies SemanticCachePort)."""
        return self.invalidate(cache_key)
    
    def clear(self) -> None:
        """Clear all cache entries across both layers."""
        with self._lock:
            if self.langcache_available:
                try:
                    self._primary_adapter.clear()
                except Exception as e:
                    logger.warning("dual_cache langcache clear failed: %s", e)
            
            self._json_cache.clear()
            logger.info("dual_cache cleared")
    
    def get_stats(self) -> dict:
        """Get combined cache statistics."""
        with self._lock:
            json_entries = len(self._json_cache.get_all())
            primary_stats = (
                self._primary_adapter.get_stats()
                if hasattr(self._primary_adapter, "get_stats")
                else {}
            )
            
            return {
                "langcache_available": self.langcache_available,
                "langcache_enabled": self.langcache_available,
                "json_fallback_entries": json_entries,
                "sync_enabled": self._enable_sync,
                "primary": primary_stats,
            }
    
    def is_healthy(self) -> bool:
        """Check if cache system is healthy."""
        # JSON cache is always available as fallback
        return True

    @staticmethod
    def _check_rbac(
        entry: DualCacheEntry,
        role: Optional[str] = None,
        roles: Optional[Sequence[str]] = None,
        project_ids: Optional[Sequence[str]] = None,
        document_ids: Optional[Sequence[str]] = None,
        is_admin: bool = False,
    ) -> bool:
        """RBAC access control check on DualCacheEntry."""
        if is_admin:
            return True

        if entry.is_public and not entry.assigned_role and not entry.document_ids and not entry.project_ids:
            return True

        caller_roles = set()
        if role:
            caller_roles.add(str(role).strip().lower())
        if roles:
            for r in roles:
                if r:
                    caller_roles.add(str(r).strip().lower())

        if "admin" in caller_roles:
            return True

        if entry.assigned_role:
            target_role = entry.assigned_role.strip().lower()
            if not caller_roles or target_role not in caller_roles:
                return False

        if entry.project_ids and project_ids is not None:
            caller_projs = {str(p).strip().lower() for p in project_ids if p}
            entry_projs = {str(p).strip().lower() for p in entry.project_ids if p}
            if not (entry_projs & caller_projs):
                return False

        if entry.document_ids and document_ids is not None:
            caller_docs = {str(d).strip().lower() for d in document_ids if d}
            for edoc in entry.document_ids:
                if str(edoc).strip().lower() not in caller_docs:
                    return False

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