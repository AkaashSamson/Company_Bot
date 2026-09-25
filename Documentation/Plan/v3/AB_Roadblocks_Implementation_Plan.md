# Master Implementation Plan: Fixing All 14 AB Architectural Roadblocks

> **Document:** AB Phase 3 Roadblocks Remediation & Engineering Implementation Plan  
> **Author / Lead:** **`AB`** (Abhinav Bargi - Infrastructure, Caching & Observability)  
> **Peer Reviewers:** **`AK`** (Akaash Samson), **`NE`** (Neha), **`RO`** (Roshan)  
> **Scope:** Exhaustive one-by-one technical resolution for all 14 roadblocks owned by Abhinav Bargi (`RB01`, `RB02`, `RB04`, `RB05`, `RB10`, `RB12`, `RB16`, `RB17`, `RB20`, `RB23`, `RB25`, `RB26`, `RB28`, `RB29`)  
> **Version:** 3.0.0 (Production Hardening)  
> **Status:** Ready for Execution  

---

## Executive Summary & Dependency Roadmap

This implementation plan establishes a step-by-step engineering roadmap to eliminate all 14 production failure modes, performance bottlenecks, and security vulnerabilities identified in the master roadblocks catalog. 

Every roadblock is addressed **one by one** with:
1. **Current Vulnerability & Root Cause** in existing source files
2. **Failure Sequence & Dataflow** (using clean ASCII art diagrams)
3. **Step-by-Step Code Changes** (exact files, class additions, method signatures, logic changes)
4. **Edge Cases & Boundary Defenses**
5. **Concrete Test Strategy** (unit test files, mock fixtures, regression assertions)
6. **Definition of Done & Verification Gate**

```text
+========================================================================================+
|                        AB ROADBLOCK REMEDIATION PHASING                                |
+========================================================================================+
|                                                                                        |
|  [PHASE 1: SECURITY & AUTH ISOLATION]                                                  |
|  +-------------------------------------+   +-------------------------------------+     |
|  | RB12: Cache Tenant/Role Isolation   |-->| RB28: PII Sanitization in Telemetry |     |
|  | Lead: AB | Review: RO | Task: AB-4  |   | Lead: AB | Review: RO | Task: AB-6.1|     |
|  +-------------------------------------+   +-------------------------------------+     |
|                   |                                                                    |
|                   v                                                                    |
|  [PHASE 2: VECTOR STORE & EMBEDDING LIFECYCLE]                                         |
|  +-------------------------------------+   +-------------------------------------+     |
|  | RB01: Embedding Dimension Migration |-->| RB05: Unicode NFKC Cache Deletion   |     |
|  | Lead: AB | Review: NE | Task: AB-4  |   | Lead: AB | Review: NE | Task: AB-3.1|     |
|  +-------------------------------------+   +-------------------------------------+     |
|                   |                                                                    |
|                   v                                                                    |
|  [PHASE 3: SEMANTIC CACHING & NLP FIDELITY]                                            |
|  +-------------------------------------+   +-------------------------------------+     |
|  | RB02: Negation & Polarity Gate      |-->| RB29: Adaptive Similarity Thresholds|     |
|  | Lead: AB | Review: AK | Task: AB-3.1|   | Lead: AB | Review: AK | Task: AB-4  |     |
|  +-------------------------------------+   +-------------------------------------+     |
|         |                                         |                                    |
|         v                                         v                                    |
|  +-------------------------------------+   +-------------------------------------+     |
|  | RB04: Cold-Start Double-Check Lock  |   | RB10: Jargon / Transliteration Dict |     |
|  | Lead: AB | Review: AK | Task: AB-4  |   | Lead: AB | Review: NE | Task: AB-3.1|     |
|  +-------------------------------------+   +-------------------------------------+     |
|                   |                                                                    |
|                   v                                                                    |
|  [PHASE 4: LLM RESILIENCE & CIRCUIT BREAKERS]                                          |
|  +-------------------------------------+   +-------------------------------------+     |
|  | RB16: Adaptive Circuit Breaker      |-->| RB17: Strict JSON Citation Enforcer |     |
|  | Lead: AB | Review: AK | Task: AB-1.1|   | Lead: AB | Review: AK | Task: AB-2  |     |
|  +-------------------------------------+   +-------------------------------------+     |
|                   |                                                                    |
|                   v                                                                    |
|  [PHASE 5: RESOURCE BOUNDS & ASYNC OBSERVABILITY]                                      |
|  +-------------------------------------+   +-------------------------------------+     |
|  | RB23: Memory-Bounded LRU & TTL      |-->| RB20: Non-Blocking Logging Worker   |     |
|  | Lead: AB | Review: AK | Task: AB-4  |   | Lead: AB | Review: NE | Task: AB-1.1|     |
|  +-------------------------------------+   +-------------------------------------+     |
|         |                                         |                                    |
|         v                                         v                                    |
|  +-------------------------------------+   +-------------------------------------+     |
|  | RB25: Connection Pool Socket Reuse  |-->| RB26: Non-Blocking Trace Serialize  |     |
|  | Lead: AB | Review: AK | Task: AB-6.1|   | Lead: AB | Review: AK | Task: AB-6.1|     |
|  +-------------------------------------+   +-------------------------------------+     |
|                                                                                        |
+========================================================================================+
```

---

## Detailed Implementation Plan (One by One)

---

### Roadblock 1: RB12 - Privilege Escalation via Cached Responses Across Differing User Role Scopes

- **Roadblock ID:** `RB12`
- **Severity / Blast Radius:** `CRITICAL` | Cross-tenant data breach; unauthorized employees obtain cached confidential executive/payroll answers.
- **Team Ownership:** **`AB`** (Abhinav Bargi) | **Peer Review:** **`RO`** (Roshan - Auth & Security)
- **Task Codes:** `[AB-4]`, `[RO-3.1]`, `[AK-1.3]`
- **Subsystem Focus:** `[Security, CacheIsolation]` - Scoped Cache Keys & Auth Isolation

#### 1. Current Vulnerability in Code
In [app/use_cases/chat/query_orchestrator.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/query_orchestrator.py#L460-L466) and [app/infrastructure/cache/quality_aware_cache.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/cache/quality_aware_cache.py), cache lookups are keyed solely by `cache_key` (normalized question string) or `question`:
```python
# CURRENT FLAW: Ignores tenant, role, and authorized_project_ids!
cached_entry = self.response_cache.get(cache_key)
if cached_entry is None:
    cached_entry = self.response_cache.get(question)
```
If an Executive queries *"What is the executive bonus allocation formula?"*, the response is cached under `"what is the executive bonus allocation formula"`. When an Intern asks the same question, `self.response_cache.get(...)` returns the cached admin answer, completely bypassing RBAC and metadata filtering.

#### 2. Architectural Solution Dataflow
```text
+---------------------------------------------------------------------------------+
| RB12 ARCHITECTURE: Role & Tenant Scoped Cache Key Hash                          |
+---------------------------------------------------------------------------------+
| Incoming Request: User (role='intern', projects=['PRJ-PUBLIC'], query='Bonus')   |
|                                                                                 |
| 1. Extract Auth Context: role, tenant_id, sorted(authorized_project_ids)        |
| 2. Compute Auth Hash: SHA256(role + ":" + tenant_id + ":" + sorted_projects)   |
| 3. Construct Scoped Cache Key: f"{auth_hash}:{normalized_query}"                |
|                                                                                 |
| Cache Check:                                                                    |
|   Lookup key "a1b2c3d4:bonus" in InMemoryQualityAwareCache                      |
|   --> MISS (Admin cache was stored under "e9f8a7b6:bonus")                      |
|   --> Fallthrough to RetrievalService with strict ChromaDB where={"project_id"} |
+---------------------------------------------------------------------------------+
```

#### 3. Step-by-Step Code Changes
1. **Modify `app/infrastructure/cache/quality_aware_cache.py`**:
   - Add helper method `generate_scoped_key(query: str, role: str, tenant_id: str, project_ids: list[str]) -> str`.
   - Update `InMemoryQualityAwareCache.get(key, auth_context=None)` and `put(key, value, auth_context=None)`.
   - Store `required_role` and `authorized_project_ids` inside `CacheEntryMetadata`.
2. **Modify `app/use_cases/chat/query_orchestrator.py`**:
   - In `answer(query, session_id, principal=None)`:
   - Extract `role = principal.role if principal else "anonymous"` and `projects = tuple(sorted(principal.project_ids or []))`.
   - Pass `auth_context={"role": role, "tenant_id": principal.tenant_id, "project_ids": projects}` into all `response_cache.get(...)` and `response_cache.put(...)` invocations.

#### 4. Edge Cases Handled
- **Public / Unauthenticated FAQs:** If `project_ids` is empty and role is `"public"`, cache key uses canonical hash `public:common:<query>` to retain cross-user cache hits on general policies (e.g. office holidays).
- **Role Escalation:** If a user's role is updated in SQLite, their previous scoped cache key is not invalidated immediately, but they immediately generate new keys matching their new role.

#### 5. Verification & Test Strategy
- **New Test File:** `tests/unit/test_cache_role_isolation.py`
  - `test_admin_cached_response_not_visible_to_intern()`: Admin seeds sensitive query into cache; Intern queries same string; assert cache miss and LLM is not bypassed.
  - `test_public_faq_reusable_across_all_roles()`: Verify that generic HR queries tagged `is_public=True` are shared safely across all roles without duplication.

---

### Roadblock 2: RB28 - PII and Sensitive Salary Information Leakage into Pipeline Tracer Log Spans

- **Roadblock ID:** `RB28`
- **Severity / Blast Radius:** `CRITICAL` | GDPR, HIPAA, and compliance breach; plaintext employee salaries, bank details, and medical leave reasons leak into cloud tracing spans.
- **Team Ownership:** **`AB`** (Abhinav Bargi) | **Peer Review:** **`RO`** (Roshan - Auth & Security)
- **Task Codes:** `[AB-6.1]`, `[RO-3.1]`, `[NE-1.1]`
- **Subsystem Focus:** `[Security, PIIScrubbing]` - PII Regex Masking & Sensitive Logs

#### 1. Current Vulnerability in Code
In [app/infrastructure/observability/pipeline_tracer.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/observability/pipeline_tracer.py), query inputs, retrieved context chunks, and LLM generated outputs are attached directly to span metadata without data sanitation:
```python
# CURRENT FLAW: Raw query and generated response logged directly to trace spans
span.metadata["query"] = query
span.metadata["response"] = response
span.metadata["evidence"] = [chunk.text for chunk in evidence]
```

#### 2. Architectural Solution Dataflow
```text
+---------------------------------------------------------------------------------+
| RB28 ARCHITECTURE: Streaming Regex PII Redactor in PipelineTracer               |
+---------------------------------------------------------------------------------+
| Incoming Trace Payload: "Employee John Doe (SSN: 123-45-6789) Salary: $185,000" |
|                                                                                 |
|                        +----------------------------+                           |
|                        |   PIIRedactor Subsystem    |                           |
|                        +----------------------------+                           |
|                        |  - SSN / Aadhaar Regex     |                           |
|                        |  - Salary / Currency Regex |                           |
|                        |  - Credit Card / IBAN      |                           |
|                        |  - Email & Phone Redaction |                           |
|                        +----------------------------+                           |
|                                       |                                         |
|                                       v                                         |
| Clean Trace Span: "Employee John Doe (SSN: [REDACTED_SSN]) Salary: [REDACTED_SALARY]"|
+---------------------------------------------------------------------------------+
```

#### 3. Step-by-Step Code Changes
1. **Create `app/infrastructure/security/pii_scrubber.py`**:
   - Implement `PIIScrubber` with compiled regular expressions for:
     - Social Security Numbers (`^\d{3}-\d{2}-\d{4}$`)
     - Phone Numbers & Email Addresses
     - Compensation / Salary amounts (`\$\d{1,3}(,\d{3})*(\.\d{2})?|\b(INR|USD|EUR)\s*\d+`)
     - Bank Account / IBAN numbers
   - Provide `scrub_text(text: str) -> str` and `scrub_dict(data: dict) -> dict`.
2. **Modify `app/infrastructure/observability/pipeline_tracer.py`**:
   - Integrate `PIIScrubber.scrub_text()` inside `trace_stage()` and `record_span()`.
   - Scrub `query`, `response`, and `evidence` strings before persisting in memory or exporting to LangFuse/LangSmith.

#### 4. Edge Cases Handled
- **Structured JSON Logs:** Recursively scrub nested dictionaries and lists in span metadata without breaking JSON syntax.
- **Over-Redaction:** Ensure standard company policy clauses (e.g. *"Policy Section 401(k)"*) are not falsely redacted as SSNs or salaries.

#### 5. Verification & Test Strategy
- **New Test File:** `tests/unit/test_pipeline_tracer_pii_scrubbing.py`
  - `test_pii_scrubber_masks_ssn_salary_email()`: Assert raw text containing salaries and phone numbers is redacted.
  - `test_pipeline_tracer_span_contains_no_raw_pii()`: Execute end-to-end trace with sensitive prompt; verify zero PII in `tracer.get_traces()`.

---

### Roadblock 3: RB01 - Vector Store Dimension Mismatch on Embedding Model Hot-Swaps

- **Roadblock ID:** `RB01`
- **Severity / Blast Radius:** `CRITICAL` | Total system retrieval failure; HTTP 500 on all queries after model change due to matrix broadcasting exceptions.
- **Team Ownership:** **`AB`** (Abhinav Bargi) | **Peer Review:** **`NE`** (Neha - Ingestion & Vector Storage)
- **Task Codes:** `[AB-4]`, `[NE-6.3]`, `[AB-5.1]`
- **Subsystem Focus:** `[Infrastructure, VectorDB]` - Embedding Model Registry & Vector Migrations

#### 1. Current Vulnerability in Code
In [app/infrastructure/vector/chroma_client.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/vector/chroma_client.py#L33) and [app/infrastructure/faq/faq_similarity_cache.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/faq/faq_similarity_cache.py), the embedding model name is hardcoded or loaded from `EMBEDDING_MODEL` without validating existing ChromaDB collection metadata. If an engineer switches from `all-MiniLM-L6-v2` (384-dim) to `bge-large-en-v1.5` (1024-dim), numpy matrix multiplications `@` crash with `ValueError: operands could not be broadcast together`.

#### 2. Architectural Solution Dataflow
```text
+---------------------------------------------------------------------------------+
| RB01 ARCHITECTURE: Model Registry & Dynamic Collection Versioning               |
+---------------------------------------------------------------------------------+
| Startup Check:                                                                  |
|   1. Query active EMBEDDING_MODEL ("bge-large-en-v1.5") --> Dim = 1024          |
|   2. Read ChromaDB Collection Metadata: {"embedding_dim": 384, "model": "mini"}  |
|                                                                                 |
| Decision Branch:                                                                |
|   IF collection.dim != model.dim:                                               |
|     +-> Log WARN: Dimension mismatch detected (Collection: 384, Model: 1024)    |
|     +-> Auto-switch active collection to "documents_bge_large_1024"             |
|     +-> Invalidate stale FAQ matrix cache (.npy checksum mismatch)              |
|     +-> Trigger background reindex task or fallback to legacy adapter           |
+---------------------------------------------------------------------------------+
```

#### 3. Step-by-Step Code Changes
1. **Modify `app/infrastructure/vector/chroma_client.py`**:
   - In `__init__`, inspect `self.collection.metadata.get("dimension")`.
   - Dynamically compute model dimension on startup (`model.get_sentence_embedding_dimension()`).
   - If dimension differs, create/load versioned collection name: `f"{self.collection_name}_{dim}"`.
   - Prevent runtime crash by raising clear descriptive error `VectorDimensionMismatchError` with auto-migration instructions.
2. **Modify `app/infrastructure/faq/faq_similarity_cache.py`**:
   - Store model metadata header in `.npy` and `.json` cache files (`{"model": EMBEDDING_MODEL, "dim": dim, "checksum": md5}`).
   - On `_load_or_build_matrix()`, verify that cached `.npy` matches current model dimension before assigning `self._matrix`.

#### 4. Edge Cases Handled
- **Zero-Vector Collections:** Fresh installations with empty collections auto-populate metadata without raising migration errors.
- **Corrupted Cache File:** If `.npy` file has mismatched shape, automatically purge and rebuild from `data/faqs.json`.

#### 5. Verification & Test Strategy
- **New Test File:** `tests/unit/test_vector_dimension_guard.py`
  - `test_faq_cache_purges_on_dimension_mismatch()`: Mock a 384-dim `.npy` file, instantiate cache with 512-dim mock model, verify automatic rebuild without crash.
  - `test_chroma_versioned_collection_creation()`: Verify ChromaClient creates isolated collection when dimension changes.

---

### Roadblock 4: RB05 - Cache Invalidation Poison Pill: Unicode Normalization Mismatch in Deletion

- **Roadblock ID:** `RB05`
- **Severity / Blast Radius:** `MEDIUM` | Silent cache corruption; deleted FAQs reappear indefinitely because smart quotes/spaces prevent deletion matches.
- **Team Ownership:** **`AB`** (Abhinav Bargi) | **Peer Review:** **`NE`** (Neha - Ingestion & Document)
- **Task Codes:** `[AB-3.1]`, `[NE-6.1]`, `[AB-4]`
- **Subsystem Focus:** `[DataQuality, UnicodeNorm]` - Unicode NFKC Normalization Pipeline

#### 1. Current Vulnerability in Code
In [app/infrastructure/faq/faq_similarity_cache.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/faq/faq_similarity_cache.py#L90-L98):
```python
# CURRENT FLAW: Simple equality comparison fails on Unicode variants!
target = question.strip()
filtered_faqs = [faq for faq in self.faqs if faq.get("question", "").strip() != target]
```
If `data/faqs.json` contains smart quotes (`“What is leave?”`), and the user/UI submits standard ASCII quotes (`"What is leave?"`), `faq.get("question") != target` evaluates to `True`, so zero records are removed.

#### 2. Architectural Solution Dataflow
```text
+---------------------------------------------------------------------------------+
| RB05 ARCHITECTURE: Strict Unicode NFKC Canonical Equivalence Layer             |
+---------------------------------------------------------------------------------+
| Storage Question: "Can I take ‘unpaid’ leave\u00A0today?"  (Smart quote + NBSP) |
| Deletion Query:   "Can I take 'unpaid' leave today?"       (ASCII quote + Space)|
|                                                                                 |
|                        +----------------------------+                           |
|                        | Unicode Normalizer (NFKC)  |                           |
|                        +----------------------------+                           |
|                        | - unicodedata.normalize    |                           |
|                        | - Replace NBSP (\u00A0->' ')|                          |
|                        | - Normalize curly quotes   |                           |
|                        | - Strip zero-width chars   |                           |
|                        +----------------------------+                           |
|                                       |                                         |
|                                       v                                         |
| Storage Hash:  "can i take 'unpaid' leave today?"                               |
| Deletion Hash: "can i take 'unpaid' leave today?"                               |
| Result: EXACT MATCH -> Successfully deleted from both JSON & Matrix!            |
+---------------------------------------------------------------------------------+
```

#### 3. Step-by-Step Code Changes
1. **Modify `app/use_cases/chat/query_normalizer.py`**:
   - Add canonical Unicode normalization function:
     ```python
     def canonicalize_unicode(text: str) -> str:
         if not text: return ""
         text = unicodedata.normalize("NFKC", text)
         text = text.replace("\u2018", "'").replace("\u2019", "'")
         text = text.replace("\u201c", '"').replace("\u201d", '"')
         text = text.replace("\u00a0", " ").replace("\u200b", "")
         return " ".join(text.split()).strip()
     ```
2. **Modify `app/infrastructure/faq/faq_similarity_cache.py`**:
   - Use `canonicalize_unicode()` when comparing queries inside `delete_entry()`, `find_similar()`, and `_load_or_build_matrix()`.

#### 4. Edge Cases Handled
- **Diacritics & Accents:** Ensure words like `Café` and `Cafe` are normalized without breaking foreign language names.
- **Empty / Null Strings:** Safely return empty string without raising exceptions.

#### 5. Verification & Test Strategy
- **New Test File:** `tests/unit/test_unicode_cache_deletion.py`
  - `test_delete_entry_with_smart_quotes_and_nbsp()`: Seed FAQ with smart quotes & `\u00a0`; execute `delete_entry()` with standard ASCII quotes; verify entry is removed and count decreases by 1.

---

### Roadblock 5: RB02 - Semantic Cache Collision Across Contrasting Polarities (Negation Blindness)

- **Roadblock ID:** `RB02`
- **Severity / Blast Radius:** `HIGH` | Incorrect policy answers served to employees; high legal and HR compliance liability.
- **Team Ownership:** **`AB`** (Abhinav Bargi) | **Peer Review:** **`AK`** (Akaash Samson - Core Orchestration)
- **Task Codes:** `[AB-3.1]`, `[AB-4]`, `[AK-5.2]`
- **Subsystem Focus:** `[Caching, SemanticNLP]` - Negation & Polarity Semantic Layer

#### 1. Current Vulnerability in Code
Small embedding models (`all-MiniLM-L6-v2`) embed *"Are contract workers entitled to annual leave?"* and *"Are contract workers NOT entitled to annual leave?"* with cosine similarity > 0.94. The semantic cache evaluates `sim >= 0.92` and returns the cached answer for the opposite polarity, answering *"No"* when the user asked who is *not* entitled.

#### 2. Architectural Solution Dataflow
```text
+---------------------------------------------------------------------------------+
| RB02 ARCHITECTURE: Polarity Gate & Negation Disambiguation Filter               |
+---------------------------------------------------------------------------------+
| Query: "Are contractors NOT entitled to annual leave?"                          |
| Candidate Cached Match: "Are contractors entitled to annual leave?" (Sim=0.94)  |
|                                                                                 |
|                        +----------------------------+                           |
|                        | Polarity & Negation Check  |                           |
|                        +----------------------------+                           |
|                        | Query has negation: TRUE   |                           |
|                        | Target has negation: FALSE |                           |
|                        +----------------------------+                           |
|                                       |                                         |
|                                       v                                         |
| Gate Decision: POLARITY_MISMATCH -> Reject Cache Hit                            |
| Action: Route to LLM Generation with Grounded Evidence                          |
+---------------------------------------------------------------------------------+
```

#### 3. Step-by-Step Code Changes
1. **Modify `app/use_cases/chat/query_normalizer.py`**:
   - Implement `extract_polarity_signature(text: str) -> dict`:
     - Detect presence and scope of negation tokens: `not, no, never, neither, nor, without, cannot, except, excluded`.
     - Return boolean `has_negation` and set of modified tokens.
2. **Modify `app/infrastructure/cache/quality_aware_cache.py` and `faq_similarity_cache.py`**:
   - Before accepting a similarity match (even if `similarity >= 0.92`), compare polarity signatures of incoming query and matched candidate.
   - If `query_polarity != candidate_polarity`, reject cache hit and log `cache_bypass reason=polarity_mismatch`.

#### 4. Edge Cases Handled
- **Double Negatives:** *"Is it not uncommon to..."* parsed correctly to avoid false polarity rejections.
- **Negation in Proper Nouns:** Words like *"No-Fault Insurance"* treated as domain entities rather than boolean question negation.

#### 5. Verification & Test Strategy
- **New Test File:** `tests/unit/test_negation_polarity_cache_gate.py`
  - `test_negated_query_does_not_hit_affirmative_cached_faq()`: Verify query with "not" bypasses cache hit when similarity is 0.95.

---

### Roadblock 6: RB29 - Semantic Similarity Threshold Drift Under Domain Jargon Expansion

- **Roadblock ID:** `RB29`
- **Severity / Blast Radius:** `HIGH` | False cache hits return irrelevant answers to nuanced policy questions sharing generic corporate vocabulary.
- **Team Ownership:** **`AB`** (Abhinav Bargi) | **Peer Review:** **`AK`** (Akaash Samson - Core Orchestration)
- **Task Codes:** `[AB-3.1]`, `[AB-4]`, `[AB-5.1]`
- **Subsystem Focus:** `[NLP, SemanticThresholds]` - Adaptive Thresholds & Semantic Jargon

#### 1. Current Vulnerability in Code
In [app/core/settings.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/core/settings.py), `SIMILARITY_THRESHOLD = 0.92` is statically applied to all queries. Questions like *"Leave without pay for medical emergency"* and *"Leave without pay for educational sabbatical"* share 80% lexical overlap, producing similarity 0.925 and serving wrong policy terms.

#### 2. Architectural Solution Dataflow
```text
+---------------------------------------------------------------------------------+
| RB29 ARCHITECTURE: Dynamic Confidence Scoring & Lexical Separation Gap          |
+---------------------------------------------------------------------------------+
| Incoming Match: Similarity = 0.93                                               |
|                                                                                 |
| Composite Scoring Formula:                                                      |
|   Final_Confidence = (0.70 * Cosine_Similarity) +                               |
|                      (0.20 * Jaccard_Noun_Overlap) +                            |
|                      (0.10 * Separation_Gap_Top1_Top2)                          |
|                                                                                 |
| If Top1 is 0.93 but Top2 is 0.928 (Separation Gap < 0.02):                      |
|   -> Ambiguous clustering detected!                                             |
|   -> Adaptive threshold raised from 0.92 to 0.96                                |
|   -> Result: Safe cache bypass; routed to RAG retrieval with precise context.   |
+---------------------------------------------------------------------------------+
```

#### 3. Step-by-Step Code Changes
1. **Modify `app/infrastructure/cache/quality_aware_cache.py`**:
   - In `CacheQualityValidator`, implement dynamic thresholding:
     - Compute separation margin between 1st and 2nd closest matches.
     - Factor in keyword overlap (Jaccard similarity on non-stopwords).
     - Require minimum separation gap of `0.025` for high-risk domains (leave, salary, severance).
2. **Modify `app/infrastructure/faq/faq_similarity_cache.py`**:
   - Implement `find_similar_adaptive(query_text, base_threshold=0.92)` using top-2 separation gating.

#### 4. Edge Cases Handled
- **Single-FAQ Collections:** If only 1 FAQ exists, separation gap check is ignored to prevent false misses.
- **Short Queries:** Queries < 4 words require higher cosine threshold (0.95) due to vector space crowding.

#### 5. Verification & Test Strategy
- **New Test File:** `tests/unit/test_adaptive_similarity_threshold.py`
  - `test_closely_clustered_questions_trigger_cache_bypass()`: Test two closely phrased questions; assert separation gap check triggers bypass.

---

### Roadblock 7: RB04 - FAQ Cache Cold-Start Thundering Herd and Embedding Model Lock Contention

- **Roadblock ID:** `RB04`
- **Severity / Blast Radius:** `HIGH` | Pod startup timeout; 60+ second API response delays on cold restarts under concurrent request surges.
- **Team Ownership:** **`AB`** (Abhinav Bargi) | **Peer Review:** **`AK`** (Akaash Samson - Core Orchestration)
- **Task Codes:** `[AB-4]`, `[AK-1.1]`, `[AB-6.1]`
- **Subsystem Focus:** `[Infrastructure, ColdStart]` - Lazy Loading & Thread Locks

#### 1. Current Vulnerability in Code
In [app/infrastructure/faq/faq_similarity_cache.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/faq/faq_similarity_cache.py), `_load_or_build_matrix()` is executed lazily on first query without double-checked locking or precomputed warm-up:
```python
# CURRENT FLAW: Multiple threads enter simultaneously on boot!
if self._matrix is None:
    self._load_or_build_matrix()
```

#### 2. Architectural Solution Dataflow
```text
+---------------------------------------------------------------------------------+
| RB04 ARCHITECTURE: Double-Checked Locking & Precomputed Cache Warmup            |
+---------------------------------------------------------------------------------+
| 50 Concurrent Requests Arrive at Boot:                                          |
|                                                                                 |
| Thread 1..50 Check: if self._matrix is None:                                    |
|   |                                                                             |
|   +--> Thread 1 acquires self._init_lock                                        |
|   |    Threads 2..50 wait on lock                                               |
|   |                                                                             |
|   +--> Thread 1 re-checks: if self._matrix is None:                             |
|   |    Loads memory-mapped .npy in 12ms (or computes embeddings)                |
|   |    Sets self._initialized = True                                            |
|   |    Releases lock                                                            |
|   |                                                                             |
|   +--> Threads 2..50 acquire lock -> see self._initialized is True -> RETURN!    |
|   Total delay for threads 2..50: < 1ms instead of 50x redundant encodes.       |
+---------------------------------------------------------------------------------+
```

#### 3. Step-by-Step Code Changes
1. **Modify `app/infrastructure/faq/faq_similarity_cache.py`**:
   - Add `self._init_lock = threading.Lock()`.
   - Implement strict double-checked locking in `_ensure_initialized()`:
     ```python
     if not self._initialized:
         with self._init_lock:
             if not self._initialized:
                 self._load_or_build_matrix()
                 self._initialized = True
     ```
   - Add eager warm-up method `warmup()` invoked during FastAPI lifecycle startup event.
2. **Modify `app/api/dependencies.py`**:
   - Warm up `FAQSimilarityCache` and `ChromaClient` inside FastAPI `@app.on_event("startup")`.

#### 4. Edge Cases Handled
- **Failed Initialization:** If model download or disk read fails inside lock, reset state cleanly and raise error rather than deadlocking subsequent threads.

#### 5. Verification & Test Strategy
- **New Test File:** `tests/unit/test_faq_cache_concurrency_lock.py`
  - `test_concurrent_cold_start_executes_encoding_once()`: Spawn 20 threads simultaneously querying uninitialized cache; assert `model.encode` called exactly once.

---

### Roadblock 8: RB10 - Language & Dialect Transliteration Hallucination in Semantic Document Retrieval

- **Roadblock ID:** `RB10`
- **Severity / Blast Radius:** `MEDIUM` | Zero retrieval matches for non-English queries or technical corporate abbreviations.
- **Team Ownership:** **`AB`** (Abhinav Bargi) | **Peer Review:** **`NE`** (Neha - Ingestion & Document)
- **Task Codes:** `[AB-3.1]`, `[AB-3.3]`, `[NE-4.1]`
- **Subsystem Focus:** `[QueryNLP, Terminology]` - Terminology Dictionary & Transliteration

#### 1. Current Vulnerability in Code
In [app/use_cases/chat/query_normalizer.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/query_normalizer.py#L51), `DOMAIN_VOCABULARY` only handles basic standard English terms (e.g. `"sick leave"`). Slang and corporate shorthand (`"p-leave"`, `"comp-off"`, `"WFH policy"`, `"chutti"`) are not expanded, causing semantic vector distance > 0.60.

#### 2. Architectural Solution Dataflow
```text
+---------------------------------------------------------------------------------+
| RB10 ARCHITECTURE: Multi-Dialect Corporate Acronym & Synonym Expander           |
+---------------------------------------------------------------------------------+
| User Query: "How many comp-off days for working Sunday?"                        |
|                                                                                 |
|                        +----------------------------+                           |
|                        | Acronym & Dialect Normalizer|                          |
|                        +----------------------------+                           |
|                        | "comp-off" -> "compensatory off leave"                 |
|                        | "p-leave"  -> "paternity leave" / "privilege leave"    |
|                        | "wfh"      -> "work from home remote work"             |
|                        +----------------------------+                           |
|                                       |                                         |
|                                       v                                         |
| Expanded Query: "How many compensatory off leave days for working Sunday?"      |
| Result: Vector search hits exact HR Handbook Section 4.2 with score 0.88!       |
+---------------------------------------------------------------------------------+
```

#### 3. Step-by-Step Code Changes
1. **Modify `app/use_cases/chat/query_normalizer.py`**:
   - Expand `DOMAIN_VOCABULARY` with enterprise acronyms:
     ```python
     CORPORATE_ACRONYMS = {
         "comp-off": "compensatory off",
         "compoff": "compensatory off",
         "p-leave": "privilege leave",
         "pl": "privilege leave",
         "cl": "casual leave",
         "sl": "sick leave",
         "wfh": "work from home remote",
         "pip": "performance improvement plan",
         "lop": "loss of pay unpaid leave",
         "chutti": "leave vacation",
     }
     ```
   - Implement `expand_acronyms(text: str) -> str` before semantic search encoding.

#### 4. Edge Cases Handled
- **Over-Expansion:** Word boundary matching `\bpl\b` ensures words like `"plan"` or `"apply"` are not mangled.

#### 5. Verification & Test Strategy
- **New Test File:** `tests/unit/test_query_acronym_expansion.py`
  - `test_acronym_expansion_transforms_compoff_and_pleave()`: Validate query strings expand correctly and improve vector distance.

---

### Roadblock 9: RB16 - Primary-to-Fallback Cascade Thrashing on Semi-Degraded HTTP 504 / 429

- **Roadblock ID:** `RB16`
- **Severity / Blast Radius:** `CRITICAL` | 35-second user latency spikes; exhaustion of secondary fallback rate limits under cascading failures.
- **Team Ownership:** **`AB`** (Abhinav Bargi) | **Peer Review:** **`AK`** (Akaash Samson - Core Orchestration)
- **Task Codes:** `[AB-1.1]`, `[AB-1.2]`, `[AK-4]`
- **Subsystem Focus:** `[LLM, FailoverCircuit]` - Circuit Breaker & Failover Cascade

#### 1. Current Vulnerability in Code
In [app/infrastructure/llm/fallback_llm_provider.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/llm/fallback_llm_provider.py#L49-L65):
```python
# CURRENT FLAW: Waits full 15s timeout on every request even after 10 consecutive failures!
try:
    response = self.primary.generate(messages)
except LLMProviderError:
    response = self.fallback.generate(messages)
```
When OpenRouter is semi-down, every incoming query waits 15 seconds on primary before falling back to Groq, cascading latency to 30+ seconds and exhausting Groq's burst limits.

#### 2. Architectural Solution Dataflow
```text
+---------------------------------------------------------------------------------+
| RB16 ARCHITECTURE: Three-State Circuit Breaker with Half-Open Probing           |
+---------------------------------------------------------------------------------+
|                                                                                 |
|    +-------------------+   >= 3 Consecutive Failures   +-------------------+    |
|    |      CLOSED       | ----------------------------> |       OPEN        |    |
|    | (Primary Active)  | <---------------------------  | (Fast Failover)   |    |
|    +-------------------+      Success on Probe         +-------------------+    |
|              ^                                                   |              |
|              |                                                   | Cooldown Exp |
|              |             +-------------------+                 | (30 seconds) |
|              +------------ |     HALF-OPEN     | <---------------+              |
|                            | (Probe 1 Request) |                                |
|                            +-------------------+                                |
|                                                                                 |
| Behavior when OPEN:                                                             |
|   Skip Primary completely (0ms wait) -> Route immediately to Fallback Provider! |
|   User latency drops from 32,000ms -> 1,200ms.                                 |
+---------------------------------------------------------------------------------+
```

#### 3. Step-by-Step Code Changes
1. **Modify `app/infrastructure/llm/provider_health.py`**:
   - Ensure `ProviderHealthMonitor` implements `is_circuit_open(provider_name)` with state enum: `CLOSED`, `OPEN`, `HALF_OPEN`.
   - Cooldown period configurable via `CIRCUIT_BREAKER_COOLDOWN_SEC = 30`.
2. **Modify `app/infrastructure/llm/fallback_llm_provider.py`**:
   - Check `self.health_monitor.is_circuit_open("primary")` BEFORE calling `self.primary.generate()`.
   - If circuit is open, immediately invoke `self.fallback.generate()` and log `circuit_breaker_active fast_failover=true`.

#### 4. Edge Cases Handled
- **Intermittent Spikes:** Requires 3 consecutive 5xx/429 errors within 60s window before opening circuit (prevents flapping on single transient drop).

#### 5. Verification & Test Strategy
- **New Test File:** `tests/unit/test_circuit_breaker_fast_failover.py`
  - `test_circuit_opens_after_three_failures_and_skips_primary()`: Mock 3 failures on primary; verify 4th call executes fallback without calling primary.

---

### Roadblock 10: RB17 - Output Schema Deviation and Hallucinated JSON in Structured Citations

- **Roadblock ID:** `RB17`
- **Severity / Blast Radius:** `HIGH` | Chat UI crashes with JSON parse error; citations render as raw syntax or disappear.
- **Team Ownership:** **`AB`** (Abhinav Bargi) | **Peer Review:** **`AK`** (Akaash Samson - Core Orchestration)
- **Task Codes:** `[AB-2]`, `[AK-5.2]`, `[NE-3.1]`
- **Subsystem Focus:** `[LLM, SchemaContracts]` - Standard LLM Contracts & Citations

#### 1. Current Vulnerability in Code
When fallback models (e.g. Groq Llama 3 8B) generate structured citations, they frequently output markdown fences (` ```json `), unescaped double quotes in text, or trailing commentary. Calling `json.loads(response)` fails with `JSONDecodeError`, crashing citation rendering.

#### 2. Architectural Solution Dataflow
```text
+---------------------------------------------------------------------------------+
| RB17 ARCHITECTURE: Robust Multi-Stage JSON Repair & Sanitizer Pipeline          |
+---------------------------------------------------------------------------------+
| Raw Fallback Output:                                                            |
|   "Here is the citations JSON:\n```json\n{\"citations\": [{\"id\": 1, ...}]}\n```" |
|                                                                                 |
|                        +----------------------------+                           |
|                        | JSON Repair & Extraction   |                           |
|                        +----------------------------+                           |
|                        | 1. Strip Markdown Fences   |                           |
|                        | 2. Regex Scan {...} Block  |                           |
|                        | 3. Fix unescaped newlines  |                           |
|                        | 4. json.loads() attempt    |                           |
|                        | 5. Fallback: ast.literal   |                           |
|                        +----------------------------+                           |
|                                       |                                         |
|                                       v                                         |
| Validated Python Dictionary: {"citations": [{"id": 1, ...}]}                    |
| UI renders citations flawlessly without throwing 500 error!                     |
+---------------------------------------------------------------------------------+
```

#### 3. Step-by-Step Code Changes
1. **Create `app/infrastructure/utils/json_repair.py`**:
   - Implement `safe_extract_json(raw_text: str) -> dict`:
     - Strip code fence markers (```` ```json ```` and ````` ``` ````).
     - Extract outermost `{...}` or `[...]` via regex.
     - Normalize smart quotes to ASCII quotes.
     - Handle trailing commas before closing braces (`,\s*}` -> `}`).
2. **Modify citation parser in `app/use_cases/chat/query_orchestrator.py`**:
   - Wrap citation extraction in `safe_extract_json()`.
   - Provide graceful fallback returning empty citation list rather than raising 500.

#### 4. Edge Cases Handled
- **Completely Unparseable Output:** If the model returns pure prose, log warning and return cleanly structured fallback with zero citations.

#### 5. Verification & Test Strategy
- **New Test File:** `tests/unit/test_json_repair_sanitizer.py`
  - `test_safe_extract_json_handles_fences_and_trailing_commas()`: Test various malformed LLM outputs; verify all parse into valid dictionaries.

---

### Roadblock 11: RB20 - API Key Depletion Silent Deadlock in Background Conversation Logging

- **Roadblock ID:** `RB20`
- **Severity / Blast Radius:** `MEDIUM` | Background worker threads block or retry continuously when API credits expire, leaking memory and starving thread pools.
- **Team Ownership:** **`AB`** (Abhinav Bargi) | **Peer Review:** **`NE`** (Neha - Ingestion & Vector)
- **Task Codes:** `[AB-1.1]`, `[NE-1.1]`, `[NE-1.3]`
- **Subsystem Focus:** `[Observability, AsyncLogging]` - Async Logging & Bounded Thread Pools

#### 1. Current Vulnerability in Code
Background title generation and conversation summarization spawn tasks into unbounded thread pools. When API keys run out of quota, calls retry indefinitely or block, holding worker threads hostage.

#### 2. Architectural Solution Dataflow
```text
+---------------------------------------------------------------------------------+
| RB20 ARCHITECTURE: Bounded Worker Pool with Circuit-Aware Fast Discard          |
+---------------------------------------------------------------------------------+
| Background Task: Summarize conversation title                                   |
|                                                                                 |
| 1. Check Circuit Breaker: Is LLM reporting 401/429 Quota Depleted?              |
|    -> If YES: Discard task immediately; assign heuristic title: "Chat - 25 Sep"|
|                                                                                 |
| 2. Submit to Bounded Queue (max_size=100, workers=2):                          |
|    -> If Queue is Full: Drop task gracefully with warning                       |
|    -> Worker executes with 5-second strict timeout                              |
+---------------------------------------------------------------------------------+
```

#### 3. Step-by-Step Code Changes
1. **Modify `app/infrastructure/logging/` and background tasks**:
   - Replace unbounded `ThreadPoolExecutor()` with bounded `ThreadPoolExecutor(max_workers=2, thread_name_prefix="bg_logger")`.
   - In background summarizer, enforce `timeout=5.0` seconds on LLM calls.
   - Catch `AuthenticationError` and `RateLimitError` as permanent non-retryable errors.

#### 4. Edge Cases Handled
- **System Shutdown:** Worker pool uses daemon threads with `shutdown(wait=False)` to prevent blocking server exit.

#### 5. Verification & Test Strategy
- **New Test File:** `tests/unit/test_background_logger_resilience.py`
  - `test_background_logger_does_not_hang_on_auth_failure()`: Mock 401 Unauthorized; verify background executor finishes within 100ms.

---

### Roadblock 12: RB23 - Unbounded Memory Leak in In-Memory LRU Cache and Session Memory Service

- **Roadblock ID:** `RB23`
- **Severity / Blast Radius:** `HIGH` | Process memory balloons to 4GB+ over days of continuous operation until Linux OOM killer terminates Python backend.
- **Team Ownership:** **`AB`** (Abhinav Bargi) | **Peer Review:** **`AK`** (Akaash Samson - Core Orchestration)
- **Task Codes:** `[AB-4]`, `[AK-1.1]`, `[NE-2.1]`
- **Subsystem Focus:** `[Infrastructure, MemoryLeaks]` - Memory-Bounded Caches & Session TTL

#### 1. Current Vulnerability in Code
In [app/use_cases/chat/query_orchestrator.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/query_orchestrator.py):
```python
# CURRENT FLAW: Standard dictionaries grow indefinitely!
self._last_interaction = {}
self._pending_citations = {}
self._alternative_answer_given = {}
```
Over thousands of queries, `_last_interaction` stores full context chunks, retrieved document texts, and chat histories without any size cap or eviction policy.

#### 2. Architectural Solution Dataflow
```text
+---------------------------------------------------------------------------------+
| RB23 ARCHITECTURE: Bounded LRU Cache with TTL Eviction for Orchestrator State   |
+---------------------------------------------------------------------------------+
| Global Orchestrator State:                                                      |
|                                                                                 |
| Instead of dict(), use BoundedTTLCache(maxsize=1000, ttl_seconds=3600):         |
|   - Keeps at most 1,000 active sessions in RAM                                 |
|   - Evicts Least-Recently-Used (LRU) sessions when limit is reached            |
|   - Purges stale sessions idle for > 1 hour                                     |
|   - Process memory capped strictly at < 350MB under 100,000 requests           |
+---------------------------------------------------------------------------------+
```

#### 3. Step-by-Step Code Changes
1. **Modify `app/use_cases/chat/query_orchestrator.py`**:
   - Replace raw dictionaries with `collections.OrderedDict` or `PromptLRUCache` instances capped at `maxsize=1000`:
     ```python
     from app.infrastructure.cache.quality_aware_cache import InMemoryQualityAwareCache
     self._last_interaction = InMemoryQualityAwareCache(max_size=1000, default_ttl=3600)
     self._pending_citations = InMemoryQualityAwareCache(max_size=1000, default_ttl=1800)
     ```
   - Add periodic eviction trigger during `answer()` calls.

#### 4. Edge Cases Handled
- **Active Session Eviction:** If a session is evicted due to LRU pressure, user asking follow-up receives graceful restart message instead of `KeyError`.

#### 5. Verification & Test Strategy
- **New Test File:** `tests/unit/test_orchestrator_memory_bounds.py`
  - `test_orchestrator_state_never_exceeds_maxsize()`: Insert 2,000 unique session IDs; assert dictionary length never exceeds 1,000.

---

### Roadblock 13: RB25 - Connection Pool Exhaustion on Background Pipeline Tracer Telemetry Export

- **Roadblock ID:** `RB25`
- **Severity / Blast Radius:** `MEDIUM` | File descriptor / socket leaks; backend stops accepting HTTP connections (`errno 24: Too many open files`).
- **Team Ownership:** **`AB`** (Abhinav Bargi) | **Peer Review:** **`AK`** (Akaash Samson - Core Orchestration)
- **Task Codes:** `[AB-6.1]`, `[AB-6.3]`, `[AK-3.2]`
- **Subsystem Focus:** `[Observability, SocketPools]` - Pipeline Tracer & HTTP Connection Pools

#### 1. Current Vulnerability in Code
In [app/infrastructure/observability/pipeline_tracer.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/observability/pipeline_tracer.py), HTTP telemetry export creates ad-hoc HTTP client sessions per trace batch without persistent connection pooling. In high-traffic scenarios, sockets remain in `TIME_WAIT`, exhausting open file descriptors.

#### 2. Architectural Solution Dataflow
```text
+---------------------------------------------------------------------------------+
| RB25 ARCHITECTURE: Singleton Pooled HTTP Transport with Keep-Alive             |
+---------------------------------------------------------------------------------+
| PipelineTracer Export Worker:                                                   |
|                                                                                 |
|                        +----------------------------+                           |
|                        | Shared httpx.Client Pool   |                           |
|                        +----------------------------+                           |
|                        | max_connections: 20        |                           |
|                        | max_keepalive_connections:5|                           |
|                        | keepalive_expiry: 30s       |                           |
|                        +----------------------------+                           |
|                                       |                                         |
|                                       v                                         |
| Reuses existing TCP connection for all LangFuse/LangSmith exports               |
| Zero socket leaks; open file descriptors remain constant at < 50!               |
+---------------------------------------------------------------------------------+
```

#### 3. Step-by-Step Code Changes
1. **Modify `app/infrastructure/observability/pipeline_tracer.py`**:
   - Introduce a thread-safe singleton HTTP client session with connection limits:
     ```python
     import httpx
     _SHARED_HTTP_CLIENT = httpx.Client(
         limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
         timeout=httpx.Timeout(5.0)
     )
     ```
   - Ensure all telemetry exporters reuse `_SHARED_HTTP_CLIENT` instead of instantiating new sessions.

#### 4. Edge Cases Handled
- **Remote Host Reset:** Auto-reconnect on connection reset or remote close without crashing worker.

#### 5. Verification & Test Strategy
- **New Test File:** `tests/unit/test_telemetry_socket_pooling.py`
  - `test_pipeline_tracer_reuses_http_socket_pool()`: Export 100 trace spans; verify single HTTP client session is utilized.

---

### Roadblock 14: RB26 - LangSmith Trace Queue Buffer Bloat Leading to Event Loop Lag and Worker Death

- **Roadblock ID:** `RB26`
- **Severity / Blast Radius:** `HIGH` | Main asyncio event loop lag > 200ms; FastAPI `/health` endpoint times out causing Docker/Kubernetes container restarts.
- **Team Ownership:** **`AB`** (Abhinav Bargi) | **Peer Review:** **`AK`** (Akaash Samson - Core Orchestration)
- **Task Codes:** `[AB-6.1]`, `[AB-6.2]`, `[AK-3.4]`
- **Subsystem Focus:** `[Observability, EventLoopLag]` - LangSmith Serialization & Event Loop Lag

#### 1. Current Vulnerability in Code
In [app/infrastructure/observability/pipeline_tracer.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/observability/pipeline_tracer.py), serializing large trace structures (containing 12,000-character context chunks) executes synchronously on the calling thread/event loop during request completion.

#### 2. Architectural Solution Dataflow
```text
+---------------------------------------------------------------------------------+
| RB26 ARCHITECTURE: Non-Blocking Trace Offloading via Dedicated Background Queue |
+---------------------------------------------------------------------------------+
| Request Completes -> PipelineTracer.end_trace(trace_id)                          |
|                                                                                 |
| 1. Do NOT serialize trace on main thread!                                       |
| 2. Push raw trace object into thread-safe queue: trace_queue.put_nowait(trace)   |
| 3. Main asyncio event loop returns HTTP response to user immediately (0ms lag)   |
|                                                                                 |
| Dedicated Background Daemon Thread:                                             |
|   While True:                                                                   |
|     trace = trace_queue.get()                                                   |
|     Serialize JSON & export to LangFuse/LangSmith in background                 |
|     Health check (/health) responds in 2ms consistently!                        |
+---------------------------------------------------------------------------------+
```

#### 3. Step-by-Step Code Changes
1. **Modify `app/infrastructure/observability/pipeline_tracer.py`**:
   - Implement `queue.Queue(maxsize=1000)` for background serialization.
   - Start dedicated background worker daemon: `threading.Thread(target=_worker_loop, daemon=True)`.
   - In `record_trace()`, execute non-blocking `queue.put_nowait(trace_data)`. If queue is full, drop trace and increment `dropped_traces` counter to preserve core bot performance.

#### 4. Edge Cases Handled
- **Queue Overflow:** If network drops for 10 minutes, queue caps at 1000 items and drops older spans rather than exhausting RAM.

#### 5. Verification & Test Strategy
- **New Test File:** `tests/unit/test_trace_queue_non_blocking.py`
  - `test_trace_recording_does_not_block_caller()`: Measure execution time of `record_trace()` with 100,000-character payload; assert execution completes in < 1ms.

---

## Master Implementation Schedule & Execution Roadmap

| Sequence | Roadblock ID | Title | Target File(s) | Reviewer | Estimated Effort |
|:---:|:---:|:---|:---|:---:|:---:|
| **Step 1** | `RB12` | Role-Scoped Cache Key Isolation | `quality_aware_cache.py`, `query_orchestrator.py` | **`RO`** | 0.5 Day |
| **Step 2** | `RB28` | Telemetry PII Regex Scrubbing | `pipeline_tracer.py`, `pii_scrubber.py` | **`RO`** | 0.5 Day |
| **Step 3** | `RB01` | Embedding Dimension Mismatch Guard | `chroma_client.py`, `faq_similarity_cache.py` | **`NE`** | 0.5 Day |
| **Step 4** | `RB05` | Unicode NFKC Cache Deletion | `query_normalizer.py`, `faq_similarity_cache.py` | **`NE`** | 0.5 Day |
| **Step 5** | `RB02` | Negation & Polarity Semantic Layer | `query_normalizer.py`, `quality_aware_cache.py` | **`AK`** | 0.5 Day |
| **Step 6** | `RB29` | Adaptive Thresholds & Jargon Gating | `quality_aware_cache.py`, `faq_similarity_cache.py`| **`AK`** | 0.5 Day |
| **Step 7** | `RB04` | Cold-Start Double-Checked Locking | `faq_similarity_cache.py`, `dependencies.py` | **`AK`** | 0.5 Day |
| **Step 8** | `RB10` | Corporate Acronyms & Dialect Dict | `query_normalizer.py` | **`NE`** | 0.5 Day |
| **Step 9** | `RB16` | Circuit Breaker & Adaptive Failover | `fallback_llm_provider.py`, `provider_health.py` | **`AK`** | 0.5 Day |
| **Step 10** | `RB17` | Standard JSON Schema & Repair Layer | `json_repair.py`, `query_orchestrator.py` | **`AK`** | 0.5 Day |
| **Step 11** | `RB20` | Bounded Thread Pool for Background Tasks | `pipeline_tracer.py`, background workers | **`NE`** | 0.5 Day |
| **Step 12** | `RB23` | Bounded LRU Cache & State TTL | `query_orchestrator.py` | **`AK`** | 0.5 Day |
| **Step 13** | `RB25` | Telemetry HTTP Connection Pooling | `pipeline_tracer.py` | **`AK`** | 0.5 Day |
| **Step 14** | `RB26` | Non-Blocking Trace Queue Offloading | `pipeline_tracer.py` | **`AK`** | 0.5 Day |

---

## Definition of Done (DoD) for AB Roadblocks Completion

1. **All 14 Individual Roadblock Unit Test Suites Pass:** 14 new/enhanced unit test suites in `tests/unit/test_*.py` execute with 100% green status.
2. **Zero Regressions on Contract Suite:** `tests/contract/test_chat_api_contract.py` executes all 9 API contract assertions successfully.
3. **No Mermaid Diagrams:** All architectural flows represented via verified, clean ASCII art.
4. **Peer Review Alignment:** Changes approved by respective designated reviewers (**`AK`**, **`NE`**, **`RO`**).
5. **No Memory Leaks / Thread Locks:** 10,000-request soak test maintains stable memory under 350MB and zero uncollected zombie threads.
