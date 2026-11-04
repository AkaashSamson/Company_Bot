# Reranker Decoupling, Telemetry Precision & Citation Guardrails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple [`BgeReranker`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/vector/bge_reranker.py) into [`QueryOrchestrator`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py) as a first-class [`PipelineStage.RERANKING`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/pipeline_tracer.py#L49) stage that takes 13 raw vector candidates and narrows them to top 4 reranked candidates (with all 13 raw chunks and 4 reranked chunks visible in Langfuse), upgrade [`PipelineTracer`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/pipeline_tracer.py) and [`LangfuseProvider`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/langfuse_provider.py) to high-resolution monotonic clocks (`time.perf_counter()`), and implement Task AK-5.2 citation guardrails on negative responses.

**Architecture:**
1. **Reranker Pipeline Decoupling:** Inject `reranker: Optional[RerankerPort] = None` into [`QueryOrchestrator`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py). `VECTOR_RETRIEVAL` fetches 13 raw candidates from [`RetrievalService`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/retrieval_service.py) without internal reranking and records all 13 chunks in span output metadata. A dedicated `RERANKING` span runs cross-encoder reranking to produce 4 chunks and records all 4 reranked chunks in span output metadata.
2. **Provider-Agnostic High-Resolution Timing:** In [`pipeline_tracer.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/pipeline_tracer.py), store `start_perf = time.perf_counter()` on `StageSpan` and `TraceContext`. Calculate `duration_ms` using monotonic time deltas, eliminating Windows ~15ms clock quantization and 0.0ms collapsed spans.
3. **OpenTelemetry-Compliant Waterfall Timestamps:** In [`langfuse_provider.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/langfuse_provider.py), compute strictly monotonic `child_end_ns = child_start_ns + max(int(duration_ms * 1_000_000), 100_000)`, guaranteeing non-zero durations and strictly ordered waterfall spans in Langfuse and any OTel-based backend.
4. **Negative Response Citation Guardrails (Task AK-5.2):** When responses are negative ("I could not find that information..."), suppress citations, clear pending citations, and strip dangling `RELEVANCE_PROMPT` prompts.

**Tech Stack:** Python 3.12, Pytest, Langfuse Python SDK (v4+), OpenTelemetry, ChromaDB, Sentence-Transformers (BGE-Reranker-v2).

**Spec Reference:** [`Documentation/Plan/v3/Task_Timeline.md`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/Documentation/Plan/v3/Task_Timeline.md) (Tasks AK-5.2, AB-6.1, AB-6.2, and Neha-Reranking integration).

---

## Global Constraints

1. **Hot File Safety:** Edits to [`app/use_cases/chat/query_orchestrator.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py) must be surgical, preserving conversation logging, RBAC scoping, and semantic cache paths.
2. **Telemetry Non-Blocking:** All span recording, timing calculations, and export operations must fail-safe without throwing unhandled exceptions to user queries.
3. **Backward Compatibility:** `RetrievalService.retrieve()` must support both decoupled caller-managed reranking and standalone backward compatibility fallback.
4. **Streamlit UI Cleanliness:** No raw telemetry strings, token counts, or debug payloads in user-facing chat bubbles ([Task AK-6.1](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/Documentation/Plan/v3/Task_Timeline.md#L325-L327)).
5. **Exact Candidate Ratios:** Vector retrieval candidate pool = 13 (`RAG_RAW_K = 13` / `RAG_CANDIDATE_COUNT = 13`); reranked final output = 4 (`RAG_FINAL_K = 4`).

---

## Review Focus

1. **Both Candidate Pools Visible in Langfuse:** Verify `VECTOR_RETRIEVAL` span metadata contains all 13 raw retrieved chunks, and `RERANKING` span metadata contains all 4 reranked chunks.
2. **Zero-Duration Prevention:** Fast stages (< 1ms like Normalization or Cache Check) must report non-zero duration (`> 0.0ms`) in Langfuse instead of collapsing.
3. **No Double-Reranking:** When orchestrator runs the `RERANKING` stage, ensure `RetrievalService` does not execute a redundant rerank pass.
4. **Fallback When Reranker is None:** When `BgeReranker` is not initialized or disabled, orchestrator must gracefully fall back to vector distance order without crashing.
5. **Negative Response Cleanliness:** When LLM or vector search yields no relevant documents, answer text must not suggest non-existent references and citations list must be empty.

---

## File Structure & Responsibilities

| File | Status | Responsibility |
| :--- | :--- | :--- |
| [`app/infrastructure/observability/pipeline_tracer.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/pipeline_tracer.py) | **Modify** | Add `start_perf: float` (`time.perf_counter`) to `StageSpan` and `TraceContext`. Ensure `duration_ms` has sub-microsecond precision. |
| [`app/infrastructure/observability/langfuse_provider.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/langfuse_provider.py) | **Modify** | Ensure `child_end_ns` reflects `duration_ms` without collapsing to `start_time` for sub-ms stages. |
| [`app/use_cases/chat/retrieval_service.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/retrieval_service.py) | **Modify** | Add `retrieve_raw_candidates()` method (fetches top 13 without reranking) and support `rerank=False` flag in `retrieve()`. |
| [`app/use_cases/chat/query_orchestrator.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py) | **Modify** | Inject `reranker`, retrieve 13 chunks in `VECTOR_RETRIEVAL`, emit `PipelineStage.RERANKING` span for 4 chunks, log all chunks to Langfuse, and enforce negative citation guardrails. |
| [`tests/unit/test_monotonic_pipeline_tracer.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/tests/unit/test_monotonic_pipeline_tracer.py) | **Create** | Verify `perf_counter` non-zero duration and Langfuse timestamp spacing. |
| [`tests/unit/test_orchestrator_reranker_stage.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/tests/unit/test_orchestrator_reranker_stage.py) | **Create** | Verify 13 raw -> 4 reranked chunk flow, span emission, and Langfuse document payloads. |
| [`tests/unit/test_negative_citation_guardrail.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/tests/unit/test_negative_citation_guardrail.py) | **Create** | Verify negative responses suppress citations and remove dangling reference prompt. |

---

## Implementation Tasks

### Task 1: High-Precision Monotonic Telemetry in `PipelineTracer` & `LangfuseProvider`

**Files:**
- Modify: [`app/infrastructure/observability/pipeline_tracer.py:L64-L120`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/pipeline_tracer.py#L64-L120), [`app/infrastructure/observability/pipeline_tracer.py:L136-L203`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/pipeline_tracer.py#L136-L203)
- Modify: [`app/infrastructure/observability/langfuse_provider.py:L240-L260`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/langfuse_provider.py#L240-L260)
- Test: [`tests/unit/test_monotonic_pipeline_tracer.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/tests/unit/test_monotonic_pipeline_tracer.py)

**Interfaces:**
- Consumes: `time.perf_counter()`, `time.time()`.
- Produces: `StageSpan.duration_ms` with high-resolution float precision; non-zero `child_end_ns` in Langfuse OpenTelemetry spans.

- [ ] **Step 1: Write failing unit test for monotonic high-precision timing**

Create [`tests/unit/test_monotonic_pipeline_tracer.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/tests/unit/test_monotonic_pipeline_tracer.py):
```python
import time
from unittest.mock import MagicMock
from app.infrastructure.observability.pipeline_tracer import PipelineTracer, PipelineStage, TraceContext, StageSpan
from app.infrastructure.observability.langfuse_provider import LangfuseProvider

def test_stage_span_high_precision_duration():
    span = StageSpan(stage=PipelineStage.NORMALIZATION, start_time=time.time())
    # Sub-millisecond sleep
    time.sleep(0.001)
    span.finish()
    assert span.duration_ms > 0.0, "duration_ms must be non-zero even for short operations"

def test_trace_context_high_precision_duration():
    tracer = PipelineTracer.create_new(enable_tracing=True)
    trace = tracer.start_trace("test query")
    with TraceContext(stage=PipelineStage.CACHE_LOOKUP, tracer=tracer) as ctx:
        time.sleep(0.0005)
    
    assert ctx.duration_ms > 0.0
    assert trace.spans[0].duration_ms > 0.0

def test_langfuse_child_span_timestamps_non_zero():
    mock_client = MagicMock()
    mock_root = MagicMock()
    mock_child = MagicMock()
    mock_client.start_observation.return_value = mock_root
    mock_root.start_observation.return_value = mock_child
    mock_child._otel_span = MagicMock()

    provider = LangfuseProvider(public_key="pk-test", secret_key="sk-test", host="http://mock")
    provider._client = mock_client

    tracer = PipelineTracer.create_new(enable_tracing=True)
    trace = tracer.start_trace("test query")
    with TraceContext(stage=PipelineStage.NORMALIZATION, tracer=tracer):
        pass
    trace.finish(final_response="test response")

    provider.export_pipeline_trace(trace)
    assert mock_child.end.called
    end_kwargs = mock_child.end.call_args.kwargs
    assert "end_time" in end_kwargs
    # Verify child_end is strictly greater than child_start
    child_start_ns = mock_child._otel_span._start_time
    assert end_kwargs["end_time"] > child_start_ns
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/test_monotonic_pipeline_tracer.py -v`
Expected: Fails or misses `start_perf` attribute on `StageSpan`.

- [ ] **Step 3: Update `StageSpan` and `TraceContext` in `pipeline_tracer.py`**

In [`app/infrastructure/observability/pipeline_tracer.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/pipeline_tracer.py):
1. In `StageSpan`:
```python
@dataclass
class StageSpan:
    stage: PipelineStage
    start_time: float
    start_perf: float = field(default_factory=time.perf_counter)
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    ...
    def finish(self, output_metadata: Optional[dict[str, Any]] = None) -> None:
        self.end_time = time.time()
        self.duration_ms = (time.perf_counter() - self.start_perf) * 1000.0
        if output_metadata:
            self.output_metadata = output_metadata
```
2. In `TraceContext`:
```python
    def __init__(self, ...):
        ...
        self.start_perf: float = 0.0

    def __enter__(self) -> 'TraceContext':
        self.start_time = time.time()
        self.start_perf = time.perf_counter()
        ...
        self.span = StageSpan(
            stage=self.stage,
            start_time=self.start_time,
            start_perf=self.start_perf,
            input_metadata=dict(self.input_metadata),
        )
        ...

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.end_time = time.time()
        self.duration_ms = (time.perf_counter() - self.start_perf) * 1000.0
        ...
```

- [ ] **Step 4: Update `LangfuseProvider.export_pipeline_trace()` for non-zero spans**

In [`app/infrastructure/observability/langfuse_provider.py:L240-L260`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/langfuse_provider.py#L240-L260):
```python
child_start = getattr(span, "start_time", None)
child_start_ns = int(child_start * 1e9) if child_start else None
if hasattr(child_obs, "_otel_span") and child_start_ns:
    try:
        child_obs._otel_span._start_time = child_start_ns
    except Exception:
        pass

if getattr(span, "error", None):
    child_obs.update(level="ERROR", status_message=str(span.error))

dur_ms = getattr(span, "duration_ms", 0.0) or 0.0
# Ensure at least 0.1ms (100,000 ns) so span is visible and strictly monotonic
dur_ns = max(int(dur_ms * 1_000_000), 100_000)
child_end_ns = (child_start_ns + dur_ns) if child_start_ns else None
child_obs.end(end_time=child_end_ns)
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/unit/test_monotonic_pipeline_tracer.py -v`
Expected: PASS (all 3 tests pass).

---

### Task 2: Decouple Reranker into Orchestrator & Expose 13 -> 4 Chunks in Telemetry

**Files:**
- Modify: [`app/use_cases/chat/retrieval_service.py:L79-L103`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/retrieval_service.py#L79-L103)
- Modify: [`app/use_cases/chat/query_orchestrator.py:L140-L220`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py#L140-L220), [`app/use_cases/chat/query_orchestrator.py:L864-L909`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py#L864-L909), [`app/use_cases/chat/query_orchestrator.py:L1211-L1215`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py#L1211-L1215)
- Test: [`tests/unit/test_orchestrator_reranker_stage.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/tests/unit/test_orchestrator_reranker_stage.py)

**Interfaces:**
- Consumes: `RerankerPort`, `RetrievalService`, `PipelineStage.VECTOR_RETRIEVAL`, `PipelineStage.RERANKING`.
- Produces: `VECTOR_RETRIEVAL` span containing 13 candidate chunks; `RERANKING` span containing 4 reranked chunks.

- [ ] **Step 1: Write failing unit test for decoupled reranking and chunk visibility**

Create [`tests/unit/test_orchestrator_reranker_stage.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/tests/unit/test_orchestrator_reranker_stage.py):
```python
import pytest
from unittest.mock import MagicMock
from app.use_cases.chat.query_orchestrator import QueryOrchestrator
from app.infrastructure.observability.pipeline_tracer import PipelineTracer, PipelineStage

def test_orchestrator_emits_reranking_stage_with_13_in_and_4_out():
    tracer = PipelineTracer.create_new(enable_tracing=True)
    
    # 13 mock raw vector candidates
    raw_13 = [
        {"id": f"chunk-{i}", "text": f"Policy chunk text {i}", "metadata": {"source": f"DOC-{i}.docx"}, "distance": 0.1 * i}
        for i in range(13)
    ]
    # 4 top reranked chunks
    reranked_4 = [
        {**raw_13[i], "rerank_score": 0.95 - (0.1 * i)}
        for i in [2, 0, 5, 8]
    ]

    mock_retrieval = MagicMock()
    mock_retrieval.retrieve_raw_candidates.return_value = raw_13
    mock_retrieval.select_relevant.side_effect = lambda q, c, **kw: c

    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = reranked_4

    mock_llm = MagicMock()
    mock_llm.generate.return_value = "Here is the policy answer."

    orchestrator = QueryOrchestrator(
        retrieval=mock_retrieval,
        reranker=mock_reranker,
        llm=mock_llm,
        pipeline_tracer=tracer,
        enable_normalizer=False,
    )

    res = orchestrator.answer("What is the leave policy?")

    trace = tracer._current_trace
    stage_names = [s.stage for s in trace.spans]
    assert PipelineStage.VECTOR_RETRIEVAL in stage_names
    assert PipelineStage.RERANKING in stage_names

    # Check vector retrieval metadata: 13 chunks
    ret_span = next(s for s in trace.spans if s.stage == PipelineStage.VECTOR_RETRIEVAL)
    assert ret_span.output_metadata["chunks_count"] == 13
    assert len(ret_span.output_metadata["documents"]) == 13

    # Check reranking metadata: 13 in, 4 out
    rerank_span = next(s for s in trace.spans if s.stage == PipelineStage.RERANKING)
    assert rerank_span.input_metadata["candidates_in"] == 13
    assert rerank_span.output_metadata["candidates_out"] == 4
    assert len(rerank_span.output_metadata["documents"]) == 4
    assert rerank_span.output_metadata["documents"][0]["chunk_id"] == "chunk-2"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/test_orchestrator_reranker_stage.py -v`
Expected: Fails because `QueryOrchestrator` does not yet accept `reranker`, `RetrievalService` lacks `retrieve_raw_candidates`, and `RERANKING` span is not emitted.

- [ ] **Step 3: Update `RetrievalService` in `retrieval_service.py`**

In [`app/use_cases/chat/retrieval_service.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/retrieval_service.py):
1. Add `retrieve_raw_candidates()`:
```python
    def retrieve_raw_candidates(
        self,
        query_text: str,
        top_k: int = RAG_RAW_K,
        authorized_project_ids: Optional[Iterable[str]] = None,
        authorized_document_ids: Optional[Iterable[str]] = None,
        include_unassigned: bool = True,
    ) -> list[dict]:
        """Fetch raw vector candidates from store without applying cross-encoder reranker."""
        # Use existing RBAC where_filter construction
        project_ids_for_filter = None
        if authorized_project_ids is not None:
            project_ids_for_filter = list(authorized_project_ids)
            if include_unassigned and "unassigned" not in project_ids_for_filter:
                project_ids_for_filter.append("unassigned")

        where_filter = None
        if authorized_document_ids is not None:
            document_filter = {"document_id": {"$in": list(authorized_document_ids)}}
            if project_ids_for_filter is not None:
                where_filter = {
                    "$or": [
                        {"project_id": {"$in": project_ids_for_filter}},
                        document_filter,
                    ]
                }
            else:
                where_filter = document_filter

        query_kwargs = {"top_k": top_k}
        if where_filter is not None:
            query_kwargs["where"] = where_filter
        elif project_ids_for_filter is not None:
            query_kwargs["project_ids"] = project_ids_for_filter

        candidates = []
        for candidate in self.store.query(query_text, **query_kwargs):
            candidates.append({**candidate, "_query_part_index": 0})
        return candidates
```
2. In `retrieve()`, add `rerank: bool = True` parameter so caller can disable internal rerank.

- [ ] **Step 4: Update `QueryOrchestrator` in `query_orchestrator.py`**

In [`app/use_cases/chat/query_orchestrator.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py):
1. Update `__init__`:
```python
    def __init__(
        self,
        retrieval: RetrievalService,
        llm: Optional[Any] = None,
        reranker: Optional[Any] = None,
        ...
    ):
        ...
        self.retrieval = retrieval
        self.reranker = reranker or getattr(retrieval, "reranker", None)
```
2. Update `VECTOR_RETRIEVAL` and add `RERANKING` stage in `answer()`:
```python
        # AB-6.2: Vector Retrieval Stage (Fetch 13 raw candidates)
        retrieval_kwargs["top_k"] = RAG_CANDIDATE_COUNT  # 13
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

        # Dedicated Reranking Stage (Narrows 13 candidates to 4 top chunks)
        if self.reranker and raw_candidates:
            with self._stage_ctx(
                PipelineStage.RERANKING,
                input_metadata={"candidates_in": len(raw_candidates), "top_k": RAG_FINAL_K}
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

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/unit/test_orchestrator_reranker_stage.py tests/unit/test_reranker.py -v`
Expected: PASS.

---

### Task 3: Negative Response Citation Guardrails (Task AK-5.2)

**Files:**
- Modify: [`app/use_cases/chat/query_orchestrator.py:L890-L910`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py#L890-L910), [`app/use_cases/chat/query_orchestrator.py:L1010-L1035`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py#L1010-L1035)
- Test: [`tests/unit/test_negative_citation_guardrail.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/tests/unit/test_negative_citation_guardrail.py)

**Interfaces:**
- Consumes: `is_negative_response()` from [`app/domain/guards/negative_response_detector.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/domain/guards/negative_response_detector.py).
- Produces: Suppressed citations (`[]`), cleared pending citations, and clean negative answer text without dangling relevance prompts.

- [ ] **Step 1: Write failing unit test for negative response citation suppression**

Create [`tests/unit/test_negative_citation_guardrail.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/tests/unit/test_negative_citation_guardrail.py):
```python
import pytest
from unittest.mock import MagicMock
from app.use_cases.chat.query_orchestrator import QueryOrchestrator, RELEVANCE_PROMPT

def test_negative_llm_response_suppresses_citations_and_prompt():
    mock_retrieval = MagicMock()
    mock_retrieval.retrieve_raw_candidates.return_value = [
        {"id": "c1", "text": "Unrelated document text", "metadata": {"source": "DOC-1.docx"}}
    ]
    mock_retrieval.select_relevant.return_value = [
        {"id": "c1", "text": "Unrelated document text", "metadata": {"source": "DOC-1.docx"}}
    ]

    mock_llm = MagicMock()
    mock_llm.generate.return_value = "I am sorry, but the provided documents do not contain information about pet allowances."

    orchestrator = QueryOrchestrator(
        retrieval=mock_retrieval,
        llm=mock_llm,
        enable_normalizer=False,
    )

    res = orchestrator.answer("Can I bring my dog to the office?", session_id="test_sess")

    assert res["citations"] == [], "Negative responses must not return citations"
    assert RELEVANCE_PROMPT not in res["answer"], "Negative responses must not include reference prompt"

def test_empty_retrieval_negative_response_suppresses_prompt():
    mock_retrieval = MagicMock()
    mock_retrieval.retrieve_raw_candidates.return_value = []
    mock_retrieval.detect_unauthorized_relevance.return_value = None

    orchestrator = QueryOrchestrator(retrieval=mock_retrieval, enable_normalizer=False)
    res = orchestrator.answer("Something completely non-existent", session_id="test_sess")

    assert res["citations"] == []
    assert RELEVANCE_PROMPT not in res["answer"]
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/test_negative_citation_guardrail.py -v`
Expected: Fails because `RELEVANCE_PROMPT` was appended to negative response text.

- [ ] **Step 3: Implement negative response guardrails in `query_orchestrator.py`**

In [`app/use_cases/chat/query_orchestrator.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py):
1. In `no_evidence` branch (around line 894):
```python
        if not selected_evidence:
            denied = self._probe_unauthorized_relevance(retrieval_query, retrieval_kwargs, scope_flags)
            if denied is not None:
                return _finish(denied)
            no_info_ans = "I could not find that information in the available documents."
            _pending_citations[session_id] = []
            _last_interaction[session_id] = {
                "question": question,
                "context": "",
                "selected_evidence": [],
                "answer": no_info_ans,
            }
            _alternative_answer_given[session_id] = False
            return _finish({
                "answer": no_info_ans,
                "citations": [],
                "cache_hit": False,
                "tokens": None,
            })
```
2. Post-LLM generation (around line 1020):
```python
        if is_negative_response(ans):
            citations = []
            _pending_citations[session_id] = []
            ans = ans.replace(RELEVANCE_PROMPT, "").strip()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_negative_citation_guardrail.py -v`
Expected: PASS.

---

### Task 4: Full Test Suite & End-to-End Regression Verification

**Files:**
- Test: All existing integration and unit test suites

- [ ] **Step 1: Run comprehensive unit and regression suites**

```powershell
pytest tests/unit/test_monotonic_pipeline_tracer.py tests/unit/test_orchestrator_reranker_stage.py tests/unit/test_negative_citation_guardrail.py tests/unit/test_reranker.py tests/unit/test_retrieval_quality_integration.py tests/unit/test_chunk_metadata.py -v
```
Expected: All tests PASS.

- [ ] **Step 2: Run core integration suite**

```powershell
pytest tests/integration/test_orchestrator_access_gate.py tests/unit/test_retrieval_selection.py tests/unit/test_groq_token_standardization.py -v
```
Expected: All tests PASS.

- [ ] **Step 3: Verification against live server**

Send query via PowerShell / curl to running server (`http://localhost:8000/api/chat`):
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/chat" -Method Post -ContentType "application/json" -Body '{"message": "What is the probation period policy?", "session_id": "test_rerank_live"}'
```
Verify:
1. Valid response with citations.
2. In Langfuse dashboard:
   - Root trace contains both `VECTOR_RETRIEVAL` (13 chunks) and `RERANKING` (4 chunks).
   - All spans have accurate, non-zero `duration_ms` (> 0.0ms).
   - Strict chronological waterfall sequencing.

- [ ] **Step 4: Git commit clean changes**

```bash
git add app/infrastructure/observability/pipeline_tracer.py app/infrastructure/observability/langfuse_provider.py app/use_cases/chat/retrieval_service.py app/use_cases/chat/query_orchestrator.py tests/unit/test_monotonic_pipeline_tracer.py tests/unit/test_orchestrator_reranker_stage.py tests/unit/test_negative_citation_guardrail.py docs/superpowers/plans/2026-10-01-reranker-decoupling-and-telemetry-precision.md
git commit -m "feat(pipeline): decouple reranker stage, enable 13-to-4 chunk Langfuse telemetry, monotonic timing, and negative response citation guardrails"
```
