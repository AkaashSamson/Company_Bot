# RAG Pipeline Optimization Changelog

A concise summary of architectural and algorithmic improvements implemented across the RAG ingestion, retrieval, context generation, and caching pipeline.

---

## 1. Vector Store & Embeddings (`app/infrastructure/vector/chroma_client.py`)
- **Dynamic Model Loading**: Replaced hardcoded `all-MiniLM-L6-v2` with dynamic loading via `EMBEDDING_MODEL` (`BAAI/bge-small-en-v1.5`).
- **Idempotent Ingestion**: Added `delete_document_chunks(document_id)` to wipe existing chunks before writing new ones, preventing duplicate/zombie chunks.
- **Affected File**: `scripts/ingest_documents.py` (invokes `delete_document_chunks` before indexing).

## 2. Ingestion Contextualization (`app/use_cases/ingestion/document_processing.py`)
- **`_contextualize()` Function**:
  - Validates heading hierarchy (filters false-positive headings > 100 characters).
  - Enforces a 200-character budget for breadcrumbs (`Deepest > Parent > Grandparent`).
  - Prepends clean breadcrumb context (`"Header A > Subheader B\n\n[Text]"`) directly into chunk text for higher retrieval precision.

## 3. Retrieval & Reranker Score Acceptance (`app/use_cases/chat/retrieval_service.py`)
- **Reranker-First Filtering**:
  - Increased candidate retrieval pool from 10 to 25 (`RAG_CANDIDATE_COUNT=25`).
  - Updated candidate acceptance logic: When candidates possess a `_rerank_score` (from `BAAI/bge-reranker-base`), acceptance is driven by `rerank_score > 0.0` rather than raw bi-encoder Euclidean distance thresholds.

## 4. RAG Context & Multi-Turn History (`app/use_cases/chat/rag_context_builder.py`, `query_orchestrator.py`)
- **Context Cleanup**: Removed synthetic `[Section N]` tags that polluted LLM context.
- **Conversation History Window**: Added `conversation_history` support to `build_messages()`, injecting a sliding window of the last 5 turns (`conversation_history[-5:]`) to preserve conversational context without context-window overflow.
- **Prompt Relaxation (`config/prompts.yaml`)**: Replaced strict 2–4 sentence limit with *"Be comprehensive but concise"* to prevent truncated policy explanations.

## 5. Cache Precision & Invalidation (`.env`, `scripts/clear_caches.py`)
- **BGE Embedding Cache Clustered Threshold**:
  - Raised `SEMANTIC_CACHE_SIMILARITY_THRESHOLD`, `LLM_CACHE_SIMILARITY_THRESHOLD`, and `FAQ_SIMILARITY_THRESHOLD` from `0.89` to `0.98`.
  - Fixes false-positive cache collisions where semantically distinct HR queries in the same domain mapped to high cosine similarity (> 0.89).
- **Cache Invalidation Script**: Created `scripts/clear_caches.py` to flush MongoDB FAQ store, Redis semantic cache, and SQLite caches.

## 6. Document Migration & Ingestion
- Cleaned legacy input files and `.chroma` store.
- Successfully indexed `input/NEXORA TECHNOLOGIES PVT.pdf` (291 chunks processed via Docling + RapidOCR).

## 7. Reranking Evaluation & Scalability Strategy
- **Current Corpus Finding**: With a single, curated HR manual (291 chunks), pure vector retrieval (`BAAI/bge-small-en-v1.5`) achieved higher recall (e.g., retrieving break policies at Rank 4) without cross-encoder keyword/entity penalties.
- **Configurable Toggle**: Set `RERANKER_PROVIDER=none` in `.env` (activates `NullReranker`).
- **Future Scale Path**: When the corpus expands to thousands of chunks across multiple departments/projects, reranking can be seamlessly re-enabled at any time simply by setting `RERANKER_PROVIDER=bge` in `.env`.

## 8. Adaptive Prompt & Temperature Calibration
- **Adaptive Length Prompt (`config/prompts.yaml`)**: Dynamically matches response length to query scope (concise for simple lookups, detailed for procedures), avoids conversational filler, and bans oversized markdown headings.
- **Temperature Setting (`app/core/settings.py`, `.env`)**: Configured `LLM_TEMPERATURE=0.2` for natural synthesis while maintaining strict factual grounding.

## 9. Zero-Trust Jev Decision Router & Workplace Etiquette Fallback (`app/infrastructure/llm/jev_client.py`)
- **Zero Document Leakage Guarantee**:
  - ZERO company documents or Chroma chunks are ever transmitted to Jev.
  - Jev acts strictly as a lightweight System-1 decision router that evaluates only the user's sanitized question.
  - Automatic PII scrubbing (Employee IDs, Emails, Phone numbers) before any routing call.
- **Out-of-Document Workplace Etiquette Routing**:
  - Questions like interpersonal etiquette, coworker pronoun preferences, or sensitive communication not documented in formal company policy are routed to a dedicated guidance prompt.
  - The model honestly acknowledges that company documents do not contain rules on the matter, while providing courteous, standard professional guidance without fabricating policy.
- **Follow-up Disambiguation**:
  - Uses Jev System-1 decision model to accurately differentiate between user confirmation feedback ("yes", "helpful", "no") and follow-up inquiries ("Can you explain further?"), preventing conversational deadlock.

## 10. Jev-Powered Dynamic Input & Output Security Guardrails (`app/infrastructure/llm/jev_client.py`, `app/domain/services/guardrails.py`)
- **Dynamic Jev System-1 Guardrails (Non-hardcoded)**:
  - **Dynamic Threat Classification**: Rather than relying purely on static regex matches, queries and answers are evaluated dynamically by `typesafe/jev-router` via OpenRouter.
  - **Input Guardrail (`check_input_safety`)**: Evaluates sanitized user queries for prompt injections, jailbreaks (`DAN`, developer mode), system prompt extraction attempts, and code/SQL injections.
  - **Output Guardrail (`check_output_safety`)**: Inspects generated responses to detect accidental leaks of system instructions, prompt templates, or internal credentials before delivery to the user.
- **Zero-Trust Document Security Guarantees**:
  - **Zero Company Document Transmission**: No Chroma chunks, repository files, or internal documents are EVER sent to Jev.
  - **PII Scrubbing**: User inputs are scrubbed of employee IDs, emails, and phone numbers before safety classification.
  - **Local Secret Redaction**: Secrets (`sk-...`, `gsk_...`, Bearer tokens) are pre-redacted locally before any external transmission.
- **Resilient Defense-in-Depth**:
  - Local regex patterns and a 2,000-character DoS cap serve as instantaneous zero-network fallbacks in case of network timeouts or offline mode.
- **Verification**:
  - 11 unit and integration tests in `tests/unit/test_security_guardrails.py` covering dynamic Jev evaluation, mock isolation, local fallbacks, and zero-document guarantees.
  - End-to-end live testing with `QueryOrchestrator.answer()`.
