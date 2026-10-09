"""
Cache Domain Entities and Value Objects (ADR v2 Architecture).

Defines structured claims, evidence references, NLI results, and policy decisions
for the simplified deterministic core and hybrid (Jev + NLI) engine.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class NLILabel(str, Enum):
    """Normalized Natural Language Inference classification labels."""
    ENTAILMENT = "ENTAILMENT"
    CONTRADICTION = "CONTRADICTION"
    NEUTRAL = "NEUTRAL"


class PolicyDecision(str, Enum):
    """The 3-state deterministic outcome from the Jev Policy Engine."""
    REUSE = "REUSE"
    REJECT = "REJECT"
    REVALIDATE = "REVALIDATE"


class EvidenceStatus(str, Enum):
    """Evidence validity and hash status."""
    EXACT_MATCH = "EXACT_MATCH"
    MODIFIED_ENTAILED = "MODIFIED_ENTAILED"
    CONTRADICTED = "CONTRADICTED"
    UNKNOWN = "UNKNOWN"


class RiskLevel(str, Enum):
    """Risk tier of the query and cached document domain."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True, slots=True)
class CachedClaim:
    """Discrete factual claim extracted from a cached answer."""
    claim_id: str
    text: str
    evidence_chunk_ids: Tuple[str, ...] = ()
    is_material: bool = True


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """
    Pointer to supporting chunk evidence.
    - chunk_hash: SHA-256 digest, the sole deterministic identity for freshness.
    - document_version: Provenance revision context only.
    """
    document_id: str
    chunk_id: str
    document_version: int
    chunk_hash: str


@dataclass(frozen=True, slots=True)
class ClaimEvidencePair:
    """Pair of claim text and evidence passage prepared for batched NLI."""
    claim_id: str
    claim_text: str
    chunk_id: str
    evidence_text: str


@dataclass(frozen=True, slots=True)
class NLIResult:
    """Result of an NLI cross-encoder verification pass."""
    label: NLILabel
    score: float
    model_id: str = "cross-encoder/nli-deberta-v3-small"
    model_version: str = "v1"


@dataclass(frozen=True, slots=True)
class CacheDecisionInput:
    """Input parameters passed to the Jev Policy Engine for the 3-state decision."""
    cache_id: str
    query_intent: str
    risk_level: RiskLevel
    is_authorized: bool
    evidence_status: EvidenceStatus
    unsupported_claims_count: int
    nli_max_contradiction_score: float
    nli_min_entailment_score: float
    model_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CacheEntry:
    """
    Structured representation of a semantic cache entry adhering to ADR v2.
    Decouples raw storage from validation, claims, and policy tracking.
    """
    cache_id: str
    query: str
    normalized_query: str
    answer: str
    tenant_id: str
    project_id: str
    created_at: datetime
    expires_at: datetime
    claims: List[CachedClaim] = field(default_factory=list)
    evidence: List[EvidenceReference] = field(default_factory=list)
    candidate_confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
