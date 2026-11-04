# Restore Telemetry & Chunk Tracing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surgically restore `PipelineTracer` multi-stage instrumentation, reranker injection, and chunk capture in `QueryOrchestrator` that were accidentally stripped in commit `f425802`, while preserving all RBAC document isolation and session auth fixes.

**Architecture:** 
Reinstate the clean 8-stage pipeline tracing (`NORMALIZATION`, `CACHE_LOOKUP`, `VECTOR_RETRIEVAL`, `RERANKING`, `LLM_GENERATION`) via `_stage_ctx()` in `QueryOrchestrator`. Each stage records input/output chunk metadata, which `PipelineTracer` dispatches directly to `ObservabilityManager` -> `LangfuseProvider` (legacy `tracer.py` is bypassed and left untouched).

**Tech Stack:** Python 3.12, Pytest, Langfuse v4 SDK, OpenTelemetry.

**Spec:** PR / Issue requirements for Task AB-6.2 (multi-stage pipeline telemetry) and AK-1.3 (session memory tracing).

## Global Constraints
- Preserve `DocumentProjectMappingService` and RBAC document security in `retrieval_service.py` and `query_orchestrator.py`.
- Preserve `session_auth.py` token verification.
- Preserve the user feedback regex prompt guard in `query_orchestrator.py`.
- Never raise unhandled exceptions from tracing calls (fail-safe).
- Maintain all existing method signatures and backward-compatibility with mocks in tests.

## Review Focus
1. `QueryOrchestrator(reranker=...)`: Must accept optional `reranker` argument without `TypeError`.
2. Negative fast-paths (e.g. "no thanks"): Must still call `start_trace()` and `end_trace()` cleanly.
3. Cache hit path: Must call `start_trace()` and `end_trace(cache_hit=True, ...)` and record turn in `SessionMemoryService`.
4. Vector retrieval output: Must include `documents` list with `content`, `source`, `distance`, `score`, and `chunk_id`.
5. Reranking output: Must include `candidates_out` and `documents` with `rerank_score`.

---

### Task 1: Restore `reranker` and `_stage_ctx()` in `QueryOrchestrator`

**Files:**
- Modify: `app/use_cases/chat/query_orchestrator.py`
- Test: `tests/unit/test_orchestrator_reranker_stage.py`

**Interfaces:**
- Consumes: `reranker: Optional[Any] = None` in `__init__`, `self.pipeline_tracer`
- Produces: `self.reranker`, `self._stage_ctx(stage: PipelineStage, input_metadata: Optional[dict])`

- [ ] **Step 1: Inspect `__init__` signature in `query_orchestrator.py`**
Verify missing `reranker` parameter and add `reranker=None` to `__init__`, assigning `self.reranker = reranker`.

- [ ] **Step 2: Add `_stage_ctx` method to `QueryOrchestrator`**
```python
    @contextmanager
    def _stage_ctx(self, stage: PipelineStage, input_metadata: Optional[dict[str, Any]] = None):
        """Safely trace a pipeline stage if pipeline_tracer is configured (Task AB-6.2)."""
        if self.pipeline_tracer:
            try:
                with self.pipeline_tracer.trace_stage(stage, input_metadata=input_metadata) as span:
                    yield span
                return
            except Exception as e:
                logger.warning("Failed to trace stage %s: %s", stage, e)
        yield None
```

- [ ] **Step 3: Run `test_orchestrator_reranker_stage.py` to verify `TypeError: unexpected keyword argument 'reranker'` is resolved**
Run: `.venv\Scripts\python -m pytest tests/unit/test_orchestrator_reranker_stage.py -v`
Expected: Passes `__init__` instantiation, fails later on missing stage assertions.

---

### Task 2: Re-instrument `start_trace()` and `end_trace()` in `answer()` and `_finish()`

**Files:**
- Modify: `app/use_cases/chat/query_orchestrator.py`
- Test: `tests/unit/test_orchestrator_memory_tracing.py`

**Interfaces:**
- Consumes: `self.pipeline_tracer.start_trace(question)`, `self.pipeline_tracer.end_trace(...)`
- Produces: Monotonic trace lifecycles for all query paths (fast-path rejection, cache-hit, and full RAG).

- [ ] **Step 1: Add `start_trace` at entry of `answer()`**
In `answer()` method before memory lookup and fast-paths:
```python
        if self.pipeline_tracer:
            try:
                self.pipeline_tracer.start_trace(question)
            except Exception as trace_err:
                logger.warning("Failed to start pipeline trace: %s", trace_err)
```

- [ ] **Step 2: Add `end_trace` in `_finish()` closure**
Inside `_finish(res)`:
```python
        if self.pipeline_tracer:
            try:
                tokens_data = res.get("tokens") if isinstance(res, dict) else None
                total_tokens = 0
                if isinstance(tokens_data, dict):
                    total_tokens = tokens_data.get("total_tokens", 0)
                elif hasattr(tokens_data, "total_tokens"):
                    total_tokens = getattr(tokens_data, "total_tokens", 0)
                cache_hit = bool(res.get("cache_hit", False)) if isinstance(res, dict) else False

                self.pipeline_tracer.end_trace(
                    cache_hit=cache_hit,
                    total_tokens=total_tokens,
                    final_response=ans_text,
                )
            except Exception:
                pass
```

- [ ] **Step 3: Run memory tracing fast-path tests**
Run: `.venv\Scripts\python -m pytest tests/unit/test_orchestrator_memory_tracing.py -k "fast_path or cache_hit or memory" -v`
Expected: PASS

---

### Task 3: Restore `VECTOR_RETRIEVAL` and `RERANKING` Stage Tracing with Document Chunks

**Files:**
- Modify: `app/use_cases/chat/query_orchestrator.py`
- Test: `tests/unit/test_orchestrator_reranker_stage.py`

**Interfaces:**
- Consumes: `raw_candidates` from `retrieval.retrieve_raw_candidates()` or `retrieval.retrieve()`, `reranker.rerank()`
- Produces: `ret_span.set_output(chunks_count=..., documents=[...])` and `rerank_span.set_output(candidates_out=..., documents=[...])`

- [ ] **Step 1: Wrap vector retrieval in `_stage_ctx(PipelineStage.VECTOR_RETRIEVAL)`**
Restore candidate retrieval logic:
```python
        with self._stage_ctx(
            PipelineStage.VECTOR_RETRIEVAL,
            input_metadata={"query": retrieval_query, "top_k": RAG_CANDIDATE_COUNT}
        ) as ret_span:
            if hasattr(self.retrieval, "retrieve_raw_candidates"):
                raw_candidates = self.retrieval.retrieve_raw_candidates(retrieval_query, **retrieval_kwargs)
            else:
                raw_candidates = self.retrieval.retrieve(retrieval_query, rerank=False, **retrieval_kwargs)

            if ret_span:
                ret_span.set_output(
                    chunks_count=len(raw_candidates) if raw_candidates else 0,
                    sources=[e.get("metadata", {}).get("source") for e in raw_candidates[:5]] if raw_candidates else [],
                    documents=[
                        {
                            "content": e.get("text", "")[:300].strip(),
                            "source": e.get("metadata", {}).get("source", "unknown"),
                            "distance": e.get("distance"),
                            "score": e.get("score"),
                            "chunk_id": e.get("id"),
                        }
                        for e in (raw_candidates or [])
                    ],
                )
```

- [ ] **Step 2: Reintroduce reranking stage with `_stage_ctx(PipelineStage.RERANKING)`**
```python
        if self.reranker and raw_candidates:
            with self._stage_ctx(
                PipelineStage.RERANKING,
                input_metadata={
                    "candidates_in": len(raw_candidates),
                    "top_k": RAG_FINAL_K,
                    "query": retrieval_query,
                    "documents": [
                        {
                            "content": e.get("text", "")[:300].strip(),
                            "source": e.get("metadata", {}).get("source", "unknown"),
                            "distance": e.get("distance"),
                            "score": e.get("score"),
                            "chunk_id": e.get("id"),
                        }
                        for e in (raw_candidates or [])
                    ],
                }
            ) as rerank_span:
                reranked_candidates = self.reranker.rerank(retrieval_query, raw_candidates, top_k=RAG_FINAL_K)
                if rerank_span:
                    rerank_span.set_output(
                        candidates_out=len(reranked_candidates),
                        documents=[
                            {
                                "content": e.get("text", "")[:300].strip(),
                                "source": e.get("metadata", {}).get("source", "unknown"),
                                "rerank_score": e.get("rerank_score") or e.get("score"),
                                "chunk_id": e.get("id"),
                            }
                            for e in reranked_candidates
                        ],
                    )
        else:
            reranked_candidates = raw_candidates[:RAG_FINAL_K] if raw_candidates else []

        selected_evidence = self.retrieval.select_relevant(
            retrieval_query,
            reranked_candidates,
            max_evidence=RAG_FINAL_K,
            distance_threshold=RAG_DISTANCE_THRESHOLD,
            max_context_chars=RAG_MAX_CONTEXT_CHARS,
        )
```

- [ ] **Step 3: Run `test_orchestrator_reranker_stage.py`**
Run: `.venv\Scripts\python -m pytest tests/unit/test_orchestrator_reranker_stage.py -v`
Expected: PASS

---

### Task 4: Restore `NORMALIZATION`, `CACHE_LOOKUP`, `LLM_GENERATION`, and Negative Citation Guardrail

**Files:**
- Modify: `app/use_cases/chat/query_orchestrator.py`
- Test: `tests/unit/test_orchestrator_memory_tracing.py`
- Test: `tests/unit/test_negative_citation_guardrail.py`
- Test: `tests/unit/test_llm_outage_fallback.py`
- Test: `tests/unit/test_relevance_feedback.py`

- [ ] **Step 1: Wrap query normalization and cache lookup in stage spans**
Wrap normalization step in `with self._stage_ctx(PipelineStage.NORMALIZATION, input_metadata={"raw_query": question}) as norm_span:` and cache check in `with self._stage_ctx(PipelineStage.CACHE_LOOKUP, input_metadata={"cache_key": cache_key, "query": question}) as cache_span:`.

- [ ] **Step 2: Wrap LLM generation in `_stage_ctx(PipelineStage.LLM_GENERATION)`**
Wrap LLM generation call, record finish reason, preview, and token counts.

- [ ] **Step 3: Restore Negative Citation Guardrail & Clean Outage Fallback**
In `query_orchestrator.py`:
- Reinstate negative response suppression:
  ```python
  is_negative = is_negative_response(answer)
  if is_negative:
      citations = []
      _pending_citations[session_id] = []
      answer = answer.replace(RELEVANCE_PROMPT, "").strip()
  ```
- Do not append `RELEVANCE_PROMPT` to empty-evidence `no_info_ans`:
  ```python
  no_info_ans = "I could not find that information in the available documents."
  ```
- Ensure LLM outage fallback returns cleanly without conflicting with deferral tests.

- [ ] **Step 4: Run all orchestrator unit tests**
Run: `.venv\Scripts\python -m pytest tests/unit/test_orchestrator_memory_tracing.py tests/unit/test_negative_citation_guardrail.py tests/unit/test_llm_outage_fallback.py tests/unit/test_relevance_feedback.py -v`
Expected: ALL pass.

---

### Task 5: Full Regression Verification

**Files:**
- Verify: `tests/unit/test_monotonic_pipeline_tracer.py`
- Verify: `tests/unit/test_orchestrator_memory_tracing.py`
- Verify: `tests/unit/test_orchestrator_reranker_stage.py`
- Verify: `tests/unit/test_negative_citation_guardrail.py`
- Verify: `tests/unit/test_llm_outage_fallback.py`
- Verify: `tests/unit/test_relevance_feedback.py`
- Verify: `tests/unit/test_document_project_cache_access.py`
- Verify: `tests/unit/test_rbac_end_to_end.py`

- [ ] **Step 1: Run complete orchestrator test suite**
Run: `.venv\Scripts\python -m pytest tests/unit/test_monotonic_pipeline_tracer.py tests/unit/test_orchestrator_memory_tracing.py tests/unit/test_orchestrator_reranker_stage.py tests/unit/test_negative_citation_guardrail.py tests/unit/test_llm_outage_fallback.py tests/unit/test_relevance_feedback.py tests/unit/test_document_project_cache_access.py tests/unit/test_rbac_end_to_end.py -v`
Expected: ALL 8 test files pass with 100% green.
