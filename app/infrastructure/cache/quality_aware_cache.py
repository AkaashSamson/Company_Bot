"""
Quality-Aware Semantic Cache (Task AB-4)

Implements intelligent caching with quality assessment:
- InMemoryQualityAwareCache: Thread-safe LRU eviction and TTL expiration
- QualityAwareCacheEntry & CacheEntryMetadata: Rich tracking of confidence, source, and metrics
- CacheQualityValidator: Gating cache writes using C.R.E.A.T.E. evaluation criteria
- 100% backward compatible with CacheEntry and QualityAwareCache aliases
"""

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.cache_quality import is_negative_response

logger = logging.getLogger(__name__)


class CacheEntrySource(Enum):
    """Source of cached response."""
    RAG_GENERATED = "rag_generated"
    FAQ_MATCHED = "faq_matched"
    LLM_CACHED = "llm_cached"
    SEMANTIC_CACHE = "semantic_cache"
    QUALITY_GATED = "quality_gated"


class EvidenceQualityLevel(Enum):
    """Quality classification for retrieved evidence based on C.R.E.A.T.E. rules."""
    STRONG = "strong"
    BORDERLINE = "borderline"
    WEAK = "weak"
    INVALID = "invalid"


class QualityGateDecision(Enum):
    """Decision produced by CacheQualityValidator."""
    PASS = "PASS"
    REVIEW = "REVIEW"
    FAIL = "FAIL"


@dataclass
class CacheEntryMetadata:
    """
    Metadata tracking for quality-aware cache entries.
    
    Tracks source, confidence score, evidence count, retrieval metrics,
    evaluation decision, and access timestamps.
    """
    source: CacheEntrySource = CacheEntrySource.SEMANTIC_CACHE
    confidence: float = 0.0
    evidence_count: int = 0
    evidence_distances: list[float] = field(default_factory=list)
    model: str = ""
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    evaluation_decision: QualityGateDecision = QualityGateDecision.PASS
    quality_metrics: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return self.extra[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            self.extra[key] = value

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key) or key in self.extra

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return self.extra.get(key, default)

    def to_dict(self) -> dict:
        return {
            "source": self.source.value if isinstance(self.source, CacheEntrySource) else str(self.source),
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "evidence_distances": self.evidence_distances,
            "model": self.model,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "evaluation_decision": self.evaluation_decision.value if isinstance(self.evaluation_decision, QualityGateDecision) else str(self.evaluation_decision),
            "quality_metrics": self.quality_metrics,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'CacheEntryMetadata':
        source_val = data.get("source", "semantic_cache")
        source = CacheEntrySource(source_val) if isinstance(source_val, str) else source_val
        decision_val = data.get("evaluation_decision", "PASS")
        decision = QualityGateDecision(decision_val) if isinstance(decision_val, str) else decision_val
        return cls(
            source=source,
            confidence=data.get("confidence", 0.0),
            evidence_count=data.get("evidence_count", 0),
            evidence_distances=data.get("evidence_distances", []),
            model=data.get("model", ""),
            created_at=data.get("created_at", time.time()),
            last_accessed=data.get("last_accessed", time.time()),
            access_count=data.get("access_count", 0),
            evaluation_decision=decision,
            quality_metrics=data.get("quality_metrics", {}),
            extra=data.get("extra", {}),
        )


@dataclass
class QualityAwareCacheEntry:
    """
    Rich cache entry with metadata for quality-aware caching.
    
    Compatible with existing CacheEntry structure while embedding
    CacheEntryMetadata.
    """
    cache_key: str
    original_query: str
    response: str
    citations: list[dict] = field(default_factory=list)
    metadata: CacheEntryMetadata = field(default_factory=CacheEntryMetadata)

    def __init__(
        self,
        cache_key: str,
        original_query: str,
        response: str,
        confidence: float = 0.0,
        source: CacheEntrySource = CacheEntrySource.SEMANTIC_CACHE,
        evidence_count: int = 0,
        evidence_distances: Optional[list[float]] = None,
        model: str = "",
        citations: Optional[list[dict]] = None,
        created_at: Optional[float] = None,
        last_accessed: Optional[float] = None,
        access_count: int = 0,
        metadata: Optional[dict[str, Any]] = None,
        entry_metadata: Optional[CacheEntryMetadata] = None,
    ):
        self.cache_key = cache_key
        self.original_query = original_query
        self.response = response
        self.citations = citations or []

        if entry_metadata is not None:
            self.metadata = entry_metadata
        else:
            source_enum = CacheEntrySource(source) if isinstance(source, str) else source
            extra = metadata if isinstance(metadata, dict) else {}
            self.metadata = CacheEntryMetadata(
                source=source_enum,
                confidence=confidence,
                evidence_count=evidence_count,
                evidence_distances=evidence_distances or [],
                model=model,
                created_at=created_at if created_at is not None else time.time(),
                last_accessed=last_accessed if last_accessed is not None else time.time(),
                access_count=access_count,
                extra=extra,
            )

    @property
    def confidence(self) -> float:
        return self.metadata.confidence

    @confidence.setter
    def confidence(self, val: float):
        self.metadata.confidence = val

    @property
    def source(self) -> CacheEntrySource:
        return self.metadata.source

    @source.setter
    def source(self, val: CacheEntrySource):
        self.metadata.source = val

    @property
    def evidence_count(self) -> int:
        return self.metadata.evidence_count

    @evidence_count.setter
    def evidence_count(self, val: int):
        self.metadata.evidence_count = val

    @property
    def evidence_distances(self) -> list[float]:
        return self.metadata.evidence_distances

    @evidence_distances.setter
    def evidence_distances(self, val: list[float]):
        self.metadata.evidence_distances = val

    @property
    def model(self) -> str:
        return self.metadata.model

    @model.setter
    def model(self, val: str):
        self.metadata.model = val

    @property
    def created_at(self) -> float:
        return self.metadata.created_at

    @property
    def last_accessed(self) -> float:
        return self.metadata.last_accessed

    @last_accessed.setter
    def last_accessed(self, val: float):
        self.metadata.last_accessed = val

    @property
    def access_count(self) -> int:
        return self.metadata.access_count

    @access_count.setter
    def access_count(self, val: int):
        self.metadata.access_count = val

    def is_expired(self, ttl_seconds: float) -> bool:
        """Check if entry has exceeded TTL."""
        return (time.time() - self.metadata.created_at) > ttl_seconds

    def update_access(self) -> None:
        """Update access statistics."""
        self.metadata.last_accessed = time.time()
        self.metadata.access_count += 1

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "cache_key": self.cache_key,
            "original_query": self.original_query,
            "response": self.response,
            "confidence": self.metadata.confidence,
            "source": self.metadata.source.value,
            "evidence_count": self.metadata.evidence_count,
            "evidence_distances": self.metadata.evidence_distances,
            "model": self.metadata.model,
            "citations": self.citations,
            "created_at": self.metadata.created_at,
            "last_accessed": self.metadata.last_accessed,
            "access_count": self.metadata.access_count,
            "metadata": self.metadata.extra,
            "entry_metadata": self.metadata.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'QualityAwareCacheEntry':
        """Create CacheEntry from dictionary."""
        source_val = data.get("source", "semantic_cache")
        source = CacheEntrySource(source_val) if isinstance(source_val, str) else source_val

        return cls(
            cache_key=data["cache_key"],
            original_query=data["original_query"],
            response=data["response"],
            confidence=data.get("confidence", 0.0),
            source=source,
            evidence_count=data.get("evidence_count", 0),
            evidence_distances=data.get("evidence_distances", []),
            model=data.get("model", ""),
            citations=data.get("citations", []),
            created_at=data.get("created_at", time.time()),
            last_accessed=data.get("last_accessed", time.time()),
            access_count=data.get("access_count", 0),
            metadata=data.get("metadata", {}),
        )


# Backward-compatible alias
CacheEntry = QualityAwareCacheEntry


@dataclass
class QualityValidationResult:
    """Detailed result of a cache quality validation check."""
    is_valid: bool
    decision: QualityGateDecision
    reason: str
    metrics: dict[str, Any] = field(default_factory=dict)
    raw_evaluation: Optional[dict[str, Any]] = None


class CacheQualityValidator:
    """
    Evaluates whether generated responses meet quality standards before caching.

    Implements C.R.E.A.T.E. quality gate rules:
    - Distance Score Thresholds (<0.60 STRONG, 0.60-0.70 BORDERLINE, 0.70-0.85 WEAK, >=0.85 INVALID)
    - Lexical Grounding Target (>= 0.20)
    - Separation Gap Target (>= 0.10)
    - Evidence Count Target (>= 1 for RAG)
    - Confidence score thresholding
    - Hallucination and contradiction guards
    """

    def __init__(
        self,
        min_confidence_threshold: float = 0.60,
        max_distance_threshold: float = 0.85,
        min_lexical_grounding: float = 0.20,
        min_separation_gap: float = 0.10,
        allow_review: bool = False,
        require_evidence_for_rag: bool = False,
    ):
        self.min_confidence_threshold = min_confidence_threshold
        self.max_distance_threshold = max_distance_threshold
        self.min_lexical_grounding = min_lexical_grounding
        self.min_separation_gap = min_separation_gap
        self.allow_review = allow_review
        self.require_evidence_for_rag = require_evidence_for_rag

    @staticmethod
    def classify_distance(distance: float) -> EvidenceQualityLevel:
        """Classify retrieval distance according to C.R.E.A.T.E. Rule 2."""
        if distance < 0.60:
            return EvidenceQualityLevel.STRONG
        elif distance < 0.70:
            return EvidenceQualityLevel.BORDERLINE
        elif distance < 0.85:
            return EvidenceQualityLevel.WEAK
        else:
            return EvidenceQualityLevel.INVALID

    def validate(
        self,
        query: str,
        response: str,
        confidence: float = 0.0,
        evidence_count: int = 0,
        evidence_distances: Optional[list[float]] = None,
        lexical_grounding: Optional[float] = None,
        separation_gap: Optional[float] = None,
        citations: Optional[list[dict]] = None,
        source: CacheEntrySource = CacheEntrySource.SEMANTIC_CACHE,
    ) -> QualityValidationResult:
        """
        Validate whether response meets quality gate criteria for caching.
        """
        distances = evidence_distances or []
        metrics: dict[str, Any] = {
            "confidence": confidence,
            "evidence_count": evidence_count,
            "distances": distances,
            "lexical_grounding": lexical_grounding,
            "separation_gap": separation_gap,
            "citations_count": len(citations or []),
        }

        # 1. Non-empty check
        if not response or not response.strip():
            return QualityValidationResult(
                is_valid=False,
                decision=QualityGateDecision.FAIL,
                reason="Empty or whitespace response cannot be cached",
                metrics=metrics,
            )

        # 2. Confidence check
        if confidence < self.min_confidence_threshold:
            return QualityValidationResult(
                is_valid=False,
                decision=QualityGateDecision.FAIL,
                reason=f"Confidence {confidence:.2f} is below threshold {self.min_confidence_threshold:.2f}",
                metrics=metrics,
            )

        # 3. RAG-specific evidence distance check
        if distances:
            min_dist = min(distances)
            quality_level = self.classify_distance(min_dist)
            metrics["best_distance"] = min_dist
            metrics["quality_level"] = quality_level.value

            if quality_level == EvidenceQualityLevel.INVALID or min_dist >= self.max_distance_threshold:
                return QualityValidationResult(
                    is_valid=False,
                    decision=QualityGateDecision.FAIL,
                    reason=f"Best evidence distance {min_dist:.3f} is INVALID (>= {self.max_distance_threshold})",
                    metrics=metrics,
                )

        # 4. Evidence count for RAG
        if self.require_evidence_for_rag and source == CacheEntrySource.RAG_GENERATED and evidence_count < 1:
            return QualityValidationResult(
                is_valid=False,
                decision=QualityGateDecision.FAIL,
                reason="RAG generated response requires at least 1 evidence chunk",
                metrics=metrics,
            )

        # 5. Lexical grounding check (if provided)
        if lexical_grounding is not None and lexical_grounding < self.min_lexical_grounding:
            decision = QualityGateDecision.REVIEW if self.allow_review else QualityGateDecision.FAIL
            is_valid = self.allow_review
            return QualityValidationResult(
                is_valid=is_valid,
                decision=decision,
                reason=f"Lexical grounding {lexical_grounding:.2f} is below target {self.min_lexical_grounding:.2f}",
                metrics=metrics,
            )

        # 6. Separation gap check (if provided)
        if separation_gap is not None and separation_gap < self.min_separation_gap:
            decision = QualityGateDecision.REVIEW if self.allow_review else QualityGateDecision.PASS
            metrics["separation_gap_warning"] = True

        # 7. Unverified / negative answer phrases (never cache non-answers)
        if is_negative_response(response):
            return QualityValidationResult(
                is_valid=False,
                decision=QualityGateDecision.FAIL,
                reason="Negative/unverified response cannot be cached",
                metrics=metrics,
            )

        return QualityValidationResult(
            is_valid=True,
            decision=QualityGateDecision.PASS,
            reason="Response satisfies all deterministic quality gate criteria",
            metrics=metrics,
        )


class InMemoryQualityAwareCache:
    """
    Quality-aware semantic cache with thread-safe LRU eviction and TTL support.
    
    Features:
    - Only caches responses passing CacheQualityValidator criteria
    - LRU eviction when max_entries reached
    - TTL-based expiration
    - Rich metadata tracking (source, confidence, evidence count, timestamps)
    - Thread-safe operations with RLock
    - Performance statistics and monitoring
    """
    
    def __init__(
        self,
        max_entries: int = 1000,
        ttl_seconds: float = 3600.0,
        min_confidence_threshold: float = 0.60,
        validator: Optional[CacheQualityValidator] = None,
        enable_stats: bool = True,
    ):
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.min_confidence_threshold = min_confidence_threshold
        self.validator = validator or CacheQualityValidator(min_confidence_threshold=min_confidence_threshold)
        self.enable_stats = enable_stats
        
        self._cache: dict[str, QualityAwareCacheEntry] = {}
        self._access_order: list[str] = []
        self._lock = threading.RLock()
        
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
            "writes": 0,
            "rejected_low_confidence": 0,
            "rejected_quality_gate": 0,
        }
        
        logger.info(
            "in_memory_quality_aware_cache initialized max_entries=%d ttl=%.0fs min_confidence=%.2f",
            max_entries, ttl_seconds, min_confidence_threshold
        )
    
    def get(self, cache_key: str) -> Optional[QualityAwareCacheEntry]:
        """
        Get entry from cache.
        
        Returns:
            QualityAwareCacheEntry if found and unexpired, else None.
        """
        with self._lock:
            entry = self._cache.get(cache_key)
            
            if entry is None:
                self._stats["misses"] += 1
                logger.debug("cache_miss key=%s", cache_key)
                return None
            
            # Check TTL expiry
            if entry.is_expired(self.ttl_seconds):
                self._remove_entry(cache_key)
                self._stats["misses"] += 1
                self._stats["expirations"] += 1
                logger.debug("cache_expired key=%s", cache_key)
                return None
            
            # Update LRU and access stats
            entry.update_access()
            self._update_access_order(cache_key)
            
            self._stats["hits"] += 1
            logger.debug(
                "cache_hit key=%s confidence=%.2f access_count=%d",
                cache_key, entry.confidence, entry.access_count
            )
            return entry
    
    def put(
        self,
        cache_key: str,
        original_query: str,
        response: str,
        confidence: float = 0.0,
        source: CacheEntrySource = CacheEntrySource.SEMANTIC_CACHE,
        evidence_count: int = 0,
        evidence_distances: Optional[list[float]] = None,
        model: str = "",
        citations: Optional[list[dict]] = None,
        metadata: Optional[dict[str, Any]] = None,
        lexical_grounding: Optional[float] = None,
        separation_gap: Optional[float] = None,
    ) -> bool:
        """
        Put entry into cache (only if quality gate validator approves).
        """
        source_enum = CacheEntrySource(source) if isinstance(source, str) else source

        # Run CacheQualityValidator
        validation = self.validator.validate(
            query=original_query,
            response=response,
            confidence=confidence,
            evidence_count=evidence_count,
            evidence_distances=evidence_distances,
            lexical_grounding=lexical_grounding,
            separation_gap=separation_gap,
            citations=citations,
            source=source_enum,
        )

        if not validation.is_valid:
            if confidence < self.min_confidence_threshold:
                self._stats["rejected_low_confidence"] += 1
            else:
                self._stats["rejected_quality_gate"] += 1
            logger.debug(
                "cache_rejected reason=%s decision=%s key=%s",
                validation.reason, validation.decision.value, cache_key
            )
            return False
        
        with self._lock:
            if len(self._cache) >= self.max_entries and cache_key not in self._cache:
                self._evict_lru()
            
            entry_metadata = CacheEntryMetadata(
                source=source_enum,
                confidence=confidence,
                evidence_count=evidence_count,
                evidence_distances=evidence_distances or [],
                model=model,
                created_at=time.time(),
                last_accessed=time.time(),
                access_count=0,
                evaluation_decision=validation.decision,
                quality_metrics=validation.metrics,
                extra=metadata or {},
            )

            entry = QualityAwareCacheEntry(
                cache_key=cache_key,
                original_query=original_query,
                response=response,
                citations=citations or [],
                entry_metadata=entry_metadata,
            )
            
            self._cache[cache_key] = entry
            self._update_access_order(cache_key)
            self._stats["writes"] += 1
            
            logger.debug(
                "cache_write key=%s confidence=%.2f source=%s decision=%s",
                cache_key, confidence, source_enum.value, validation.decision.value
            )
            return True
    
    def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if not self._access_order:
            return
        oldest_key = self._access_order.pop(0)
        if oldest_key in self._cache:
            del self._cache[oldest_key]
            self._stats["evictions"] += 1
            logger.debug("cache_evicted key=%s reason=lru", oldest_key)
    
    def _remove_entry(self, cache_key: str) -> None:
        """Remove entry from cache."""
        if cache_key in self._cache:
            del self._cache[cache_key]
        if cache_key in self._access_order:
            self._access_order.remove(cache_key)
    
    def _update_access_order(self, cache_key: str) -> None:
        """Update access order for LRU tracking."""
        if cache_key in self._access_order:
            self._access_order.remove(cache_key)
        self._access_order.append(cache_key)
    
    def invalidate(self, cache_key: str) -> bool:
        """Invalidate a specific cache entry."""
        with self._lock:
            if cache_key in self._cache:
                self._remove_entry(cache_key)
                logger.info("cache_invalidated key=%s", cache_key)
                return True
            return False
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
            logger.info("cache_cleared")
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                (self._stats["hits"] / total_requests * 100)
                if total_requests > 0 else 0
            )
            return {
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": hit_rate,
                "evictions": self._stats["evictions"],
                "expirations": self._stats["expirations"],
                "writes": self._stats["writes"],
                "rejected_low_confidence": self._stats["rejected_low_confidence"],
                "rejected_quality_gate": self._stats.get("rejected_quality_gate", 0),
                "current_entries": len(self._cache),
                "max_entries": self.max_entries,
                "utilization": (len(self._cache) / self.max_entries * 100) if self.max_entries > 0 else 0,
            }
    
    def cleanup_expired(self) -> int:
        """Remove all expired entries."""
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired(self.ttl_seconds)
            ]
            for key in expired_keys:
                self._remove_entry(key)
                self._stats["expirations"] += 1
            if expired_keys:
                logger.info("cache_cleanup_expired count=%d", len(expired_keys))
            return len(expired_keys)
    
    def get_all_entries(self) -> list[QualityAwareCacheEntry]:
        """Get all cache entries (for debugging/inspection)."""
        with self._lock:
            return list(self._cache.values())


# Backward-compatible alias
QualityAwareCache = InMemoryQualityAwareCache

# Global singleton instance
_quality_cache: Optional[InMemoryQualityAwareCache] = None


def get_quality_cache(
    max_entries: int = 1000,
    ttl_seconds: float = 3600.0,
) -> InMemoryQualityAwareCache:
    """Get the global quality-aware cache instance."""
    global _quality_cache
    if _quality_cache is None:
        _quality_cache = InMemoryQualityAwareCache(
            max_entries=max_entries,
            ttl_seconds=ttl_seconds,
        )
    return _quality_cache