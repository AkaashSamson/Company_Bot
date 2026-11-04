# Observability & Pipeline Tracing Telemetry Specification

- **Module:** `app.infrastructure.observability` & `app.domain.ports.observability`
- **Associated Tasks:** Task AK-3.3 (Groq Token Standardization), Task AB-6.3 (Pipeline Tracer Dispatch Hook)
- **Status:** Approved Specification (Post-Brainstorming)
- **Author:** Akaash Samson

---

## 1. Executive Summary & Intent

This specification defines the production-grade telemetry and observability contract for Company_Bot's RAG pipeline. It bridges internal in-memory execution profiling (`PipelineTracer`) with external enterprise observability providers (`ObservabilityManager` -> Langfuse / Arize Phoenix / NullProvider).

### Primary Objectives:
1. **Root-to-Leaf Trace Hierarchy:** Capture each user request as one root trace containing 8 nested stage spans in Langfuse, avoiding disconnected orphan spans.
2. **Accurate Timestamp Preservation:** Maintain real execution durations per stage by forwarding recorded microsecond start/end timestamps from in-memory spans to the provider, eliminating 0ms post-hoc distortion.
3. **High-Diagnostic Value Payloads:** Transition from vanity metrics (bare timing numbers) to actionable debugging telemetry (query transformations, document chunk snippets with similarity scores, quality gate scores, full prompts, and token counts).
4. **Zero Vendor Coupling in Application Logic:** `QueryOrchestrator` interacts strictly with `PipelineTracer`. External telemetry logic (Langfuse/Phoenix) is isolated within `ObservabilityManager`.

---

## 2. Architecture & Data Flow

```
┌────────────────────────────────────────────────────────────────────────┐
│                        QueryOrchestrator.answer()                      │
│                                                                        │
│   tracer = get_pipeline_tracer()                                       │
│   trace = tracer.start_trace(query=question, session_id=session_id)    │
│                                                                        │
│   with tracer.trace_stage(PipelineStage.NORMALIZATION) as s:           │
│       ... s.set_output(normalized_query=..., cache_key=...)            │
│   with tracer.trace_stage(PipelineStage.VECTOR_RETRIEVAL) as s:        │
│       ... s.set_output(chunks=evidence_summaries)                      │
│   with tracer.trace_stage(PipelineStage.LLM_GENERATION) as s:          │
│       ... s.record_tokens(usage.prompt_tokens, usage.completion_tokens)│
│                                                                        │
│   tracer.end_trace(trace_id=trace.trace_id, final_response=answer)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼ triggers on trace finish
┌────────────────────────────────────────────────────────────────────────┐
│                   PipelineTracer (In-Memory Facade)                    │
│   - Stores in-memory trace for local health stats & unit test checks   │
│   - Dispatches completed PipelineTrace to ObservabilityManager         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ dispatch_trace(trace)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     ObservabilityManager (Router)                      │
│   - Creates Root Trace on active provider (with session_id & user_id)  │
│   - Unpacks StageSpans into typed Observations (span, retriever, gen)  │
│   - Applies original start_time and end_time to preserve duration      │
│   - Flushes event queue                                                │
└───────────────────┬───────────────────────────────┬────────────────────┘
                    ▼                               ▼
       [Langfuse Cloud / Host]            [Arize Phoenix OTLP]
```

---

## 3. Telemetry Schema & Stage Contracts

### 3.1 Root Trace (`QueryOrchestrator.answer`)
- **Observation Type:** Root Trace / Transaction
- **Identity:** `trace_id` (UUID), `session_id` (conversational session grouping), `user_id`
- **Input:** Raw user question
- **Output:** Final assistant answer text
- **Tags:** `["teams", "v3", "rag"]`
- **Metadata:**
  ```python
  {
      "cache_hit": bool,
      "early_exit": bool,
      "exit_stage": str | None,
      "exit_reason": str | None,
      "total_duration_ms": float,
      "total_tokens": int,
  }
  ```

---

### 3.2 Stage 1: Context Rewrite (`CONTEXT_REWRITE`)
- **Observation Type:** `span`
- **Input:** Raw user question
- **Output:** Standalone resolved question
- **Metadata:**
  ```python
  {
      "was_rewritten": bool
  }
  ```
- *Note:* Excludes conversational history counting to eliminate coupling with the in-progress session memory implementation.

---

### 3.3 Stage 2: Normalization (`NORMALIZATION`)
- **Observation Type:** `span`
- **Input:** Raw or rewritten query
- **Output:** Normalized query string
- **Metadata:**
  ```python
  {
      "cache_key": str,
      "corrections_made": list[str],
      "was_modified": bool,
  }
  ```

---

### 3.4 Stage 3: Cache Lookup (`CACHE_LOOKUP`)
- **Observation Type:** `span`
- **Input:** `cache_key`
- **Output:** Cached answer or null
- **Metadata:**
  ```python
  {
      "cache_hit": bool,
      "cache_type": "semantic" | "faq" | "miss",
      "similarity_score": float,
      "matched_question": str | None,
  }
  ```

---

### 3.5 Stage 4: Vector Retrieval (`VECTOR_RETRIEVAL`)
- **Observation Type:** `retriever`
- **Input:** Retrieval search query string
- **Output:** Summary of candidate evidence chunks
- **Metadata:**
  ```python
  {
      "chunks_retrieved_count": int,
      "chunks": [
          {
              "chunk_id": str,
              "source": str,
              "score": float,
              "snippet": str  # First 150 characters of chunk text
          }
      ]
  }
  ```

---

### 3.6 Stage 5: Reranking (`RERANKING`)
- **Observation Type:** `span`
- **Input:** Candidate chunk count
- **Output:** Filtered chunk count
- **Metadata:**
  ```python
  {
      "candidates_in": int,    # e.g., 15
      "candidates_out": int,   # e.g., 4
      "top_scores": list[float]
  }
  ```

---

### 3.7 Stage 6: Quality Gate (`QUALITY_GATE`)
- **Observation Type:** `guardrail`
- **Input:** Reranked evidence count
- **Output:** Assessment verdict
- **Metadata:**
  ```python
  {
      "quality_level": "STRONG" | "BORDERLINE" | "WEAK" | "INVALID",
      "confidence_score": float,
      "grounding_score": float,
      "passed": bool,
  }
  ```

---

### 3.8 Stage 7: LLM Generation (`LLM_GENERATION`)
- **Observation Type:** `generation`
- **Model:** Target LLM model name (e.g., `llama-3.3-70b-versatile`)
- **Input:** Full messages payload (system prompt with injected context + user turn)
- **Output:** Raw LLM response string
- **Token Usage (`TokenUsage`):**
  - `prompt_tokens`: int
  - `completion_tokens`: int
  - `total_tokens`: int
- **Metadata:**
  ```python
  {
      "latency_ms": float,
      "provider": "groq" | "openrouter",
  }
  ```

---

### 3.9 Stage 8: Post Guardrails (`POST_GUARDRAILS`)
- **Observation Type:** `guardrail`
- **Input:** LLM generated text
- **Output:** Final sanitized response
- **Metadata:**
  ```python
  {
      "citations_count": int,
      "negative_response_detected": bool,
      "cache_written": bool,
  }
  ```

---

## 4. Component Scope & Implementation Plan

### 4.1 Task AK-3.3: Groq Token Standardization
- **File:** `app/infrastructure/llm/groq_client.py`
- **Architectural Boundary:** Preserves separation between LLM Infrastructure and Observability Domain. `GroqClient` standardizes on `LLMTokenUsage` from `app.infrastructure.llm.llm_response` (matching `OpenRouterClient`).
- **Changes:**
  1. In `generate()`: parse `usage` dictionary (`prompt_tokens`, `completion_tokens`, `total_tokens`) into `LLMTokenUsage`.
  2. In `generate_with_response()`: continue populating `LLMTokenUsage` on `LLMResponse`.
  3. Store and expose `get_last_token_usage() -> Optional[LLMTokenUsage]`.
  4. Keeps `GroqClient` 100% decoupled from `app.domain.ports.observability`.

### 4.2 Task AB-6.3: Pipeline Tracer Dispatch Hook & Boundary Adapter
- **Files:** `app/infrastructure/observability/manager.py` & `app/infrastructure/observability/pipeline_tracer.py`
- **Architectural Boundary:** `ObservabilityManager` acts as the translator/adapter at the boundary:
  1. In `manager.py`, implement `to_token_usage(usage_input: Any) -> Optional[TokenUsage]`:
     - Safely converts duck-typed `LLMTokenUsage`, dictionaries, or existing `TokenUsage` instances into frozen domain `TokenUsage`.
     - Returns `None` if usage is missing/unavailable (preventing misleading zero-token metrics on failed calls).
  2. In `ObservabilityManager`, add `dispatch_trace(trace: PipelineTrace) -> None`:
     - Creates Root Trace on active provider (`QueryOrchestrator.answer`).
     - Unpacks each `StageSpan` with explicit start and end timestamps.
     - Translates LLM tokens via `to_token_usage()` and records call via `record_llm_call()`.
     - Calls `flush()`.
  3. In `PipelineTracer.end_trace()`, automatically invoke `get_observability_manager().dispatch_trace(trace)` if tracing is enabled.
