# Architectural Design Record (ADR v2): Semantic Cache Simplification & Hybrid (NLI + Jev) Engine

**Document:** Company_Bot Semantic Cache Redesign, Verification, and Policy Evolution  
**Author:** AI Architecture & Core Engineering Team  
**Status:** Approved for Implementation (Production-Grade RFC)  
**Target Subsystems:** `app/domain/`, `app/use_cases/chat/`, `app/infrastructure/cache/`, `app/infrastructure/semantic/`

---

## Executive Summary

This architecture design record supersedes the initial draft. While the directional thesis remains sound—dismantling the 1,262-line [`InMemoryQualityAwareCache`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/cache/quality_aware_cache.py#L571) into pure storage, deterministic gates, and layered semantic evaluation—this v2 specification resolves key design vulnerabilities:

1. **Claim-Level Grounding:** NLI operates on discrete, stored `CachedClaim` items rather than evaluating whole answer text against whole documents.
2. **Query ↔ Answer Compatibility:** Solves the critical blind spot where evidence entails an answer, but the answer does not address the current query (e.g., employee rules vs. contractor rules).
3. **Decoupled Lifecycle:** Distinguishes **`REJECT`** (runtime routing to RAG) from **`INVALIDATE`** and **`DELETE`** (lifecycle cleanup). Contradictions do not trigger immediate destructive eviction.
4. **Dynamic RBAC Evaluation:** Evaluates live access against source evidence via `AuthorizationService` at read time, rather than comparing static cached role strings.
5. **Event-Driven Verification:** If chunk hashes are unchanged, semantic validation results are reused. NLI is batched and executed only on changed evidence or cache writes.
6. **3-State Policy Decisions:** Jev produces deterministic outcomes: `REUSE`, `REJECT`, or `REVALIDATE`.
7. **Architectural Cohesion:** Retains Company_Bot's existing Hexagonal architecture (`app/domain/`, `app/use_cases/`, `app/infrastructure/`) rather than creating competing folder hierarchies.

---

## Table of Contents
1. [The Revised Architecture](#1-the-revised-architecture)
2. [What Stays: Existing Abstractions](#2-what-stays-existing-abstractions)
3. [Dismantling the Cache Monolith](#3-dismantling-the-cache-monolith)
4. [Phase 0 — Empirical Baseline & Regression Dataset](#4-phase-0--empirical-baseline--regression-dataset)
5. [Domain Model: First-Class Claims & Evidence Identity](#5-domain-model-first-class-claims--evidence-identity)
6. [Evidence Freshness: Chunk Hash vs Document Version Semantics](#6-evidence-freshness-chunk-hash-vs-document-version-semantics)
7. [Query ↔ Answer Compatibility Check](#7-query--answer-compatibility-check)
8. [Claim-Level NLI Verification & Aggregation Policy](#8-claim-level-nli-verification--aggregation-policy)
9. [Read Path: Optimized Event-Driven Execution](#9-read-path-optimized-event-driven-execution)
10. [Write Path: Claim Extraction & Grounding Pipeline](#10-write-path-claim-extraction--grounding-pipeline)
11. [Candidate Quality Validation (Clarifying C.R.E.A.T.E.)](#11-candidate-quality-validation-clarifying-create)
12. [Live Authorization (RBAC Fail-Closed Gate)](#12-live-authorization-rbac-fail-closed-gate)
13. [Cache Lifecycle: Reject vs Invalidate vs Delete](#13-cache-lifecycle-reject-vs-invalidate-vs-delete)
14. [Jev Policy Specification & The 3-State Contract](#14-jev-policy-specification--the-3-state-contract)
15. [Performance Realism & Batched Inference](#15-performance-realism--batched-inference)
16. [Component Audit: Delete, Merge, or Retain](#16-component-audit-delete-merge-or-retain)
17. [Directory Structure: Respecting Hexagonal Architecture](#17-directory-structure-respecting-hexagonal-architecture)
18. [The 12-Stage Implementation Sequence](#18-the-12-stage-implementation-sequence)

---

# 1. The Revised Architecture

### Read Path

```text
                                USER QUERY
                                     │
                                     ▼
                            QueryNormalizer
                                     │
                                     ▼
                           QueryIntentClassifier
                                     │
                                     ▼
                          SemanticCacheService
                                     │
                                     ▼
                          CacheCandidateRetriever
                         (Vector / Semantic Match)
                                     │
                                     ▼
                              Cache Candidate
                                     │
                                     ▼
                       ┌───────────────────────────┐
                       │   Deterministic Gates     │
                       │                           │
                       │ 1. TTL Expiration         │
                       │ 2. Live RBAC (AuthService)│
                       │ 3. Negative Filter        │
                       └─────────────┬─────────────┘
                                     │
                                     ▼
                     Query ↔ Cached Answer Compatibility
                                     │
                       ┌─────────────┴─────────────┐
                       ▼                           ▼
                     FAIL                        PASS
                       │                           │
                   Fall to RAG                     ▼
                                       Evidence Hash Identity
                                                   │
                       ┌───────────────────────────┴───────────────────────────┐
                       ▼                                                       ▼
               ALL HASHES MATCH                                       EVIDENCE CHANGED
             (Reuse Cached NLI)                                                │
                       │                                                       ▼
                       │                                            Batched Claim NLI
                       │                                       (Verify Claims vs New Text)
                       │                                                       │
                       │                                                       ▼
                       │                                              Semantic Aggregation
                       │                                              (Contradiction / Neutral)
                       │                                                       │
                       │                                       ┌───────────────┴───────────────┐
                       │                                       ▼                               ▼
                       │                                  CONTRADICTION                   ENTAILMENT
                       │                                  (Soft-Invalidate                (Update Hash)
                       │                                   & Fall to RAG)                      │
                       │                                                                       │
                       └───────────────────────────────┬───────────────────────────────────────┘
                                                       │
                                                       ▼
                                            Jev Policy Decision
                                          (Risk / Multi-Hop Context)
                                                       │
                                     ┌─────────────────┼─────────────────┐
                                     ▼                 ▼                 ▼
                                   REUSE            REJECT          REVALIDATE
                                     │                 │                 │
                                     ▼                 ▼                 ▼
                                CACHE HIT          Run RAG          Fetch Context
```

### Write Path

```text
RAG Hybrid Retrieval ──► BGE Reranker ──► LLM Answer Generation
                                                │
                                                ▼
                                    Candidate Quality Gate
                                (CandidateConfidence, Distance,
                                  EvidenceCount, NotNegative)
                                                │
                                 ┌──────────────┴──────────────┐
                                 ▼                             ▼
                               FAIL                          PASS
                                 │                             │
                              DISCARD                          ▼
                                                       Claim Extraction
                                                (Decompose Answer into Claims)
                                                               │
                                                               ▼
                                                    Claim ↔ Chunk Alignment
                                                               │
                                                               ▼
                                                      Batched NLI Verification
                                                               │
                                                               ▼
                                                     Grounding Aggregator
                                                (All Material Claims Entailed?)
                                                               │
                                                 ┌─────────────┴─────────────┐
                                                 ▼                           ▼
                                               FAIL                        PASS
                                                 │                           │
                                              DISCARD                        ▼
                                                                     Jev Policy Engine
                                                                 (Safety, PII, High-Risk)
                                                                             │
                                                               ┌─────────────┴─────────────┐
                                                               ▼                           ▼
                                                             DENY                        ALLOW
                                                               │                           │
                                                            DISCARD                        ▼
                                                                                   Write to Cache
                                                                               (with Claims & Hashes)
```

---

# 2. What Stays: Existing Abstractions

We preserve Company_Bot's foundational ports and domain services:
* [`SemanticCachePort`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/domain/ports/cache.py)
* `DocumentRepository` & `ProvenanceService`
* `AuthorizationService` & `AuthorizationEngine`
* `RetrievalPort` & `RerankerPort`
* `QueryNormalizer` & `QueryIntentClassifier`
* [`QueryOrchestrator`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/query_orchestrator.py)

---

# 3. Dismantling the Cache Monolith

[`InMemoryQualityAwareCache`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/cache/quality_aware_cache.py#L571) is stripped of conflicting concerns:

* ❌ **Extracted:** RBAC logic moved to `AuthorizationService`.
* ❌ **Extracted:** Document timestamp polling replaced by `ChunkHasher` SHA-256 evidence identity.
* ❌ **Extracted:** In-memory embedding vector math moved to `CacheCandidateRetriever`.
* ❌ **Extracted:** Regex word-intersection heuristics replaced by `NLIService`.
* ❌ **Extracted:** Telemetry & stats moved to domain event observers.
* ✅ **Retained in Repository:** Pure storage (`get`, `put`, `delete`, LRU eviction bounds).

---

# 4. Phase 0 — Empirical Baseline & Regression Dataset

Before code changes, we establish an empirical baseline across 150+ curated cases:
* 50 normal enterprise queries
* 20 paraphrased queries
* 20 stale-document updates
* 20 numeric policy updates (e.g., 15 days $\to$ 26 days)
* 20 negation flips (e.g., permitted $\to$ strictly prohibited)
* 20 authorization changes (user removed from project)
* 10 negative answers ("I don't know")
* 10 high-risk confidential queries (executive salary/PII)

### Primary Metric Mandate:
$$\text{False Reuse Rate} \ll \text{False Rejection Rate}$$
In an enterprise context, a false cache miss costs tokens and 800ms of latency; a **false cache reuse leaks confidential or incorrect legal/HR policy**.

---

# 5. Domain Model: First-Class Claims & Evidence Identity

`CacheEntry` explicitly stores structured claims:

```python
@dataclass(frozen=True)
class CachedClaim:
    claim_id: str
    text: str
    evidence_chunk_ids: tuple[str, ...]
    is_material: bool = True


@dataclass(frozen=True)
class EvidenceReference:
    document_id: str
    chunk_id: str
    document_version: int      # Provenance / revision context
    chunk_hash: str            # Deterministic SHA-256 content identity


@dataclass
class CacheEntry:
    cache_id: str
    query: str
    normalized_query: str
    answer: str
    tenant_id: str
    project_id: str
    created_at: datetime
    expires_at: datetime
    claims: list[CachedClaim]
    evidence: list[EvidenceReference]
    candidate_confidence: float
    validation_record: Optional["SemanticValidationRecord"] = None
```

---

# 6. Evidence Freshness: Chunk Hash vs Document Version Semantics

We define precise semantics for versioning vs. hashing:
* **`document_version`**: Source revision metadata used for audit trails. A bump in `document_version` does **not** invalidate unchanged chunks.
* **`chunk_hash`**: SHA-256 digest of chunk content. This is the **sole deterministic identity for freshness**.

### Freshness Invariant:
$$\text{Cached Chunk Fresh} \iff \text{Cached } \texttt{chunk\_hash} == \text{Current } \texttt{chunk\_hash}$$

### Changed Evidence $\ne$ Automatic Cache Eviction:
When $\text{cached\_hash} \ne \text{current\_hash}$, the entry is marked **`POTENTIALLY_STALE`**. The system passes the updated chunk and the specific `CachedClaim` to the NLI verifier. If NLI still proves `ENTAILMENT`, the entry's hash reference is updated in place, preventing unnecessary cache churn.

---

# 7. Query ↔ Answer Compatibility Check

> [!IMPORTANT]
> **The Semantic Gap:** Evidence entailing an answer does not guarantee the answer satisfies the current query.

* **Example:** User asks *"What is the parental leave for contractors?"*
* **Cached Answer:** *"Employees receive 26 weeks of parental leave."*
* **Evidence:** Entails the cached answer perfectly.
* **Failure:** Serving this answer is an incorrect response to the user's question.

### The Gate:
Before evaluating evidence, `QueryAnswerCompatibilityValidator` verifies semantic compatibility:
1. Intent matching: `cached_intent == current_query_intent`.
2. Entity alignment: Target subjects (e.g., employee vs. contractor) must not conflict.
3. If incompatible $\to$ **Immediate fail-safe fallback to RAG**.

---

# 8. Claim-Level NLI Verification & Aggregation Policy

### Batched Model Interface
```python
@dataclass(frozen=True)
class ClaimEvidencePair:
    claim_id: str
    claim_text: str
    chunk_id: str
    evidence_text: str

@dataclass(frozen=True)
class NLIResult:
    label: NLILabel        # ENTAILMENT, CONTRADICTION, NEUTRAL
    score: float
    model_id: str
    model_version: str

class EvidenceVerifier(Protocol):
    async def verify_batch(self, pairs: list[ClaimEvidencePair]) -> list[NLIResult]:
        ...
```

### Aggregation Policy (No Arithmetic Averages):
Never use arithmetic score averages ($\text{avg} \ge 0.80$), as averages hide catastrophic single-claim hallucinations.
1. **Contradiction Rule:** If **any** material claim receives `CONTRADICTION` with calibrated confidence $\ge \tau_c$ $\to$ **REJECT**.
2. **Neutral Rule:** If **any** material claim receives `NEUTRAL` (unsupported by retrieved evidence) $\to$ **REJECT**.
3. **Entailment Rule:** Cache reuse is permitted if and only if **100% of material claims** are evaluated as `ENTAILMENT` with calibrated confidence $\ge \tau_e$.

---

# 9. Read Path: Optimized Event-Driven Execution

To avoid running NLI on every cache read:

```python
async def validate_candidate(self, entry: CacheEntry, current_chunks: dict[str, ChunkMetadata]) -> ValidationDecision:
    # 1. Deterministic Gates (TTL, Negative filter)
    if self.is_expired(entry) or self.is_negative(entry.answer):
        return ValidationDecision.REJECT

    # 2. Query/Answer Compatibility
    if not self.check_query_compatibility(entry.query, current_query):
        return ValidationDecision.REJECT

    # 3. Evidence Identity (RAM Hash Check)
    all_hashes_match = all(
        ref.chunk_hash == current_chunks[ref.chunk_id].chunk_hash
        for ref in entry.evidence if ref.chunk_id in current_chunks
    )

    if all_hashes_match:
        # Source evidence is identical to when the answer was cached -> NLI is bypassed
        return ValidationDecision.PASS_DETERMINISTIC

    # 4. Evidence Changed -> Selective Batched NLI on modified chunks only
    stale_pairs = [
        ClaimEvidencePair(c.claim_id, c.text, ref.chunk_id, current_chunks[ref.chunk_id].content)
        for c in entry.claims for ref in entry.evidence
        if ref.chunk_hash != current_chunks[ref.chunk_id].chunk_hash
    ]
    nli_results = await self.verifier.verify_batch(stale_pairs)
    return self.aggregate_nli(nli_results)
```

---

# 10. Write Path: Claim Extraction & Grounding Pipeline

NLI on write exists to protect against LLM hallucinations beyond the retrieved chunks:

1. **LLM Generation:** Produces answer.
2. **Claim Decomposition:** Splits answer into testable factual claims (`ClaimExtractor`).
3. **Alignment:** Maps claims to cited chunk IDs.
4. **Batched NLI:** Evaluates claims against source chunks.
5. **Quality Filter:** Unconfirmed claims cause the answer to be served to the user with a low-confidence flag, but **blocked from entry into the semantic cache**.

---

# 11. Candidate Quality Validation (Clarifying C.R.E.A.T.E.)

We decouple generation quality from semantic grounding:

* **`CacheCandidateQualityValidator`**:
  * **Retrieval Distance:** Cosine distance of source chunks ($< \tau_d$).
  * **Evidence Count:** Must cite $\ge 1$ supporting chunk for RAG.
  * **Composite Model Confidence:** Signal floor calibrated via regression dataset.
  * **Negative Response Guard:** Rejects refusals and empty answers.
* **`EvidenceVerifier` (NLI):**
  * Evaluates deep semantic entailment and claim contradiction.

> [!NOTE]
> All thresholds ($\tau_c, \tau_e, \tau_d$) are **configuration parameters calibrated against the golden dataset**, not rigid architectural invariants.

---

# 12. Live Authorization (RBAC Fail-Closed Gate)

Static string comparisons (`entry.assigned_role == user.role`) fail when a user's permissions change after an answer was cached.

### The Rule:
Authorization must be evaluated dynamically at lookup time against the current principal and the cited evidence:

```python
async def check_authorization(self, user_context: UserContext, entry: CacheEntry) -> bool:
    # Fail-closed evaluation against active AuthorizationService
    return await self.auth_service.can_access_resources(
        user=user_context,
        tenant_id=entry.tenant_id,
        project_id=entry.project_id,
        resource_ids=[ref.document_id for ref in entry.evidence]
    )
```

---

# 13. Cache Lifecycle: Reject vs Invalidate vs Delete

We establish clear boundaries between runtime decisions and data lifecycle:

* **`REJECT` (Routing Decision):** The candidate is unsuitable for the current request. Fall back to RAG immediately. Do not mutate the cache.
* **`INVALIDATE` (Soft State):** Mark the cache entry as invalid or stale. Prevents future lookups while retaining telemetry and provenance data for debugging.
* **`DELETE` (Lifecycle Operation):** Physical purge executed by background LRU eviction or administrative document deletion.

---

# 14. Jev Policy Specification & The 3-State Contract

### The 3 Outcomes
* **`REUSE`**: Answer is fully grounded and policy-compliant. Return immediately.
* **`REJECT`**: Answer violates policy, contains high-risk PII, or conflicts with context. Fall back to RAG.
* **`REVALIDATE`**: Evidence is ambiguous or high-risk. Triggers human-in-the-loop review or re-retrieval.

### State Schema
```python
@dataclass(frozen=True)
class CacheDecisionInput:
    cache_id: str
    query_intent: str
    risk_level: str              # LOW, MEDIUM, HIGH (salary/legal/exec)
    is_authorized: bool
    evidence_status: str         # EXACT_MATCH, MODIFIED_ENTAILED, UNKNOWN
    unsupported_claims_count: int
    nli_max_contradiction_score: float
    nli_min_entailment_score: float
    model_metadata: dict
```

---

# 15. Performance Realism & Batched Inference

* **Latency Expectations:** We do not rely on speculative "15ms" guarantees. Latency scales as $O(K \times C)$ (number of claims $\times$ candidate chunks).
* **Optimization Strategy:**
  1. Hash checks bypass NLI for >80% of warm cache hits.
  2. In-memory batching (`verify_batch`) processes all claim-chunk pairs in a single tensor forward pass.
  3. Quantized ONNX / OpenVINO backends are used for CPU deployment in production containers.

---

# 16. Component Audit: Delete, Merge, or Retain

| Component | Action | Target Location / Responsibility |
| :--- | :--- | :--- |
| `InMemoryQualityAwareCache` | **Dismantle** | Split into `InMemorySemanticCacheRepository` and validator pipeline |
| `SemanticCachePort` | **Retain** | Core domain port in `app/domain/ports/cache.py` |
| `DualCache` | **Simplify** | Retain as secondary storage adapter behind `SemanticCachePort` |
| `CacheQualityValidator` | **Refactor** | Focused solely on candidate qualification (C.R.E.A.T.E. signals) |
| Regex Lexical Grounding | **Remove** | Replaced by `EvidenceVerifier` |
| Coarse Timestamp Polling | **Remove** | Replaced by `ChunkHasher` SHA-256 evidence identity |
| `QueryAnswerCompatibilityValidator` | **New** | Guarantees cached answer matches current query intent |
| `NLIService` | **New** | Batched claim-level verification (`app/infrastructure/semantic/`) |
| `JevDecisionProvider` | **New (Phase 3)**| 3-state macro policy engine |

---

# 17. Directory Structure: Respecting Hexagonal Architecture

We place all components inside Company_Bot's existing architectural structure:

```text
app/
├── domain/
│   ├── entities/
│   │   └── cache.py           # CacheEntry, CachedClaim, EvidenceReference, CacheScope
│   └── ports/
│       ├── cache.py           # SemanticCachePort, SemanticCacheRepository
│       ├── nli.py             # EvidenceVerifier protocol, ClaimEvidencePair, NLIResult
│       └── decision.py        # DecisionProvider protocol, CacheDecisionInput
│
├── use_cases/
│   └── chat/
│       ├── semantic_cache_service.py     # Main cache orchestration
│       ├── query_answer_compatibility.py # Query/Answer check
│       └── claim_extractor.py            # Answer decomposition into claims
│
└── infrastructure/
    ├── cache/
    │   ├── memory_repository.py          # Pure LRU storage
    │   ├── dual_cache.py                 # LangCache + JSON fallback adapter
    │   └── validators/                   # TTL, RBAC, Freshness, NegativeResponse
    ├── semantic/
    │   ├── deberta_nli.py                # Batched Cross-Encoder implementation
    │   └── jev_adapter.py                # Typesafe Jev System One client
    └── document/
        └── chunk_hasher.py               # SHA-256 chunk identity tracker
```

---

# 18. The 12-Stage Implementation Sequence

```text
Stage 1:  Freeze baseline behavior & compile 150-case regression dataset
Stage 2:  Extract repository (InMemorySemanticCacheRepository) — pure storage
Stage 3:  Extract deterministic gates (TTL, Live RBAC, Negative response filter)
Stage 4:  Implement ChunkHasher & replace document-level timestamp polling
Stage 5:  Regression checkpoint 1: Verify zero behavioral drift vs baseline
Stage 6:  Implement Query ↔ Answer compatibility check
Stage 7:  Implement CachedClaim data model & ClaimExtractor
Stage 8:  Implement EvidenceVerifier with batched DeBERTa Cross-Encoder
Stage 9:  Benchmark NLI: Measure contradiction recall & false reuse rate
Stage 10: Define DecisionProvider contract & implement Jev 3-state adapter
Stage 11: Benchmark full hybrid pipeline (Jev + NLI vs simplified baseline)
Stage 12: Production hardening: ONNX quantization, circuit breakers, and telemetry
```