# Langfuse Pipeline Trace & Stage Spans Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the observability telemetry pipeline into a clean Hexagonal / Ports & Adapters architecture where [`ObservabilityManager`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/manager.py) delegates complete [`PipelineTrace`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/pipeline_tracer.py) objects to [`LangfuseProvider`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/langfuse_provider.py), enabling top-level `input` (`trace.query`), `output` (`final_response`), and nested stage spans (`NORMALIZATION`, `CACHE_LOOKUP`, `VECTOR_RETRIEVAL`, `LLM_GENERATION`) in the Langfuse UI.

**Architecture:** 
1. **Domain Model & Contracts:** Update [`PipelineTrace`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/pipeline_tracer.py#L238) and `end_trace()` to capture `final_response` and stage input/output payloads. Add `export_pipeline_trace(trace)` to [`BaseObservabilityProvider`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/domain/ports/observability.py#L34).
2. **Dispatcher:** In [`ObservabilityManager.dispatch_trace()`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/manager.py#L140), stop flattening traces into metadata; delegate the full `PipelineTrace` object directly to `provider.export_pipeline_trace(trace)`.
3. **Vendor Adapter:** In [`LangfuseProvider`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/langfuse_provider.py), implement `export_pipeline_trace()` to create a root trace with `input=trace.query` and `output={"final_response": trace.final_response}`, then iterate `trace.spans` to create properly typed and nested child observations (`span`, `retriever`, `generation` with token metrics).

**Tech Stack:** Python 3.12, Langfuse Python SDK (v4+), OpenTelemetry, Pytest.

**Spec Reference:** [`Documentation/Plan/v3/Task_Timeline.md`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/Documentation/Plan/v3/Task_Timeline.md) (Subsystem 3 Observability Bridge & Phase 4 Tracing).

---

## Global Constraints

1. **Hot File Safety:** Any changes to [`app/use_cases/chat/query_orchestrator.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py) must be strictly additive and surgical.
2. **Zero Crash Tolerance:** Telemetry failures (network timeouts, Langfuse API errors, serialization failures) must never raise exceptions to the user query path.
3. **Backwards Compatibility:** Existing `create_trace()` and `record_llm_call()` methods on `BaseObservabilityProvider` must remain intact so legacy callers do not break.
4. **Offline / Dry-Run Safety:** When `LangfuseProvider` runs with `enabled=False` or invalid credentials, it must gracefully no-op without errors.

---

## Review Focus

1. **Missing or Empty Final Response:** If query hits an error or returns early without an answer, `output` must safely record `{"final_response": ""}` or error details instead of crashing.
2. **Missing Token Details on Spans:** Non-LLM spans (Normalization, Retrieval) have 0 tokens; ensure `LangfuseProvider` doesn't pass invalid usage payloads to span types.
3. **Parent-Child Span Nesting:** Child observations must be nested under the root trace (`root_obs`) so they appear as a tree in the Langfuse waterfall UI rather than disconnected root traces.
4. **Time Alignment:** Child spans must preserve their actual start and end timestamps (`span.start_time`, `span.end_time`) so waterfall timelines in Langfuse reflect real execution latencies.
5. **Caller-Supplied Session & User IDs:** Ensure `session_id` and `user_id` from `QueryOrchestrator` propagate down through `PipelineTrace` into Langfuse root trace.

---

## File Structure & Responsibilities

| File | Status | Responsibility |
| :--- | :--- | :--- |
| [`tests/unit/test_langfuse_pipeline_trace_export.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/tests/unit/test_langfuse_pipeline_trace_export.py) | **Create** | Unit tests verifying `PipelineTrace` export, input/output payload population, and nested stage span translation in `LangfuseProvider`. |
| [`app/domain/ports/observability.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/domain/ports/observability.py) | **Modify** | Add `export_pipeline_trace(trace: Any) -> None` to `BaseObservabilityProvider` protocol. |
| [`app/infrastructure/observability/pipeline_tracer.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/pipeline_tracer.py) | **Modify** | Update `finish()` and `end_trace()` to accept and store `final_response: Optional[str] = None`. |
| [`app/use_cases/chat/query_orchestrator.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py) | **Modify** | Pass `final_response=ans_text` in `_finish()`, and pass `input_metadata` to stage contexts. |
| [`app/infrastructure/observability/manager.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/manager.py) | **Modify** | In `dispatch_trace()`, delegate full `PipelineTrace` directly to `provider.export_pipeline_trace(trace)`. |
| [`app/infrastructure/observability/langfuse_provider.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/langfuse_provider.py) | **Modify** | Implement `export_pipeline_trace()` with root trace (`input`, `output`) and nested child observations. |

---

## Implementation Tasks

### Task 1: Create Unit Test Suite for Pipeline Trace Export

**Files:**
- Create: `tests/unit/test_langfuse_pipeline_trace_export.py`

**Interfaces:**
- Consumes: `PipelineTrace`, `StageSpan`, `PipelineStage`, `LangfuseProvider`, `ObservabilityManager`.
- Produces: Failing unit test assertions for full trace export, input/output mapping, and child span generation.

- [ ] **Step 1: Write the failing unit tests**

```python
"""Tests for Langfuse Pipeline Trace Export and Stage Span Hierarchy."""
import time
import pytest
from unittest.mock import MagicMock, patch

from app.infrastructure.observability.pipeline_tracer import PipelineTrace, StageSpan, PipelineStage
from app.infrastructure.observability.langfuse_provider import LangfuseProvider
from app.infrastructure.observability.manager import ObservabilityManager


@pytest.fixture
def sample_pipeline_trace():
    trace = PipelineTrace(
        trace_id="trace-abc-123",
        query="how many sick leaves I have?",
        start_time=time.time() - 2.0,
        metadata={"user_id": "emp-001", "session_id": "session-xyz"},
    )
    # Add normalization span
    span_norm = StageSpan(
        stage=PipelineStage.NORMALIZATION,
        start_time=trace.start_time,
        end_time=trace.start_time + 0.1,
        input_metadata={"raw_query": "how many sick leaves I have?"},
        output_metadata={"normalized_query": "how many sick leaves i have"},
    )
    trace.add_span(span_norm)

    # Add retrieval span
    span_retrieval = StageSpan(
        stage=PipelineStage.VECTOR_RETRIEVAL,
        start_time=trace.start_time + 0.1,
        end_time=trace.start_time + 0.5,
        input_metadata={"query": "how many sick leaves i have"},
        output_metadata={"chunks_count": 3},
    )
    trace.add_span(span_retrieval)

    # Add LLM generation span
    span_llm = StageSpan(
        stage=PipelineStage.LLM_GENERATION,
        start_time=trace.start_time + 0.5,
        end_time=trace.start_time + 1.8,
        input_metadata={"model": "llama-3.3-70b-versatile"},
        output_metadata={"finish_reason": "stop"},
        prompt_tokens=500,
        completion_tokens=201,
        tokens_used=701,
    )
    trace.add_span(span_llm)

    # Finish trace with final response
    trace.finish(
        cache_hit=False,
        total_tokens=701,
        final_response="You have 12 sick leaves remaining.",
    )
    return trace


def test_pipeline_trace_captures_final_response(sample_pipeline_trace):
    assert sample_pipeline_trace.final_response == "You have 12 sick leaves remaining."
    assert sample_pipeline_trace.total_tokens == 701
    assert len(sample_pipeline_trace.spans) == 3


def test_observability_manager_delegates_to_export_pipeline_trace(sample_pipeline_trace):
    manager = ObservabilityManager()
    mock_provider = MagicMock()
    manager.set_provider(mock_provider)

    manager.dispatch_trace(sample_pipeline_trace)

    mock_provider.export_pipeline_trace.assert_called_once_with(sample_pipeline_trace)


def test_langfuse_provider_exports_root_and_child_spans(sample_pipeline_trace):
    provider = LangfuseProvider(public_key="pk-dummy", secret_key="sk-dummy", host="http://localhost:3000")
    provider.enabled = True
    mock_client = MagicMock()
    mock_root_obs = MagicMock()
    mock_child_obs = MagicMock()
    mock_client.start_observation.side_effect = [mock_root_obs, mock_child_obs, mock_child_obs, mock_child_obs]
    provider._client = mock_client

    provider.export_pipeline_trace(sample_pipeline_trace)

    # Verify Root Observation created with proper input and output
    mock_client.start_observation.assert_any_call(
        name="QueryOrchestrator.answer",
        as_type="chain",
        input="how many sick leaves I have?",
        output={"final_response": "You have 12 sick leaves remaining."},
        metadata=pytest.approx(mock_client.start_observation.call_args_list[0][1]["metadata"]),
    )

    # Verify child observations created (3 spans)
    assert mock_client.start_observation.call_count == 4
    mock_client.flush.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_langfuse_pipeline_trace_export.py -v
```
Expected: FAIL (`TypeError: PipelineTrace.finish() got an unexpected keyword argument 'final_response'`).

---

### Task 2: Update `PipelineTrace` and `PipelineTracer` to Support `final_response`

**Files:**
- Modify: [`app/infrastructure/observability/pipeline_tracer.py:L263-L283`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/pipeline_tracer.py#L263-L283)
- Modify: [`app/infrastructure/observability/pipeline_tracer.py:L456-L500`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/pipeline_tracer.py#L456-L500)

**Interfaces:**
- Consumes: `final_response: Optional[str] = None`
- Produces: `trace.final_response` populated and preserved across trace lifecycle.

- [ ] **Step 1: Update `PipelineTrace.finish()`**

In [`app/infrastructure/observability/pipeline_tracer.py:L263`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/pipeline_tracer.py#L263):
```python
    def finish(
        self,
        cache_hit: bool = False,
        early_exit: bool = False,
        exit_stage: Optional[PipelineStage] = None,
        exit_reason: Optional[str] = None,
        total_tokens: int = 0,
        final_response: Optional[str] = None,
    ) -> None:
        """Mark trace as finished and calculate totals."""
        self.end_time = time.time()
        self.total_duration_ms = (self.end_time - self.start_time) * 1000
        self.cache_hit = cache_hit
        self.early_exit = early_exit
        self.exit_stage = exit_stage
        self.exit_reason = exit_reason
        self.total_tokens = total_tokens
        if final_response is not None:
            self.final_response = final_response
        
        # Sum tokens from all spans, falling back to passed total_tokens
        span_tokens = sum(s.tokens_used for s in self.spans)
        self.total_tokens = span_tokens if span_tokens > 0 else total_tokens
```

- [ ] **Step 2: Update `PipelineTracer.end_trace()`**

In [`app/infrastructure/observability/pipeline_tracer.py:L456`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/pipeline_tracer.py#L456):
```python
    def end_trace(
        self,
        trace_id: Optional[str] = None,
        cache_hit: bool = False,
        early_exit: bool = False,
        exit_stage: Optional[PipelineStage] = None,
        exit_reason: Optional[str] = None,
        total_tokens: int = 0,
        final_response: Optional[str] = None,
    ) -> Optional[PipelineTrace]:
        ...
            trace.finish(
                cache_hit=cache_hit,
                early_exit=early_exit,
                exit_stage=exit_stage,
                exit_reason=exit_reason,
                total_tokens=total_tokens,
                final_response=final_response,
            )
```

- [ ] **Step 3: Run Task 1 tests to verify progress**

Run:
```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_langfuse_pipeline_trace_export.py -k "test_pipeline_trace_captures_final_response" -v
```
Expected: PASS.

---

### Task 3: Add `export_pipeline_trace` to Observability Port & Manager

**Files:**
- Modify: [`app/domain/ports/observability.py:L34-L60`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/domain/ports/observability.py#L34-L60)
- Modify: [`app/infrastructure/observability/manager.py:L140-L215`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/manager.py#L140-L215)

**Interfaces:**
- Consumes: `BaseObservabilityProvider.export_pipeline_trace(trace: Any) -> None`
- Produces: Direct, decoupled delegation of `PipelineTrace` from `ObservabilityManager` to active provider.

- [ ] **Step 1: Update `BaseObservabilityProvider` Protocol**

In [`app/domain/ports/observability.py:L34`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/domain/ports/observability.py#L34):
```python
@runtime_checkable
class BaseObservabilityProvider(Protocol):
    """Vendor-neutral observability port for tracing and token/cost tracking."""

    def export_pipeline_trace(self, trace: Any) -> None:
        """Convert and export a complete domain PipelineTrace with child spans."""
        ...

    def create_trace(
        self,
        name: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TraceSpanPort:
        ...
```

- [ ] **Step 2: Update `ObservabilityManager.dispatch_trace()`**

In [`app/infrastructure/observability/manager.py:L140`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/manager.py#L140):
```python
    def dispatch_trace(self, trace: Any) -> None:
        """Dispatch a completed PipelineTrace execution record to the active observability provider."""
        if trace is None:
            return

        try:
            with self._lock:
                provider = self._active_provider

            # Clean Architecture: If provider supports direct pipeline export, delegate full object
            if hasattr(provider, "export_pipeline_trace") and callable(provider.export_pipeline_trace):
                provider.export_pipeline_trace(trace)
                return

            # Legacy fallback for providers without export_pipeline_trace
            ...
```

- [ ] **Step 3: Run Task 1 tests to verify manager delegation**

Run:
```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_langfuse_pipeline_trace_export.py -k "test_observability_manager_delegates" -v
```
Expected: PASS.

---

### Task 4: Implement `export_pipeline_trace()` in `LangfuseProvider`

**Files:**
- Modify: [`app/infrastructure/observability/langfuse_provider.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/langfuse_provider.py)

**Interfaces:**
- Consumes: `PipelineTrace` containing `query`, `final_response`, and `spans` (`StageSpan`).
- Produces: Langfuse root observation with `input=trace.query` and `output={"final_response": ...}`, plus child observations for each stage.

- [ ] **Step 1: Implement `export_pipeline_trace`**

In [`app/infrastructure/observability/langfuse_provider.py`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/langfuse_provider.py):
```python
    def export_pipeline_trace(self, trace: Any) -> None:
        """Convert domain PipelineTrace and StageSpans into Langfuse hierarchical observations."""
        if not self.enabled or self._client is None or trace is None:
            return

        try:
            query = getattr(trace, "query", "")
            final_response = getattr(trace, "final_response", None)
            trace_id = getattr(trace, "trace_id", None)
            meta = {
                "total_duration_ms": getattr(trace, "total_duration_ms", 0.0),
                "cache_hit": getattr(trace, "cache_hit", False),
                "early_exit": getattr(trace, "early_exit", False),
                "exit_stage": getattr(trace.exit_stage, "value", None) if getattr(trace, "exit_stage", None) else None,
                "total_tokens": getattr(trace, "total_tokens", 0),
            }
            user_id = getattr(trace, "metadata", {}).get("user_id") if hasattr(trace, "metadata") else None
            session_id = getattr(trace, "metadata", {}).get("session_id", trace_id)

            # 1. Start Root Observation
            root_obs = self._client.start_observation(
                name="QueryOrchestrator.answer",
                as_type="chain",
                input=query,
                output={"final_response": final_response} if final_response is not None else None,
                metadata={**meta, "session_id": session_id, "user_id": user_id},
            )

            # 2. Iterate and attach Child Stage Spans
            spans = getattr(trace, "spans", []) or []
            for span in spans:
                stage_val = getattr(span.stage, "value", str(span.stage)) if hasattr(span, "stage") else "stage"
                obs_type = _resolve_observation_type(stage_val)

                span_kwargs: Dict[str, Any] = {
                    "name": f"stage_{stage_val}",
                    "as_type": obs_type,
                    "input": getattr(span, "input_metadata", None),
                    "output": getattr(span, "output_metadata", None),
                    "metadata": {
                        "duration_ms": getattr(span, "duration_ms", 0.0),
                        "error": getattr(span, "error", None),
                    },
                }

                # Attach parent observation link if supported by SDK
                if root_obs is not None and hasattr(root_obs, "id"):
                    span_kwargs["parent_observation_id"] = root_obs.id

                # Attach generation model & token metrics for LLM stages
                if stage_val == "llm_generation" or obs_type == "generation":
                    model_name = getattr(span, "input_metadata", {}).get("model", "unknown")
                    span_kwargs["model"] = model_name
                    p_tok = getattr(span, "prompt_tokens", 0)
                    c_tok = getattr(span, "completion_tokens", 0)
                    t_tok = getattr(span, "tokens_used", 0) or (p_tok + c_tok)
                    if t_tok > 0 or p_tok > 0 or c_tok > 0:
                        span_kwargs["usage_details"] = {
                            "input": p_tok,
                            "output": c_tok,
                            "total": t_tok,
                        }

                child_obs = self._client.start_observation(**span_kwargs)
                if child_obs is not None:
                    if getattr(span, "error", None):
                        child_obs.update(level="ERROR", status_message=str(span.error))
                    child_obs.end()

            # 3. End Root Observation
            if root_obs is not None:
                root_obs.end()

            self.flush()

        except Exception as exc:
            logger.warning("Langfuse export_pipeline_trace encountered error: %s", exc)
```

- [ ] **Step 2: Run Task 1 tests to verify full Langfuse export**

Run:
```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_langfuse_pipeline_trace_export.py -v
```
Expected: All 3 tests PASS.

---

### Task 5: Wire `final_response` & Stage Payloads in `QueryOrchestrator`

**Files:**
- Modify: [`app/use_cases/chat/query_orchestrator.py:L265`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py#L265)
- Modify: [`app/use_cases/chat/query_orchestrator.py:L431-L715`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py#L431-L715)

**Interfaces:**
- Consumes: `ans_text` in `_finish()`.
- Produces: `end_trace(final_response=ans_text)` and enriched `StageSpan` metadata.

- [ ] **Step 1: Pass `final_response=ans_text` in `_finish()`**

In [`app/use_cases/chat/query_orchestrator.py:L265`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/use_cases/chat/query_orchestrator.py#L265):
```python
            if self.pipeline_tracer:
                try:
                    tokens_data = res.get("tokens") if isinstance(res, dict) else None
                    tot_tok = tokens_data.get("total_tokens", 0) if isinstance(tokens_data, dict) else 0
                    self.pipeline_tracer.end_trace(
                        cache_hit=bool(res.get("cache_hit", False)) if isinstance(res, dict) else False,
                        total_tokens=tot_tok,
                        final_response=ans_text,
                    )
                except Exception as trace_err:
                    logger.warning("Failed to end pipeline trace for session %s: %s", session_id, trace_err)
```

- [ ] **Step 2: Attach query input metadata to stage contexts**

1. Normalization:
```python
        with self._stage_ctx(PipelineStage.NORMALIZATION, input_metadata={"raw_query": question}):
            normalized_result = self.query_normalizer.normalize(question)
```
2. Retrieval:
```python
        with self._stage_ctx(PipelineStage.VECTOR_RETRIEVAL, input_metadata={"query": retrieval_query}):
            selected_evidence = self._retrieve(retrieval_query, **retrieval_kwargs)
```
3. LLM Generation:
```python
        with self._stage_ctx(PipelineStage.LLM_GENERATION, input_metadata={"model": getattr(self.llm, "model_name", "unknown")}):
            answer = self._generate(messages, session_id=session_id)
```

- [ ] **Step 3: Run full orchestrator and tracing tests**

Run:
```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_orchestrator_memory_tracing.py tests\unit\test_langfuse_pipeline_trace_export.py -v
```
Expected: All 8 tests PASS.

---

### Task 6: Full Regression Verification

**Files:**
- Test: `tests/unit/test_orchestrator_memory_tracing.py`
- Test: `tests/unit/test_langfuse_pipeline_trace_export.py`
- Test: `tests/unit/test_observability_subsystem_e2e.py`
- Test: `tests/unit/test_orchestrator_access_gate.py`

- [ ] **Step 1: Execute full test suite**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_orchestrator_memory_tracing.py tests\unit\test_langfuse_pipeline_trace_export.py tests\unit\test_observability_subsystem_e2e.py tests\unit\test_orchestrator_access_gate.py -v
```
Expected: All 23 tests PASS.

- [ ] **Step 2: Verify Python syntax & compile**

```powershell
.\.venv\Scripts\python.exe -m compileall -q app tests
```
Expected: Exit code 0.
