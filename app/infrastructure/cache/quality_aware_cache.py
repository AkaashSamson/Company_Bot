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
import uuid
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from app.core.cache_quality import is_negative_response

logger = logging.getLogger(__name__)


def _to_timestamp(val: Any) -> float:
    """Convert datetime, int, float, or ISO string to UTC epoch float."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc).timestamp()
        return val.timestamp()
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val).timestamp()
        except Exception:
            try:
                return float(val)
            except Exception:
                return 0.0
    return 0.0


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
    Metadata tracking for quality-aware cache entries with RBAC isolation and document freshness.
    
    Tracks cache_id, assigned_role, document_ids, doc_last_updated, project_ids, source,
    confidence score, evidence count, retrieval metrics, evaluation decision,
    and access timestamps.
    """
    cache_id: str = ""
    assigned_role: Optional[str] = None
    document_ids: list[str] = field(default_factory=list)
    doc_last_updated: dict[str, float] = field(default_factory=dict)
    project_ids: list[str] = field(default_factory=list)
    is_public: bool = False
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
            "cache_id": self.cache_id,
            "assigned_role": self.assigned_role,
            "document_ids": list(self.document_ids),
            "doc_last_updated": dict(self.doc_last_updated),
            "project_ids": list(self.project_ids),
            "is_public": self.is_public,
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
            cache_id=data.get("cache_id", ""),
            assigned_role=data.get("assigned_role"),
            document_ids=list(data.get("document_ids", [])),
            doc_last_updated=dict(data.get("doc_last_updated", {})),
            project_ids=list(data.get("project_ids", [])),
            is_public=bool(data.get("is_public", False)),
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
    Rich cache entry with metadata for quality-aware caching, RBAC document isolation,
    and document last_updated freshness tracking.
    
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
        cache_id: str = "",
        assigned_role: Optional[str] = None,
        document_ids: Optional[Sequence[str]] = None,
        project_ids: Optional[Sequence[str]] = None,
        is_public: bool = False,
        doc_last_updated: Optional[dict[str, float]] = None,
    ):
        self.cache_key = cache_key
        self.original_query = original_query
        self.response = response
        self.citations = citations or []

        if entry_metadata is not None:
            self.metadata = entry_metadata
            if cache_id and not self.metadata.cache_id:
                self.metadata.cache_id = cache_id
            if assigned_role is not None and self.metadata.assigned_role is None:
                self.metadata.assigned_role = assigned_role
            if document_ids and not self.metadata.document_ids:
                self.metadata.document_ids = list(document_ids)
            if doc_last_updated and not self.metadata.doc_last_updated:
                self.metadata.doc_last_updated = dict(doc_last_updated)
            if project_ids and not self.metadata.project_ids:
                self.metadata.project_ids = list(project_ids)
            if is_public:
                self.metadata.is_public = is_public
        else:
            source_enum = CacheEntrySource(source) if isinstance(source, str) else source
            extra = metadata if isinstance(metadata, dict) else {}
            effective_cache_id = cache_id or f"cch_{uuid.uuid4().hex[:12]}"
            self.metadata = CacheEntryMetadata(
                cache_id=effective_cache_id,
                assigned_role=assigned_role,
                document_ids=list(document_ids) if document_ids else [],
                doc_last_updated=dict(doc_last_updated) if doc_last_updated else {},
                project_ids=list(project_ids) if project_ids else [],
                is_public=is_public,
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
    def cache_id(self) -> str:
        return self.metadata.cache_id

    @cache_id.setter
    def cache_id(self, val: str):
        self.metadata.cache_id = val

    @property
    def assigned_role(self) -> Optional[str]:
        return self.metadata.assigned_role

    @assigned_role.setter
    def assigned_role(self, val: Optional[str]):
        self.metadata.assigned_role = val

    @property
    def document_ids(self) -> list[str]:
        return self.metadata.document_ids

    @document_ids.setter
    def document_ids(self, val: list[str]):
        self.metadata.document_ids = val

    @property
    def doc_last_updated(self) -> dict[str, float]:
        return self.metadata.doc_last_updated

    @doc_last_updated.setter
    def doc_last_updated(self, val: dict[str, float]):
        self.metadata.doc_last_updated = val

    @property
    def project_ids(self) -> list[str]:
        return self.metadata.project_ids

    @project_ids.setter
    def project_ids(self, val: list[str]):
        self.metadata.project_ids = val

    @property
    def is_public(self) -> bool:
        return self.metadata.is_public

    @is_public.setter
    def is_public(self, val: bool):
        self.metadata.is_public = val

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
            "cache_id": self.metadata.cache_id,
            "assigned_role": self.metadata.assigned_role,
            "document_ids": self.metadata.document_ids,
            "doc_last_updated": self.metadata.doc_last_updated,
            "project_ids": self.metadata.project_ids,
            "is_public": self.metadata.is_public,
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
            cache_id=data.get("cache_id", ""),
            assigned_role=data.get("assigned_role"),
            document_ids=data.get("document_ids", []),
            doc_last_updated=data.get("doc_last_updated", {}),
            project_ids=data.get("project_ids", []),
            is_public=data.get("is_public", False),
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
    Quality-aware semantic cache with thread-safe LRU eviction, TTL support,
    unique Cache IDs, and RBAC document isolation.
    
    Features:
    - Unique Cache ID (cch_<hex>) generated for every cached document response
    - Role-based Access Control (RBAC): Only provides responses assigned to the requester's role
    - Document-level scoping: Ensures requester has authorization to all cited documents
    - Only caches responses passing CacheQualityValidator criteria
    - LRU eviction when max_entries reached
    - TTL-based expiration
    - Rich metadata tracking (source, confidence, evidence count, timestamps, RBAC)
    - Thread-safe operations with RLock
    - Cache ID index and role/document invalidation
    """
    
    def __init__(
        self,
        max_entries: int = 1000,
        ttl_seconds: float = 3600.0,
        min_confidence_threshold: float = 0.60,
        validator: Optional[CacheQualityValidator] = None,
        enable_stats: bool = True,
        document_timestamp_lookup: Optional[Callable[[str], Optional[float]]] = None,
    ):
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.min_confidence_threshold = min_confidence_threshold
        self.validator = validator or CacheQualityValidator(min_confidence_threshold=min_confidence_threshold)
        self.enable_stats = enable_stats
        self.document_timestamp_lookup = document_timestamp_lookup
        
        self._cache: dict[str, QualityAwareCacheEntry] = {}
        self._cache_id_to_key: dict[str, str] = {}
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
            "rbac_denials": 0,
            "stale_document_evictions": 0,
        }
        
        logger.info(
            "in_memory_quality_aware_cache initialized max_entries=%d ttl=%.0fs min_confidence=%.2f",
            max_entries, ttl_seconds, min_confidence_threshold
        )

    def _check_rbac_access(
        self,
        entry: QualityAwareCacheEntry,
        role: Optional[str] = None,
        roles: Optional[Sequence[str]] = None,
        project_ids: Optional[Sequence[str]] = None,
        document_ids: Optional[Sequence[str]] = None,
        is_admin: bool = False,
    ) -> bool:
        """
        Validate RBAC access for a cache entry based on role, document_ids, and project_ids.
        
        Rules:
        1. is_admin=True grants unrestricted access to all cached entries.
        2. If entry has no assigned_role, no document_ids, and no project_ids, or is_public=True,
           access is granted.
        3. If entry.assigned_role is set:
           - User must provide role/roles.
           - If 'admin' is in user's roles, access is granted.
           - User's role must match entry.assigned_role (case-insensitive).
        4. If entry.document_ids is set and document_ids filter is provided:
           - Every document in entry.document_ids must be authorized for requester.
        5. If entry.project_ids is set and project_ids filter is provided:
           - Requester's authorized projects must intersect with entry.project_ids.
        """
        if is_admin:
            return True

        entry_role = entry.assigned_role
        entry_docs = entry.document_ids or []
        entry_projs = entry.project_ids or []

        # Open public entries with no role or doc restrictions
        if entry.is_public and not entry_role and not entry_docs and not entry_projs:
            return True

        # Build set of caller roles (lowercase)
        caller_roles: Set[str] = set()
        if role:
            caller_roles.add(str(role).strip().lower())
        if roles:
            for r in roles:
                if r:
                    caller_roles.add(str(r).strip().lower())

        if "admin" in caller_roles:
            return True

        # 1. Role enforcement: Only provide responses assigned to each role
        if entry_role:
            target_role = entry_role.strip().lower()
            if not caller_roles or target_role not in caller_roles:
                return False

        # 2. Project enforcement: Requester must be authorized for the project
        if entry_projs and project_ids is not None:
            caller_projs = {str(p).strip().lower() for p in project_ids if p}
            entry_projs_set = {str(p).strip().lower() for p in entry_projs if p}
            if not (entry_projs_set & caller_projs):
                return False

        # 3. Document enforcement: Requester must be authorized for all cited documents
        if entry_docs and document_ids is not None:
            caller_docs = {str(d).strip().lower() for d in document_ids if d}
            for edoc in entry_docs:
                if str(edoc).strip().lower() not in caller_docs:
                    return False

        return True
    
    def get(
        self,
        cache_key: str,
        role: Optional[str] = None,
        roles: Optional[Sequence[str]] = None,
        project_ids: Optional[Sequence[str]] = None,
        document_ids: Optional[Sequence[str]] = None,
        is_admin: bool = False,
        document_timestamp_lookup: Optional[Callable[[str], Optional[float]]] = None,
        document_timestamps: Optional[dict[str, float]] = None,
    ) -> Optional[QualityAwareCacheEntry]:
        """
        Get entry from cache with RBAC validation and document freshness check.
        
        If any document cited by this cached answer has been updated (Last_updated),
        the cached response is considered stale, automatically evicted, and None is returned
        so that an LLM-generated answer will be produced with the latest document content.
        
        Returns:
            QualityAwareCacheEntry if found, unexpired, RBAC-authorized, and document is fresh, else None.
        """
        with self._lock:
            entry = self._cache.get(cache_key)
            
            if entry is None:
                self._stats["misses"] += 1
                logger.debug("cache_miss key=%s", cache_key)
                return None
            
            # 1. Check TTL expiry
            if entry.is_expired(self.ttl_seconds):
                self._remove_entry(cache_key)
                self._stats["misses"] += 1
                self._stats["expirations"] += 1
                logger.debug("cache_expired key=%s", cache_key)
                return None

            # 2. RBAC Validation Gate
            if not self._check_rbac_access(
                entry,
                role=role,
                roles=roles,
                project_ids=project_ids,
                document_ids=document_ids,
                is_admin=is_admin,
            ):
                self._stats["misses"] += 1
                self._stats["rbac_denials"] = self._stats.get("rbac_denials", 0) + 1
                logger.debug(
                    "cache_rbac_denied key=%s cache_id=%s assigned_role=%s req_role=%s",
                    cache_key, entry.cache_id, entry.assigned_role, role
                )
                return None

            # 3. Document Freshness / Last_Updated Validation Gate:
            # If any cited document was updated after caching, evict and return None (cache miss -> use LLM)
            if entry.document_ids:
                lookup_fn = document_timestamp_lookup or self.document_timestamp_lookup
                entry_created_at = entry.metadata.created_at
                is_stale = False
                stale_doc = None
                latest_ts = 0.0

                for doc_id in entry.document_ids:
                    current_doc_updated_at = None
                    if document_timestamps and doc_id in document_timestamps:
                        current_doc_updated_at = _to_timestamp(document_timestamps[doc_id])
                    elif lookup_fn:
                        try:
                            raw_ts = lookup_fn(doc_id)
                            if raw_ts is not None:
                                current_doc_updated_at = _to_timestamp(raw_ts)
                        except Exception as exc:
                            logger.debug("Failed looking up updated_at for doc %s: %s", doc_id, exc)

                    if current_doc_updated_at is not None:
                        cached_ts = entry.metadata.doc_last_updated.get(doc_id)
                        if cached_ts is None:
                            cached_ts = entry_created_at
                        else:
                            cached_ts = _to_timestamp(cached_ts)

                        if current_doc_updated_at > cached_ts:
                            is_stale = True
                            stale_doc = doc_id
                            latest_ts = current_doc_updated_at
                            break

                if is_stale:
                    logger.info(
                        "cache_stale_document_detected key=%s doc=%s (cached_ts=%.2f, current_updated_at=%.2f) - evicting stale cache to use LLM",
                        cache_key, stale_doc, cached_ts, latest_ts
                    )
                    self._remove_entry(cache_key)
                    self._stats["misses"] += 1
                    self._stats["stale_document_evictions"] = self._stats.get("stale_document_evictions", 0) + 1
                    return None
            
            # Update LRU and access stats
            entry.update_access()
            self._update_access_order(cache_key)
            
            self._stats["hits"] += 1
            logger.debug(
                "cache_hit key=%s cache_id=%s role=%s confidence=%.2f access_count=%d",
                cache_key, entry.cache_id, entry.assigned_role, entry.confidence, entry.access_count
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
        cache_id: Optional[str] = None,
        assigned_role: Optional[str] = None,
        document_ids: Optional[Sequence[str]] = None,
        project_ids: Optional[Sequence[str]] = None,
        is_public: bool = False,
        doc_last_updated: Optional[dict[str, float]] = None,
    ) -> bool:
        """
        Put entry into cache with unique Cache ID, RBAC document metadata, and document last_updated timestamps.
        (Only stores if CacheQualityValidator approves).
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
        
        # Generate unique Cache ID if not provided
        effective_cache_id = cache_id or f"cch_{uuid.uuid4().hex[:12]}"

        # Auto-extract document references from citations if document_ids not explicitly passed
        docs_list = list(document_ids) if document_ids else []
        if not docs_list and citations:
            extracted_docs = []
            for c in citations:
                src = c.get("source") or c.get("document_id")
                if src and src not in extracted_docs:
                    extracted_docs.append(str(src))
            docs_list = extracted_docs

        projs_list = list(project_ids) if project_ids else []

        # Resolve document last_updated timestamps if not provided
        effective_doc_last_updated = dict(doc_last_updated) if doc_last_updated else {}
        if not effective_doc_last_updated and docs_list:
            now_ts = time.time()
            for doc_id in docs_list:
                ts = None
                if self.document_timestamp_lookup:
                    try:
                        ts = self.document_timestamp_lookup(doc_id)
                    except Exception:
                        ts = None
                effective_doc_last_updated[doc_id] = _to_timestamp(ts) if ts is not None else now_ts

        with self._lock:
            if len(self._cache) >= self.max_entries and cache_key not in self._cache:
                self._evict_lru()
            
            entry_metadata = CacheEntryMetadata(
                cache_id=effective_cache_id,
                assigned_role=assigned_role,
                document_ids=docs_list,
                doc_last_updated=effective_doc_last_updated,
                project_ids=projs_list,
                is_public=is_public,
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
            self._cache_id_to_key[effective_cache_id] = cache_key
            self._update_access_order(cache_key)
            self._stats["writes"] += 1
            
            logger.debug(
                "cache_write key=%s cache_id=%s role=%s docs=%s confidence=%.2f source=%s decision=%s",
                cache_key, effective_cache_id, assigned_role, docs_list, confidence, source_enum.value, validation.decision.value
            )
            return True

    def get_by_cache_id(
        self,
        cache_id: str,
        role: Optional[str] = None,
        roles: Optional[Sequence[str]] = None,
        project_ids: Optional[Sequence[str]] = None,
        document_ids: Optional[Sequence[str]] = None,
        is_admin: bool = False,
        document_timestamp_lookup: Optional[Callable[[str], Optional[float]]] = None,
        document_timestamps: Optional[dict[str, float]] = None,
    ) -> Optional[QualityAwareCacheEntry]:
        """Retrieve a cached entry by its unique Cache ID with RBAC and document freshness enforcement."""
        with self._lock:
            cache_key = self._cache_id_to_key.get(cache_id)
            if not cache_key:
                return None
            return self.get(
                cache_key,
                role=role,
                roles=roles,
                project_ids=project_ids,
                document_ids=document_ids,
                is_admin=is_admin,
                document_timestamp_lookup=document_timestamp_lookup,
                document_timestamps=document_timestamps,
            )

    def delete_by_cache_id(self, cache_id: str) -> bool:
        """Delete a cache entry by its unique Cache ID."""
        with self._lock:
            cache_key = self._cache_id_to_key.get(cache_id)
            if not cache_key:
                return False
            return self.invalidate(cache_key)

    def get_entries_by_role(self, role: str) -> list[QualityAwareCacheEntry]:
        """List all cache entries assigned to a specific role."""
        with self._lock:
            target = role.strip().lower()
            return [
                entry for entry in self._cache.values()
                if entry.assigned_role and entry.assigned_role.strip().lower() == target
            ]

    def get_entries_by_document(self, document_id: str) -> list[QualityAwareCacheEntry]:
        """List all cache entries referencing a specific document."""
        with self._lock:
            target = document_id.strip().lower()
            return [
                entry for entry in self._cache.values()
                if any(doc.strip().lower() == target for doc in entry.document_ids)
            ]

    def invalidate_document(self, document_id: str) -> int:
        """Invalidate all cache entries generated with a specific document."""
        with self._lock:
            target = document_id.strip().lower()
            keys_to_remove = [
                key for key, entry in self._cache.items()
                if any(doc.strip().lower() == target for doc in entry.document_ids)
            ]
            for key in keys_to_remove:
                self._remove_entry(key)
            if keys_to_remove:
                logger.info("cache_invalidated_by_document doc=%s count=%d", document_id, len(keys_to_remove))
            return len(keys_to_remove)

    def invalidate_role(self, role: str) -> int:
        """Invalidate all cache entries assigned to a specific role."""
        with self._lock:
            target = role.strip().lower()
            keys_to_remove = [
                key for key, entry in self._cache.items()
                if entry.assigned_role and entry.assigned_role.strip().lower() == target
            ]
            for key in keys_to_remove:
                self._remove_entry(key)
            if keys_to_remove:
                logger.info("cache_invalidated_by_role role=%s count=%d", role, len(keys_to_remove))
            return len(keys_to_remove)
    
    def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if not self._access_order:
            return
        oldest_key = self._access_order.pop(0)
        if oldest_key in self._cache:
            entry = self._cache[oldest_key]
            if entry.cache_id in self._cache_id_to_key:
                del self._cache_id_to_key[entry.cache_id]
            del self._cache[oldest_key]
            self._stats["evictions"] += 1
            logger.debug("cache_evicted key=%s reason=lru", oldest_key)
    
    def _remove_entry(self, cache_key: str) -> None:
        """Remove entry from cache."""
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if entry.cache_id in self._cache_id_to_key:
                del self._cache_id_to_key[entry.cache_id]
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
            self._cache_id_to_key.clear()
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
                "rbac_denials": self._stats.get("rbac_denials", 0),
                "stale_document_evictions": self._stats.get("stale_document_evictions", 0),
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
    document_timestamp_lookup: Optional[Callable[[str], Optional[float]]] = None,
) -> InMemoryQualityAwareCache:
    """Get the global quality-aware cache instance."""
    global _quality_cache
    if _quality_cache is None:
        _quality_cache = InMemoryQualityAwareCache(
            max_entries=max_entries,
            ttl_seconds=ttl_seconds,
            document_timestamp_lookup=document_timestamp_lookup,
        )
    elif document_timestamp_lookup is not None:
        _quality_cache.document_timestamp_lookup = document_timestamp_lookup
    return _quality_cache