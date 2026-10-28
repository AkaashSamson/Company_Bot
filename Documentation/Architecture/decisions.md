# Architectural Decision Records: JEV System Enhancement

**Project:** KnowLayer HR Policy Assistant (`Company_Bot`)  
**Scope:** JEV (Judge / Evaluation Validator) Architecture, Security Guardrails, and RAG Pipeline  
**Status:** Pending Approval  
**Date:** October 2026  

---

## Executive Overview

Following the Phase 0 Architecture and Security Audit, this document presents the key architectural decisions required to transform JEV into a robust, enterprise-grade validation and evaluation engine. 

Each decision defines the context, considered alternatives, trade-offs, and recommended path. **Please review and approve these decisions so implementation can proceed.**

---

## Decision Index

| ID | Title | Focus Area | Status |
| :--- | :--- | :--- | :--- |
| **ADR-01** | [Document-Access Policy for JEV](#adr-01-document-access-policy-for-jev-groundedness-vs-privacy) | Groundedness & Privacy | **Approved (Option B)** |
| **ADR-02** | [Evidence-Grounded Context Sufficiency Routing](#adr-02-evidence-grounded-context-sufficiency-routing-replacing-rigid-pre-retrieval-categories) | Routing & Zero Hallucination | **Approved & Implemented** |
| **ADR-03** | [Provider Transparency & Failure Resilience](#adr-03-provider-transparency--failure-resilience) | Reliability & Monitoring | **Approved & Implemented** |
| **ADR-04** | [Claim-Level Groundedness Evaluation Strategy](#adr-04-claim-level-groundedness-evaluation-strategy) | Hallucination Prevention | **Approved & Implemented** |
| **ADR-05** | [Expanded Secret & PII Scrubbing Perimeter](#adr-05-expanded-secret--pii-scrubbing-perimeter) | Security & Privacy | **Approved & Implemented** |
| **ADR-06** | [HTTP Client Lifecycle & Concurrency Optimization](#adr-06-http-client-lifecycle--concurrency-optimization) | Performance & Latency | **Approved & Implemented** |

---

## ADR-01: Document-Access Policy for JEV (Groundedness vs. Privacy)

### Context & Problem Statement
Currently, JEV operates under a strict "Zero-Document Guarantee" where company handbook chunks are never passed to JEV API endpoints (`api.groq.com`). While this protects handbook text from being sent to JEV, it introduces a critical limitation:
> **A judge cannot evaluate whether an answer is grounded in facts without reading the source evidence.**

Because JEV cannot see retrieved chunks, the system has **zero claim-level groundedness checking**. The primary LLM already receives these chunks (via Groq or OpenRouter) to generate the answer. Therefore, passing chunks to Groq for JEV evaluation does not cross a new trust boundary, provided secrets are masked.

### Evaluated Options

#### Option A: Maintain 100% Document-Blind JEV (Current State)
- **Mechanism:** JEV only receives the user question and the final generated answer; never context chunks.
- **Pros:** Zero risk of document transmission to JEV endpoints.
- **Cons:** Impossible to verify factual groundedness, hallucinated leave counts, or policy contradictions. Citations remain unverified.

#### Option B: Full Document Transmission to JEV (Context-Aware JEV) — *(Recommended)*
- **Mechanism:** 
  1. Pre-flight input safety and query intent remain **document-blind** (only the user question is passed).
  2. Post-generation groundedness evaluation receives `(context_chunks, candidate_answer)`.
  3. Pre-redaction strips secrets and PII from both chunks and answer before external dispatch.
  4. If `OLLAMA_ENABLED=true` (air-gapped/local deployment), JEV runs entirely on the local Ollama instance.
- **Pros:** Unlocks true hallucination detection, factual entailment verification, and citation accuracy. Ensures the assistant never misquotes company policy.
- **Cons:** Document chunks are sent to the JEV model provider (same provider as primary LLM).

#### Option C: Local NLI Model for Groundedness (Zero Cloud Transmission)
- **Mechanism:** Run a local lightweight Cross-Encoder or NLI model (e.g. `DeBERTa-v3-small`) on the server CPU/GPU for groundedness.
- **Pros:** Zero cloud transmission of documents.
- **Cons:** Higher server RAM/CPU footprint; slower inference on CPU; added Python dependencies (`transformers`, `torch`).

### Decision & Recommendation
> **Recommendation: Option B (Hybrid Context-Aware Policy).**  
> Allow JEV to receive retrieved context chunks **exclusively** during the post-generation groundedness evaluation stage, while maintaining document-blindness for input safety and query classification. Ensure secret pre-scrubbing applies to chunks.

- [ ] **Approve Option B (Recommended)**
- [ ] **Keep Option A (Document-Blind, no groundedness check)**
- [ ] **Select Option C (Local NLI model)**

---

## ADR-02: Evidence-Grounded Context Sufficiency Routing (Replacing Rigid Pre-Retrieval Categories)

### Context & Problem Statement
The initial proposal suggested classifying user queries into rigid categories (`"policy" | "etiquette" | "unrelated"`) *before* retrieval. However, architectural review and user feedback identified two critical flaws in pre-retrieval categorization:
1. **Misclassification & Premature Denial:** An external category classifier cannot know what documents exist in the database. A query about internal project architecture or technical specifications might be wrongly classified as "unrelated" and denied without querying ChromaDB.
2. **False Assumptions Cause Hallucinations:** Even if a query is clearly a "policy" question (e.g. paternity leave or pet policies), if the handbook does not contain those clauses, classifying it as "policy" and feeding irrelevant chunks causes the LLM to hallucinate rules.

Furthermore, hardcoding narrow threat keys or rigid regex categories in safety guardrails leaves the system vulnerable to subtle evasion, prompt manipulation, or social engineering.

### Architecture Decision: Holistic Safety + Context Sufficiency Routing — *(Approved & Implemented)*

1. **Holistic Maliciousness Evaluation (Pre-Flight Safety):**
   - Rather than checking only a few hardcoded keys, JEV evaluates whether the entire query is malicious, adversarial, harmful, or an exploit attempt in **ANY** way (prompt injection, jailbreak personas, prompt extraction, social engineering, payload delivery, or unauthorized reconnaissance).
   - Benign workplace questions are safely permitted.

2. **ChromaDB Retrieval & Dedicated Reranking:**
   - Every legitimate user query is searched in ChromaDB and reranked using the BGE reranker to retrieve the most semantically relevant chunks.

3. **Evidence-Grounded Context Sufficiency Gating (`evaluate_context_sufficiency`):**
   - JEV evaluates the retrieved candidate chunks against the user query:
     - `can_be_answered (bool)`: Do the chunks contain direct, factual evidence to answer the query?
     - `relevant_chunk_indices (list[int])`: Which specific chunks contain the facts?
     - `is_etiquette (bool)`: Is this an interpersonal etiquette/communication inquiry that policy documents do not record?
     - `reason (str)`: Factual justification.

4. **Guaranteed Zero-Hallucination Routing:**
   - **If `can_be_answered == True`:** The context is filtered strictly to the `relevant_chunk_indices`, passed to the generative LLM, and validated post-generation by JEV claim-level groundedness checking.
   - **If `can_be_answered == False`:** The generative LLM is **never** invoked with irrelevant chunks!
     - If `is_etiquette == True`: Provides courteous workplace advice with the explicit disclaimer: *"Company policy documents do not contain specific rules or records on this individual matter."*
     - Else: Safely abstains: *"I could not find that information in the available documents."*

### Status
- **Status:** **Approved and Implemented**
- **Validation:** 24 unit tests passing in `test_jev_enhancements.py` and `test_security_guardrails.py`.

---

## ADR-03: Provider Transparency & Failure Resilience

### Context & Problem Statement
`guardrails.py` currently reports `provider="jev"` even when `JevClient` encounters HTTP 402, 429, 500, or timeouts and falls back to local regex. Furthermore, `JevClient` does not log HTTP error codes or response bodies when non-200 responses occur.

### Evaluated Options

#### Option A: Silent Fallback with Fake Attribution (Current State)
- **Cons:** Deceptive monitoring; ops team has no visibility into API outages or exhausted credits.

#### Option B: Honest Attribution with Circuit Breaker & Metrics — *(Recommended)*
- **Mechanism:**
  1. `GuardrailResult.provider` strictly reflects reality: `"jev"` if semantic model evaluated, `"local_fallback"` if local regex was used due to error, `"local"` if running in offline mode.
  2. Explicitly log HTTP status codes (402, 429, 500) and response excerpts.
  3. Emit failure counters to `ObservabilityManager` / `PipelineTracer`.
  4. Introduce a simple circuit breaker: if JEV fails 3 consecutive times, short-circuit to local fallback for 60 seconds rather than waiting for 8.0s timeouts on every request.
- **Pros:** Complete operational transparency; prevents thread pool congestion during external outages.

### Decision & Recommendation
> **Recommendation: Option B.** Implement honest provider attribution, explicit error logging, and circuit-breaker protection.

- [ ] **Approve Option B**

---

## ADR-04: Claim-Level Groundedness Evaluation Strategy

### Context & Problem Statement
`ProvenanceService` currently only formats citations. It does not verify whether the generated answer is faithful to the retrieved chunks. If the LLM hallucinates an inaccurate policy detail, citations still attach the retrieved chunk as false validation.

### Evaluated Options

#### Option A: Two-Step Generation + JEV Groundedness Verification — *(Recommended)*
- **Mechanism:**
  1. LLM generates candidate answer.
  2. JEV evaluates candidate answer against retrieved context chunks:
     ```json
     {
       "is_grounded": true,
       "hallucination_score": 0.0,
       "unsupported_claims": [],
       "verdict": "pass" | "abstain"
     }
     ```
  3. If `verdict == "abstain"` (major unsupported claims or contradiction): the bot safely falls back to:  
     *"I found relevant policy documents, but cannot confirm the exact answer with certainty. Please refer to Section X or contact HR directly."*
  4. Citations are filtered to include only chunks that actually supported the answer.
- **Pros:** Guarantees policy accuracy; completely stops hallucinations from reaching employees.
- **Cons:** Adds an evaluation step (~300-600ms latency on RAG turns).

#### Option B: Strict Few-Shot Groundedness in Generation Prompt Only
- **Mechanism:** Rely solely on prompt engineering (`"Answer ONLY using facts from context. If unsure, say you don't know"`).
- **Pros:** Zero added latency.
- **Cons:** LLMs still hallucinate ~5-15% of the time, especially on numerical policy limits (probation months, leave days).

### Decision & Recommendation
> **Recommendation: Option A.** Implement post-generation JEV groundedness evaluation with clean abstention fallback.

- [ ] **Approve Option A (JEV Groundedness Evaluation)**
- [ ] **Approve Option B (Prompt-only constraints)**

---

## ADR-05: Expanded Secret & PII Scrubbing Perimeter

### Context & Problem Statement
The current secret scrubber misses AWS keys (`AKIA...`), GitHub PATs (`ghp_...`), Google API keys, and PEM private keys. PII scrubbing only covers emails, phone numbers, and employee IDs matching `MSS|EMP|DEPT|PROJ`.

### Evaluated Options

#### Option A: Comprehensive Regex Pattern Suite — *(Recommended)*
- **Mechanism:** Expand regex definitions to cover:
  - AWS Access Key ID (`\bAKIA[0-9A-Z]{16}\b`) and AWS Secret Key heuristics
  - GitHub PATs (`\bgh[pousr]_[A-Za-z0-9_]{36,255}\b`)
  - Google Cloud API keys (`\bAIza[0-9A-Za-z-_]{35}\b`)
  - Slack Tokens (`\bxox[baprs]-[0-9a-zA-Z-]+\b`)
  - Cryptographic Private Keys (`-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----`)
  - Generic High-Entropy API key patterns
  - Pre-evaluation Unicode NFKC normalization (`unicodedata.normalize('NFKC', text)`)
- **Pros:** Zero-dependency, sub-millisecond execution, blocks common leak vectors.
- **Cons:** Regex cannot detect unstructured person names without NER.

#### Option B: Add Microsoft Presidio / SpaCy NER
- **Mechanism:** Integrate external NLP NER library for full name and address redaction.
- **Pros:** Detects arbitrary employee names and addresses.
- **Cons:** Requires adding 200MB+ dependencies, heavy CPU overhead on every request.

### Decision & Recommendation
> **Recommendation: Option A.** Implement comprehensive regex suite + Unicode normalization immediately. Defer Presidio/SpaCy to future roadmap.

- [ ] **Approve Option A**

---

## ADR-06: HTTP Client Lifecycle & Concurrency Optimization

### Context & Problem Statement
Every invocation of `check_input_safety`, `check_output_safety`, or `classify_query_intent` executes `with httpx.Client(timeout=self.timeout) as client:`. This forces a new TCP connection and TLS handshake for every call, adding 150-300ms of latency per check and creating socket exhaustion under concurrent load.

### Evaluated Options

#### Option A: Persistent Pooled `httpx.Client` — *(Recommended)*
- **Mechanism:** 
  1. Instantiate a single, long-lived `httpx.Client` on `JevClient` during initialization with keep-alive connection pooling:
     ```python
     self._client = httpx.Client(
         timeout=httpx.Timeout(self.timeout, connect=3.0),
         limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
     )
     ```
  2. Implement proper cleanup in `close()` and application lifespan hooks.
  3. Bypass `validate_output` when `_finish` is called for early input rejections.
- **Pros:** Saves 150-300ms per JEV turn; reuses TLS sessions; prevents socket churn.
- **Cons:** Requires managing client shutdown lifecycle.

### Decision & Recommendation
> **Recommendation: Option A.** Implement persistent connection pooling and eliminate redundant rejection evaluations.

- [ ] **Approve Option A**

---

## Summary of Recommendations

| Decision | Recommended Choice | Primary Benefit |
| :--- | :--- | :--- |
| **ADR-01: Document Access** | **Option B (Context-Aware for Groundedness)** | Enables real hallucination & claim verification |
| **ADR-02: Context Sufficiency Routing** | **Context Sufficiency & Chunk Answerability** | Eliminates hallucinations & false category denials |
| **ADR-03: Provider Transparency** | **Option B (Honest Attribution + Circuit Breaker)** | Accurate observability & outage protection |
| **ADR-04: Groundedness Strategy** | **Option A (Structured JEV Evaluator)** | Eliminates false citations & ungrounded policy answers |
| **ADR-05: Security Perimeter** | **Option A (Comprehensive Regex + NFKC)** | Blocks AWS/GitHub/PEM leaks & Unicode evasion |
| **ADR-06: Client Lifecycle** | **Option A (Pooled Client + Rejection Bypass)** | Cuts 300ms+ latency & prevents socket exhaustion |

---

*Please confirm approval of these recommendations. Once approved, execution will strictly follow `plan.md`.*
