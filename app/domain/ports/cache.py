"""
Semantic Cache Port (Domain Layer)

Defines vendor-neutral abstractions and protocols for semantic and response caching.
This port enables loose coupling between the application core/use cases
and specific cache backends (LangCache, Redis, JSON file, InMemory LRU, etc.).
"""

from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable
from dataclasses import dataclass, field
import time


@dataclass
class CacheEntryProtocol:
    """Standardized representation of a cache entry across all cache adapters."""
    cache_key: str
    original_query: str
    response: str
    confidence: float = 0.0
    source: str = "semantic_cache"
    evidence_count: int = 0
    model: str = ""
    citations: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    cache_id: str = ""
    assigned_role: Optional[str] = None
    document_ids: List[str] = field(default_factory=list)
    project_ids: List[str] = field(default_factory=list)
    is_public: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert entry to dictionary representation."""
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


@runtime_checkable
class SemanticCachePort(Protocol):
    """
    Protocol for semantic cache backends.
    
    Implementations must provide retrieval, insertion, eviction, health checks,
    and statistics while remaining swappable without affecting query orchestration.
    """

    def get(
        self,
        cache_key: str,
        original_query: str = "",
        **kwargs: Any,
    ) -> Optional[Any]:
        """
        Retrieve cached entry for a given cache_key or query prompt.
        
        Args:
            cache_key: Deterministic cache key (or hash)
            original_query: Raw user query for semantic similarity search
            **kwargs: Additional contextual filters (role, project_ids, document_ids, etc.)
            
        Returns:
            Cached entry object (with .response or dict with 'answer') if hit, None if miss.
        """
        ...

    def put(
        self,
        cache_key: str,
        original_query: str,
        response: str,
        confidence: float = 0.0,
        source: str = "semantic_cache",
        evidence_count: int = 0,
        model: str = "",
        citations: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> bool:
        """
        Store an entry in the cache.
        
        Args:
            cache_key: Deterministic cache key
            original_query: Raw user query
            response: Response text to cache
            confidence: Confidence score (0.0 to 1.0)
            source: Source of generation (e.g. 'rag_generated', 'faq_matched')
            evidence_count: Number of supporting evidence items
            model: Model name used for generation
            citations: List of source citations
            metadata: Additional metadata dictionary
            **kwargs: Additional parameters (cache_id, assigned_role, document_ids, etc.)
            
        Returns:
            True if stored successfully, False if rejected or failed.
        """
        ...

    def delete(self, cache_key: str) -> bool:
        """
        Evict an entry from the cache by key or query.
        
        Args:
            cache_key: Cache key to evict
            
        Returns:
            True if removed, False otherwise.
        """
        ...

    def clear(self) -> None:
        """Clear all entries from the cache backend."""
        ...

    def get_stats(self) -> Dict[str, Any]:
        """
        Return operational statistics for the cache backend.
        
        Returns:
            Dictionary containing metrics (hits, misses, entries, backend status, etc.)
        """
        ...

    def is_healthy(self) -> bool:
        """
        Check whether the cache backend is operational and reachable.
        
        Returns:
            True if healthy, False if degraded or unreachable.
        """
        ...
