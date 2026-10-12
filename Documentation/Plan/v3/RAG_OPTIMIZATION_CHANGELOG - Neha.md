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
