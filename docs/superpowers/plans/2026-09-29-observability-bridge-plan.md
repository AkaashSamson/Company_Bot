# Observability Telemetry Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standardize LLM token parsing in `GroqClient` using `LLMTokenUsage` (Task AK-3.3) and bind `PipelineTracer` execution records to `ObservabilityManager.dispatch_trace()` via a boundary `to_token_usage` converter (Task AB-6.3), preserving bounded context separation, historical timestamps, and RAG telemetry hierarchy.

**Architecture:** Hexagonal telemetry bridge where `GroqClient` produces `LLMTokenUsage` (matching `OpenRouterClient`), keeping the LLM subsystem completely decoupled from observability. `PipelineTracer` records in-memory stage spans (`StageSpan`) and dispatches the completed turn (`PipelineTrace`) to `ObservabilityManager.dispatch_trace()`. `ObservabilityManager` provides a boundary converter `to_token_usage(usage_input)` translating `LLMTokenUsage` into frozen domain `TokenUsage` value objects before forwarding to active providers (Langfuse / Phoenix / Null).

**Tech Stack:** Python 3.11+, pytest, dataclasses, `app.domain.ports.observability`, `app.infrastructure.llm.llm_response`, `httpx`.

**Spec:** [`docs/superpowers/specs/2026-09-29-observability-telemetry-spec.md`](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/docs/superpowers/specs/2026-09-29-observability-telemetry-spec.md)

## Global Constraints

- Domain contracts in `app/domain/ports/observability.py` (`BaseObservabilityProvider`, `TokenUsage`, `TraceSpanPort`) remain frozen and vendor-neutral.
- `GroqClient` and `llm_response.py` must NOT import or depend on `app.domain.ports.observability` (preserving strict bounded context separation).
- `to_token_usage()` converter lives inside `ObservabilityManager` (`manager.py`) so the observer translates the observed system, not vice-versa.
- All telemetry dispatch operations must fail-safe: external network errors or missing credentials must never throw unhandled exceptions to callers.
- Unit and regression tests must execute 100% offline without requiring external network connectivity or API keys (`OBSERVABILITY_PROVIDER=null`).

## Review Focus

1. **Missing Usage in Groq Response:** When Groq API returns a payload without a `usage` block (or on error), both `res.tokens` and `GroqClient.get_last_token_usage()` must return `None` rather than raising `KeyError` or creating fake zero tokens.
2. **Missing Stage Timestamps:** If an aborted stage span lacks an explicit `end_time`, `ObservabilityManager.dispatch_trace()` must calculate duration gracefully from `span.duration_ms` without throwing `TypeError`.
3. **Empty Spans Array:** A `PipelineTrace` with zero spans (e.g. immediate early exit) must dispatch cleanly as an empty root trace without failing.
4. **Thread Safety During Dispatch:** `PipelineTracer.end_trace()` must dispatch completed traces safely under lock to prevent race conditions during high-concurrency requests.
5. **Disabled Tracing No-Op:** When `enable_tracing=False` on `PipelineTracer`, no dispatch call should occur and overhead must remain zero.

---

### Task 0: Feature Branch Setup

**Goal:** Isolate all changes for Subsystem 3 into a dedicated feature branch `feat/observability-bridge` branched from `p3-akaash`. Work will be committed incrementally on this branch and only merged back into `p3-akaash` upon passing all unit and end-to-end regression tests.

- [x] **Step 1: Check out isolated feature branch**
  ```powershell
  git checkout -b feat/observability-bridge
  ```
  Verify active branch:
  ```powershell
  git branch --show-current
  ```
  Expected: `feat/observability-bridge`

---

### Task 1: Groq Token Standardization to `LLMTokenUsage` (Task AK-3.3)

**Files:**
- Modify: `app/infrastructure/llm/groq_client.py:1-208`
- Test: `tests/unit/test_groq_token_standardization.py`

**Interfaces:**
- Consumes: `LLMTokenUsage` from `app.infrastructure.llm.llm_response`
- Produces: `GroqClient.get_last_token_usage() -> Optional[LLMTokenUsage]`, `res.tokens: Optional[LLMTokenUsage]`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_groq_token_standardization.py`:
```python
import pytest
from app.infrastructure.llm.llm_response import LLMTokenUsage
from app.infrastructure.llm.groq_client import GroqClient


def test_groq_client_populates_llm_token_usage_on_generate(monkeypatch):
    client = GroqClient(api_key="test-key", model="llama-3.3-70b-versatile")
    fake_response_data = {
        "choices": [{"message": {"content": "Test response"}}],
        "usage": {
            "prompt_tokens": 42,
            "completion_tokens": 18,
            "total_tokens": 60,
        },
    }

    class FakeResponse:
        status_code = 200
        is_error = False

        def json(self):
            return fake_response_data

    monkeypatch.setattr(client._client, "post", lambda *args, **kwargs: FakeResponse())

    content = client.generate([{"role": "user", "content": "Hello"}])
    assert content == "Test response"

    tokens = client.get_last_token_usage()
    assert tokens is not None
    assert isinstance(tokens, LLMTokenUsage)
    assert tokens.prompt_tokens == 42
    assert tokens.completion_tokens == 18
    assert tokens.total_tokens == 60


def test_groq_client_populates_llm_token_usage_on_generate_with_response(monkeypatch):
    client = GroqClient(api_key="test-key", model="llama-3.3-70b-versatile")
    fake_response_data = {
        "choices": [{"message": {"content": "Structured response"}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        },
    }

    class FakeResponse:
        status_code = 200
        is_error = False

        def json(self):
            return fake_response_data

    monkeypatch.setattr(client._client, "post", lambda *args, **kwargs: FakeResponse())

    res = client.generate_with_response([{"role": "user", "content": "Hello"}])
    assert res.content == "Structured response"

    # 1. Primary accessor: directly from LLMResponse object
    assert res.tokens is not None
    assert isinstance(res.tokens, LLMTokenUsage)
    assert res.tokens.prompt_tokens == 100
    assert res.tokens.completion_tokens == 50
    assert res.tokens.total_tokens == 150

    # 2. State accessor: client state is in sync with response
    assert client.get_last_token_usage() == res.tokens


def test_groq_client_returns_none_when_usage_missing(monkeypatch):
    client = GroqClient(api_key="test-key", model="llama-3.3-70b-versatile")
    fake_response_data = {
        "choices": [{"message": {"content": "Response without usage"}}],
    }

    class FakeResponse:
        status_code = 200
        is_error = False

        def json(self):
            return fake_response_data

    monkeypatch.setattr(client._client, "post", lambda *args, **kwargs: FakeResponse())

    # Test generate()
    client.generate([{"role": "user", "content": "Hello"}])
    assert client.get_last_token_usage() is None

    # Test generate_with_response()
    res = client.generate_with_response([{"role": "user", "content": "Hello"}])
    assert res.tokens is None
    assert client.get_last_token_usage() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_groq_token_standardization.py -v
```
Expected: FAIL with `AttributeError: 'GroqClient' object has no attribute 'get_last_token_usage'`

- [ ] **Step 3: Implement minimal code in `groq_client.py`**

In `app/infrastructure/llm/groq_client.py`:
1. Ensure `LLMTokenUsage` is imported from `app.infrastructure.llm.llm_response` (already on line 16).
2. In `__init__`:
   ```python
   self._last_token_usage: Optional[LLMTokenUsage] = None
   ```
3. In `generate()`:
   ```python
   usage = data.get("usage", {})
   if usage:
       prompt_tok = usage.get("prompt_tokens", 0)
       comp_tok = usage.get("completion_tokens", 0)
       tot_tok = usage.get("total_tokens", prompt_tok + comp_tok)
       self._last_tokens = {
           "prompt_tokens": prompt_tok,
           "completion_tokens": comp_tok,
           "total_tokens": tot_tok,
           "model": self.model,
       }
       self._last_token_usage = LLMTokenUsage(
           prompt_tokens=prompt_tok,
           completion_tokens=comp_tok,
           total_tokens=tot_tok,
       )
   else:
       self._last_tokens = None
       self._last_token_usage = None
   ```
4. In `generate_with_response()`:
   ```python
   usage = data.get("usage", {})
   if usage:
       tokens = LLMTokenUsage(
           prompt_tokens=usage.get("prompt_tokens", 0),
           completion_tokens=usage.get("completion_tokens", 0),
           total_tokens=usage.get("total_tokens", 0),
       )
       self._last_token_usage = tokens
       self._last_tokens = {
           "prompt_tokens": tokens.prompt_tokens,
           "completion_tokens": tokens.completion_tokens,
           "total_tokens": tokens.total_tokens,
           "model": self.model,
       }
   else:
       tokens = None
       self._last_token_usage = None
       self._last_tokens = None

   builder = (
       LLMResponseBuilder()
       .with_content(content)
       .with_status(LLMResponseStatus.SUCCESS)
       .with_provider(LLMProviderName.GROQ)
       .with_model(self.model)
       .with_latency(latency_ms)
   )
   if tokens is not None:
       builder = builder.with_tokens(tokens=tokens)

   return builder.build()
   ```
5. Add public accessor:
   ```python
   def get_last_token_usage(self) -> Optional[LLMTokenUsage]:
       """Get standardized LLMTokenUsage from the last generate call (Task AK-3.3)."""
       return self._last_token_usage
   ```

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_groq_token_standardization.py -v
```
Expected: PASS

- [ ] **Step 5: Run existing Groq and health unit tests**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_llm_provider.py tests/unit/test_client_health.py -v
```
Expected: All tests PASS

- [ ] **Step 6: Commit changes**

```bash
git add app/infrastructure/llm/groq_client.py tests/unit/test_groq_token_standardization.py
git commit -m "feat(llm): standardize Groq token parsing to LLMTokenUsage (AK-3.3)"
```

---

### Task 2: ObservabilityManager `to_token_usage` Adapter & `dispatch_trace` Implementation (Task AB-6.3 Part 1)

**Files:**
- Modify: `app/infrastructure/observability/manager.py`
- Test: `tests/unit/test_observability_manager_dispatch.py`

**Interfaces:**
- Produces:
  - `to_token_usage(usage_input: Any) -> Optional[TokenUsage]`
  - `ObservabilityManager.dispatch_trace(trace: PipelineTrace) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_observability_manager_dispatch.py`:
```python
import pytest
import time
from unittest.mock import MagicMock
from app.domain.ports.observability import TokenUsage
from app.infrastructure.llm.llm_response import LLMTokenUsage
from app.infrastructure.observability.manager import (
    ObservabilityManager,
    reset_observability_manager,
    to_token_usage,
)
from app.infrastructure.observability.pipeline_tracer import (
    PipelineTrace,
    PipelineStage,
    StageSpan,
)


@pytest.fixture(autouse=True)
def clean_manager():
    reset_observability_manager()
    yield
    reset_observability_manager()


def test_to_token_usage_converts_llm_token_usage():
    llm_tokens = LLMTokenUsage(prompt_tokens=50, completion_tokens=25, total_tokens=75)
    token_vo = to_token_usage(llm_tokens)
    assert isinstance(token_vo, TokenUsage)
    assert token_vo.prompt_tokens == 50
    assert token_vo.completion_tokens == 25
    assert token_vo.total_tokens == 75


def test_to_token_usage_converts_dict():
    raw_dict = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    token_vo = to_token_usage(raw_dict)
    assert isinstance(token_vo, TokenUsage)
    assert token_vo.total_tokens == 15


def test_to_token_usage_returns_none_for_none():
    assert to_token_usage(None) is None


def test_dispatch_trace_creates_root_trace_and_dispatches_spans():
    manager = ObservabilityManager()
    mock_provider = MagicMock()
    mock_span = MagicMock()
    mock_provider.create_trace.return_value = mock_span
    manager.set_provider(mock_provider)

    now = time.time()
    trace = PipelineTrace(
        trace_id="test-trace-123",
        query="What is 401k?",
        start_time=now,
    )
    span_retrieval = StageSpan(
        stage=PipelineStage.VECTOR_RETRIEVAL,
        start_time=now,
        end_time=now + 0.1,
        duration_ms=100.0,
        input_metadata={"query": "What is 401k?"},
        output_metadata={"chunks_count": 2},
    )
    span_llm = StageSpan(
        stage=PipelineStage.LLM_GENERATION,
        start_time=now + 0.1,
        end_time=now + 0.5,
        duration_ms=400.0,
        input_metadata={"model": "llama-3.3-70b-versatile"},
        output_metadata={"completion": "401k is retirement..."},
        prompt_tokens=40,
        completion_tokens=20,
        tokens_used=60,
    )
    trace.add_span(span_retrieval)
    trace.add_span(span_llm)
    trace.finish(total_tokens=60, cache_hit=False)

    manager.dispatch_trace(trace)

    # 1. Root trace created with correct metadata
    mock_provider.create_trace.assert_any_call(
        name="QueryOrchestrator.answer",
        session_id="test-trace-123",
        user_id=None,
        metadata={
            "query": "What is 401k?",
            "total_duration_ms": trace.total_duration_ms,
            "cache_hit": False,
            "early_exit": False,
            "exit_stage": None,
            "exit_reason": None,
            "total_tokens": 60,
        },
    )

    # 2. LLM call recorded using converted TokenUsage VO
    mock_provider.record_llm_call.assert_called_once_with(
        model="llama-3.3-70b-versatile",
        token_usage=TokenUsage(prompt_tokens=40, completion_tokens=20, total_tokens=60),
        latency_ms=400.0,
        metadata={"completion": "401k is retirement..."},
    )

    # 3. Provider flushed
    mock_provider.flush.assert_called_once()
    mock_span.end.assert_called_once()


def test_dispatch_trace_handles_missing_end_time_gracefully():
    manager = ObservabilityManager()
    mock_provider = MagicMock()
    mock_span = MagicMock()
    mock_provider.create_trace.return_value = mock_span
    manager.set_provider(mock_provider)

    trace = PipelineTrace(trace_id="test-incomplete", query="Q")
    # Incomplete span with end_time=None
    span = StageSpan(stage=PipelineStage.CACHE_LOOKUP, start_time=time.time(), end_time=None, duration_ms=5.0)
    trace.add_span(span)
    trace.finish()

    # Must execute cleanly without throwing TypeError
    manager.dispatch_trace(trace)
    mock_provider.create_trace.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_observability_manager_dispatch.py -v
```
Expected: FAIL with `ImportError: cannot import name 'to_token_usage' from 'app.infrastructure.observability.manager'`

- [ ] **Step 3: Implement `to_token_usage` and `dispatch_trace` in `manager.py`**

In `app/infrastructure/observability/manager.py`:
1. Add `to_token_usage` converter helper:
```python
def to_token_usage(usage_input: Any) -> Optional[TokenUsage]:
    """Boundary converter: safely translates LLMTokenUsage, dict, or TokenUsage into domain TokenUsage."""
    if usage_input is None:
        return None

    if isinstance(usage_input, TokenUsage):
        return usage_input

    # Duck-typed handling for LLMTokenUsage or any object with token attributes
    if hasattr(usage_input, "prompt_tokens"):
        p = getattr(usage_input, "prompt_tokens", 0)
        c = getattr(usage_input, "completion_tokens", 0)
        t = getattr(usage_input, "total_tokens", 0) or (p + c)
        return TokenUsage(prompt_tokens=p, completion_tokens=c, total_tokens=t)

    # Dict handling
    if isinstance(usage_input, dict):
        p = usage_input.get("prompt_tokens", 0)
        c = usage_input.get("completion_tokens", 0)
        t = usage_input.get("total_tokens", 0) or (p + c)
        return TokenUsage(prompt_tokens=p, completion_tokens=c, total_tokens=t)

    return None
```

2. Add `dispatch_trace` method on `ObservabilityManager`:
```python
    def dispatch_trace(self, trace: Any) -> None:
        """Dispatch a completed PipelineTrace execution record to the active observability provider.
        
        Binds root trace, individual stage spans, and LLM token usage (Task AB-6.3).
        Fails safe with logging: telemetry dispatch errors never raise exceptions to caller.
        """
        if trace is None:
            return

        try:
            with self._lock:
                provider = self._active_provider

            trace_metadata = {
                "query": getattr(trace, "query", ""),
                "total_duration_ms": getattr(trace, "total_duration_ms", 0.0),
                "cache_hit": getattr(trace, "cache_hit", False),
                "early_exit": getattr(trace, "early_exit", False),
                "exit_stage": getattr(trace.exit_stage, "value", None) if getattr(trace, "exit_stage", None) else None,
                "exit_reason": getattr(trace, "exit_reason", None),
                "total_tokens": getattr(trace, "total_tokens", 0),
            }

            session_id = getattr(trace, "trace_id", None)
            root_span = provider.create_trace(
                name="QueryOrchestrator.answer",
                session_id=session_id,
                user_id=getattr(trace, "metadata", {}).get("user_id"),
                metadata=trace_metadata,
            )

            # Process individual stage spans
            spans = getattr(trace, "spans", []) or []
            for span in spans:
                stage_val = getattr(span.stage, "value", str(span.stage)) if hasattr(span, "stage") else "unknown"

                # Calculate duration safely without TypeError if end_time is None
                start_t = getattr(span, "start_time", 0.0)
                end_t = getattr(span, "end_time", None)
                if end_t is not None and start_t:
                    duration_ms = (end_t - start_t) * 1000.0
                else:
                    duration_ms = getattr(span, "duration_ms", 0.0)

                if stage_val == "llm_generation":
                    # Check for explicit token object in metadata or span attributes
                    out_meta = getattr(span, "output_metadata", {}) or {}
                    raw_usage = out_meta.get("tokens") or out_meta.get("token_usage")
                    if raw_usage is None and (getattr(span, "prompt_tokens", 0) or getattr(span, "completion_tokens", 0)):
                        raw_usage = {
                            "prompt_tokens": getattr(span, "prompt_tokens", 0),
                            "completion_tokens": getattr(span, "completion_tokens", 0),
                            "total_tokens": getattr(span, "tokens_used", 0),
                        }

                    token_vo = to_token_usage(raw_usage)
                    if token_vo is not None:
                        model_name = getattr(span, "input_metadata", {}).get("model", "unknown")
                        provider.record_llm_call(
                            model=model_name,
                            token_usage=token_vo,
                            latency_ms=duration_ms,
                            metadata=out_meta,
                        )

            if root_span:
                output_payload = {"final_response": getattr(trace, "final_response", None)}
                root_span.end(outputs=output_payload)

            provider.flush()

        except Exception as exc:
            logger.warning("ObservabilityManager failed to dispatch trace %s: %s", getattr(trace, "trace_id", "unknown"), exc)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_observability_manager_dispatch.py -v
```
Expected: PASS

- [ ] **Step 5: Run full observability manager test suite**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_observability_manager.py -v
```
Expected: All tests PASS

- [ ] **Step 6: Commit changes**

```bash
git add app/infrastructure/observability/manager.py tests/unit/test_observability_manager_dispatch.py
git commit -m "feat(observability): add to_token_usage adapter and dispatch_trace to ObservabilityManager (AB-6.3)"
```

---

### Task 3: PipelineTracer Auto-Dispatch Wiring (Task AB-6.3 Part 2)

**Files:**
- Modify: `app/infrastructure/observability/pipeline_tracer.py:445-510`
- Test: `tests/unit/test_pipeline_tracer_dispatch_wiring.py`

**Interfaces:**
- Consumes: `get_observability_manager` from `app.infrastructure.observability.manager`
- Produces: Auto-dispatch on `PipelineTracer.end_trace()`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_pipeline_tracer_dispatch_wiring.py`:
```python
import pytest
from unittest.mock import MagicMock
from app.infrastructure.observability.pipeline_tracer import (
    PipelineTracer,
    PipelineStage,
    get_pipeline_tracer,
)
from app.infrastructure.observability.manager import (
    get_observability_manager,
    reset_observability_manager,
)


@pytest.fixture(autouse=True)
def clean_state():
    reset_observability_manager()
    tracer = get_pipeline_tracer()
    tracer._traces.clear()
    tracer._current_trace = None
    tracer._observability_callback = None
    yield
    reset_observability_manager()
    tracer._traces.clear()
    tracer._current_trace = None
    tracer._observability_callback = None


def test_end_trace_automatically_dispatches_to_observability_manager(monkeypatch):
    manager = get_observability_manager()
    mock_dispatch = MagicMock()
    monkeypatch.setattr(manager, "dispatch_trace", mock_dispatch)

    tracer = get_pipeline_tracer()
    tracer.enable_tracing = True

    trace = tracer.start_trace(query="Test query", trace_id="trace-auto-1")
    tracer.end_trace(trace_id="trace-auto-1", cache_hit=True, total_tokens=0)

    mock_dispatch.assert_called_once()
    dispatched_trace = mock_dispatch.call_args[0][0]
    assert dispatched_trace.trace_id == "trace-auto-1"
    assert dispatched_trace.query == "Test query"
    assert dispatched_trace.cache_hit is True


def test_custom_observability_callback_takes_precedence_if_set():
    tracer = get_pipeline_tracer()
    tracer.enable_tracing = True
    custom_cb = MagicMock()
    tracer.set_observability_callback(custom_cb)

    trace = tracer.start_trace(query="Callback query", trace_id="trace-cb-1")
    tracer.end_trace(trace_id="trace-cb-1")

    custom_cb.assert_called_once()


def test_disabled_tracing_does_not_dispatch(monkeypatch):
    manager = get_observability_manager()
    mock_dispatch = MagicMock()
    monkeypatch.setattr(manager, "dispatch_trace", mock_dispatch)

    tracer = get_pipeline_tracer()
    tracer.enable_tracing = False

    trace = tracer.start_trace(query="Disabled query", trace_id="trace-disabled-1")
    assert trace is None
    ended = tracer.end_trace(trace_id="trace-disabled-1")
    assert ended is None

    mock_dispatch.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_pipeline_tracer_dispatch_wiring.py -v
```
Expected: FAIL (mock_dispatch not called because auto-dispatch not wired in `end_trace()`).

- [ ] **Step 3: Update `end_trace()` in `pipeline_tracer.py`**

In `app/infrastructure/observability/pipeline_tracer.py`, update `end_trace()` around lines 490-496:
```python
            # Call observability callback or auto-dispatch to ObservabilityManager
            if self._observability_callback:
                try:
                    self._observability_callback(trace)
                except Exception as e:
                    logger.error("observability_callback_failed error=%s", e)
            else:
                try:
                    from app.infrastructure.observability.manager import get_observability_manager
                    get_observability_manager().dispatch_trace(trace)
                except Exception as e:
                    logger.warning("observability_autodispatch_failed error=%s", e)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_pipeline_tracer_dispatch_wiring.py -v
```
Expected: PASS

- [ ] **Step 5: Run existing pipeline tracer tests**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_pipeline_tracing.py -v
```
Expected: All tests PASS

- [ ] **Step 6: Commit changes**

```bash
git add app/infrastructure/observability/pipeline_tracer.py tests/unit/test_pipeline_tracer_dispatch_wiring.py
git commit -m "feat(observability): wire PipelineTracer auto-dispatch to ObservabilityManager (AB-6.3)"
```

---

### Task 4: Subsystem 3 Full End-to-End Integration Test & Verification

**Files:**
- Create: `tests/unit/test_observability_subsystem_e2e.py`

**Interfaces:**
- Verifies the full pipeline flow: `GroqClient` token generation (`LLMTokenUsage`) $\rightarrow$ `PipelineTracer` execution recording $\rightarrow$ `ObservabilityManager.dispatch_trace()` boundary conversion (`TokenUsage`) $\rightarrow$ active provider.

- [ ] **Step 1: Write the end-to-end integration test**

Create `tests/unit/test_observability_subsystem_e2e.py`:
```python
import pytest
from unittest.mock import MagicMock
from app.domain.ports.observability import TokenUsage
from app.infrastructure.llm.groq_client import GroqClient
from app.infrastructure.llm.llm_response import LLMTokenUsage
from app.infrastructure.observability.pipeline_tracer import (
    get_pipeline_tracer,
    PipelineStage,
)
from app.infrastructure.observability.manager import (
    get_observability_manager,
    reset_observability_manager,
)


@pytest.fixture(autouse=True)
def reset_singletons():
    reset_observability_manager()
    tracer = get_pipeline_tracer()
    tracer._traces.clear()
    tracer._current_trace = None
    tracer._observability_callback = None
    yield
    reset_observability_manager()
    tracer._traces.clear()
    tracer._current_trace = None
    tracer._observability_callback = None


def test_full_observability_subsystem_turn_lifecycle(monkeypatch):
    # 1. Setup mock observability backend
    manager = get_observability_manager()
    mock_provider = MagicMock()
    mock_root_span = MagicMock()
    mock_provider.create_trace.return_value = mock_root_span
    manager.set_provider(mock_provider)

    tracer = get_pipeline_tracer()

    # 2. Simulate Groq client call producing LLMTokenUsage
    groq = GroqClient(api_key="test-key", model="llama-3.3-70b-versatile")
    fake_response_data = {
        "choices": [{"message": {"content": "Vacation policy details."}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160},
    }

    class FakeResponse:
        status_code = 200
        is_error = False

        def json(self):
            return fake_response_data

    monkeypatch.setattr(groq._client, "post", lambda *args, **kwargs: FakeResponse())
    llm_res = groq.generate_with_response([{"role": "user", "content": "How much vacation do I get?"}])
    assert llm_res.tokens is not None
    assert isinstance(llm_res.tokens, LLMTokenUsage)
    assert llm_res.tokens.total_tokens == 160
    assert groq.get_last_token_usage() == llm_res.tokens

    # 3. Simulate multi-stage pipeline trace
    trace = tracer.start_trace(query="How much vacation do I get?", trace_id="turn-e2e-999")

    # Stage: Normalization
    with tracer.trace_stage(PipelineStage.NORMALIZATION) as s:
        if s:
            s.output_metadata = {"normalized_query": "how much vacation do i get", "cache_key": "vacation_policy"}

    # Stage: Retrieval
    with tracer.trace_stage(PipelineStage.VECTOR_RETRIEVAL) as s:
        if s:
            s.output_metadata = {
                "chunks_count": 1,
                "chunks": [{"source": "HR_Policy.pdf", "score": 0.22, "snippet": "Employees receive 20 days..."}],
            }

    # Stage: LLM Generation
    with tracer.trace_stage(PipelineStage.LLM_GENERATION, input_metadata={"model": groq.model}) as s:
        if s:
            s.record_tokens(llm_res.tokens.prompt_tokens, llm_res.tokens.completion_tokens)
            s.output_metadata = {"completion": llm_res.content, "tokens": llm_res.tokens}

    # 4. Finish turn (triggers auto-dispatch to ObservabilityManager)
    tracer.end_trace(trace_id="turn-e2e-999", total_tokens=llm_res.tokens.total_tokens)

    # 5. Verify ObservabilityManager converted LLMTokenUsage -> TokenUsage and forwarded
    mock_provider.create_trace.assert_called_once_with(
        name="QueryOrchestrator.answer",
        session_id="turn-e2e-999",
        user_id=None,
        metadata={
            "query": "How much vacation do I get?",
            "total_duration_ms": trace.total_duration_ms,
            "cache_hit": False,
            "early_exit": False,
            "exit_stage": None,
            "exit_reason": None,
            "total_tokens": 160,
        },
    )

    mock_provider.record_llm_call.assert_called_once_with(
        model="llama-3.3-70b-versatile",
        token_usage=TokenUsage(prompt_tokens=120, completion_tokens=40, total_tokens=160),
        latency_ms=pytest.approx(trace.get_stage_duration(PipelineStage.LLM_GENERATION), rel=0.1),
        metadata={"completion": "Vacation policy details.", "tokens": llm_res.tokens},
    )

    mock_provider.flush.assert_called_once()
    mock_root_span.end.assert_called_once()
```

- [ ] **Step 2: Run the end-to-end integration test**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_observability_subsystem_e2e.py -v
```
Expected: PASS

- [ ] **Step 3: Run comprehensive test suite across observability and LLM modules**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_observability.py tests/unit/test_observability_manager.py tests/unit/test_pipeline_tracing.py tests/unit/test_groq_token_standardization.py tests/unit/test_observability_manager_dispatch.py tests/unit/test_pipeline_tracer_dispatch_wiring.py tests/unit/test_observability_subsystem_e2e.py -v
```
Expected: All tests PASS with zero regressions

- [ ] **Step 4: Update `Task_Timeline.md` status**

In `Documentation/Plan/v3/Task_Timeline.md`:
Mark tasks complete:
- `- [x] **Task AK-3.3 (Groq Token Standardization - Akaash Samson):** ...`
- `- [x] **Task AB-6.3 (Pipeline Tracer Dispatch Hook - Abhinav):** ...`

- [ ] **Step 5: Commit complete subsystem on feature branch**

```bash
git add tests/unit/test_observability_subsystem_e2e.py Documentation/Plan/v3/Task_Timeline.md
git commit -m "feat(observability): complete Subsystem 3 Observability Bridge (AK-3.3, AB-6.3)"
```

- [ ] **Step 6: Switch back to `p3-akaash` and merge `feat/observability-bridge`**

Run:
```powershell
git checkout p3-akaash
git merge --no-ff feat/observability-bridge -m "feat(observability): merge Subsystem 3 Observability Bridge into p3-akaash"
```

- [ ] **Step 7: Run full regression test suite on `p3-akaash`**

Run:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_observability.py tests/unit/test_observability_manager.py tests/unit/test_pipeline_tracing.py tests/unit/test_groq_token_standardization.py tests/unit/test_observability_manager_dispatch.py tests/unit/test_pipeline_tracer_dispatch_wiring.py tests/unit/test_observability_subsystem_e2e.py -v
```
Expected: All tests PASS with zero regressions on `p3-akaash`.
