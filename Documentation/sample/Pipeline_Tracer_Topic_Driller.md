# Topic Driller: Pipeline Tracer (`pipeline_tracer.py`)

> **File Reference:** [`pipeline_tracer.py`](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/observability/pipeline_tracer.py)  
> **Task Baseline:** `AB-6.1` (Pipeline Tracing Engine) & `AB-6.3` (Observability Bridge)  
> **Status:** Completed, 26/26 Unit Tests Passing  
> **Execution Location:** `Documentation/sample/Pipeline_Tracer_Topic_Driller.md`

---

## 1. The Core Engineering Problem: Why Build an In-Tree Tracer?

In production AI & RAG systems, teams often default to external APMs (Datadog, OpenTelemetry, LangSmith, Langfuse). However, that introduces three fatal dependencies:

```text
+-----------------------------------------------------------------------------+
|                     WHY EXTERNAL-ONLY TRACING BREAKS DOWN                   |
|                                                                             |
| 1. SaaS Vendor Lock-In & Outages:                                           |
|    If LangSmith or Langfuse has an API outage, an unhandled tracing error    |
|    can crash the primary chat request, or block user queries with timeouts. |
|                                                                             |
| 2. Development & Air-Gapped Environments:                                   |
|    Local developers and air-gapped enterprise deployments cannot export     |
|    traces to external cloud endpoints.                                      |
|                                                                             |
| 3. Domain-Specific RAG Semantics:                                           |
|    Generic APMs track HTTP endpoints and database queries, but know nothing  |
|    about RAG concepts: "Cache Hit vs Miss", "Early Negative Cutoff",        |
|    "Quality Gate Rejections", or "Chunk Reranking Latency".                 |
+-----------------------------------------------------------------------------+
```

### The Solution
`pipeline_tracer.py` is an **in-tree, zero-dependency, thread-safe tracing engine** that records microsecond execution spans and token metrics across **8 canonical pipeline stages**. It provides immediate local observability while acting as the staging buffer for external exporters via `set_observability_callback()`.

---

## 2. The 8 Canonical Pipeline Stages

The pipeline models a query's lifecycle through a discrete state machine defined in `PipelineStage`:

```text
========================================================================================
THE 8 CANONICAL PIPELINE STAGES (Task AB-6.1)
========================================================================================

 1. [CONTEXT_REWRITE]   Resolves multi-turn conversational pronouns ("it", "that policy")
           |
           v
 2. [NORMALIZATION]     Unicode NFKD, whitespace stripping, corporate typo correction
           |
           v
 3. [CACHE_LOOKUP]      Semantic cache & FAQ exact/similarity checks (<5ms fast path)
           |             └─> [EARLY EXIT on Cache Hit]
           v
 4. [VECTOR_RETRIEVAL]  ChromaDB cosine embedding search (fetches top-K candidates)
           |
           v
 5. [RERANKING]         Cross-Encoder deep semantic candidate filtering (top-15 -> top-4)
           |
           v
 6. [QUALITY_GATE]      Multi-signal evaluation: Lexical grounding, separation gap
           |             └─> [EARLY EXIT if evidence is INVALID]
           v
 7. [LLM_GENERATION]    Dispatch to Groq / OpenRouter with token consumption
           |
           v
 8. [POST_GUARDRAILS]   Negative answer detection, citation cleaning, cache write
```

---

## 3. Structural Object Hierarchy (ASCII Diagram)

The tracing system is built on a 4-tier object hierarchy:

```text
+-----------------------------------------------------------------------------+
|                               PipelineTracer                                |
|  - Process-wide Singleton (_instance, _lock)                                |
|  - Holds active trace dict: _traces: dict[str, PipelineTrace] (max 1000)     |
|  - Observability callback dispatch: _observability_callback                 |
+-----------------------------------------------------------------------------+
                                       |
                               Manages / Owns
                                       v
+-----------------------------------------------------------------------------+
|                                PipelineTrace                                |
|  - trace_id: UUID                                                           |
|  - query: Original user prompt                                              |
|  - total_duration_ms: (end_time - start_time) * 1000                        |
|  - cache_hit: bool, early_exit: bool, exit_stage: Optional[PipelineStage]   |
|  - spans: list[StageSpan]                                                   |
+-----------------------------------------------------------------------------+
                                       |
                             Aggregates Spans
                                       v
+-----------------------------------------------------------------------------+
|                                  StageSpan                                  |
|  - stage: PipelineStage (e.g., VECTOR_RETRIEVAL)                            |
|  - start_time / end_time: float (time.time())                               |
|  - duration_ms: float                                                       |
|  - prompt_tokens / completion_tokens / tokens_used: int                     |
|  - input_metadata / output_metadata: dict[str, Any]                         |
|  - error: Optional[str]                                                     |
+-----------------------------------------------------------------------------+
                                       ^
                           Instrumented / Managed By
                                       |
+-----------------------------------------------------------------------------+
|                                TraceContext                                 |
|  - Python Context Manager (__enter__ / __exit__)                            |
|  - Automatically captures unhandled exceptions into span.error              |
|  - Exposes record_tokens() and set_output() to active stage code            |
+-----------------------------------------------------------------------------+
```

---

## 4. Deep Dissection of Core Components

### Component 1: `TraceContext` (Context Manager Engine)

`TraceContext` allows engineers to wrap any code block cleanly without polluting business logic:

```python
with TraceContext(stage=PipelineStage.VECTOR_RETRIEVAL) as ctx:
    results = retrieve(query)
    ctx.set_output(candidates_found=len(results))
```

#### How `__exit__` Handles Errors:
```python
def __exit__(self, exc_type, exc_val, exc_tb) -> None:
    self.end_time = time.time()
    self.duration_ms = (self.end_time - self.start_time) * 1000.0

    if exc_val is not None:
        self.error = str(exc_val)
        if self.span:
            self.span.error = self.error
        logger.warning("pipeline_stage_error stage=%s error=%s", self.stage.value, exc_val)

    if self.span:
        self.span.finish(output_metadata=self.output_metadata)

    return False  # Critical: Never swallow the exception!
```
* **Why `return False`?** Tracing is an observer, not an exception handler. Returning `False` allows Python to re-raise the exception up the call stack to the orchestrator's outage fallback mechanism.

---

### Component 2: `PipelineTrace` (Aggregate Lifecycle Record)

`PipelineTrace` represents the complete end-to-end journey of a single query.

* **Token Aggregation:** When `finish()` is invoked, it dynamically computes:
  ```python
  self.total_tokens = sum(s.tokens_used for s in self.spans)
  ```
* **Early Exit Tracking:** If the pipeline aborts early (e.g., Cache Hit at stage 3, or `INVALID` evidence at stage 6), the trace explicitly records:
  ```python
  trace.finish(early_exit=True, exit_stage=PipelineStage.QUALITY_GATE, exit_reason="insufficient_grounding")
  ```
  This distinguishes successful early terminations from pipeline crashes.

---

### Component 3: `PipelineTracer` (Global Coordinator & Memory Pruning)

`PipelineTracer` acts as the process-wide singleton (`get_pipeline_tracer()`).

#### Thread Safety:
It employs a re-entrant lock (`threading.RLock()`) to serialize access to the internal dictionary `_traces`. Even under 50 concurrent requests, span insertion and trace completion remain race-condition free.

#### Bounded In-Memory Ring Buffer (`_cleanup_old_traces`):
To prevent an unbounded memory leak on high-traffic servers, `PipelineTracer` caps stored traces at `max_traces` (default: 1000):

```text
[Incoming Trace #1001]
          |
          v
+-----------------------------------------------------------------------------+
| Check: len(_traces) > max_traces (1000)?                                    |
|                                                                             |
| 1. Sort existing traces by start_time ascending (oldest first).             |
| 2. Bulk delete oldest 100 traces (batch purge buffer).                      |
| 3. Prevent repeated O(N log N) sorting on every subsequent trace insert!    |
+-----------------------------------------------------------------------------+
```

---

## 5. Phase 3 & 4 Handshake: The Observability Bridge

In **Phase 3, Subsystem 3 (Task AB-6.3)**, this hook connects Abhinav's `PipelineTracer` directly to Akaash's `ObservabilityManager`:

```text
+-------------------------+             +------------------------------+
|     PipelineTracer      |             |     ObservabilityManager     |
|   (Abhinav - AB-6.1)    |             |      (Akaash - AK-3.2)       |
+-------------------------+             +------------------------------+
             |                                         |
             | trace.finish()                          |
             v                                         |
    [Invoke Callback] -------------------------------> | Dispatches to:
                                                       | - Langfuse REST API
                                                       | - LangSmith Tracing
                                                       | - Prometheus / Grafana
```

---

## 6. The 5 "What-If" Failure Drills

| Failure Scenario | Behavior of `pipeline_tracer.py` | Severity | Safety Mechanism |
| :--- | :--- | :---: | :--- |
| **Stage throws an unhandled exception (e.g. ChromaDB timeout)** | Caught in `TraceContext.__exit__`. Stores error string in `span.error`, marks `duration_ms`, re-raises exception (`return False`). | **Zero Impact** | Exception propagates cleanly to caller; telemetry is preserved. |
| **Observability exporter (Langfuse) crashes during callback** | Caught in `try...except` inside `end_trace()`. Logs error; trace completes normally. | **Zero Impact** | Primary user chat flow is never blocked by telemetry export crashes. |
| **Tracing is disabled in `.env` (`ENABLE_PIPELINE_TRACING=false`)** | `start_trace()` returns `None`. `trace_stage()` yields `None` immediately. | **Zero Overhead** | Near-zero CPU overhead; zero memory allocated. |
| **Server handles 100,000 queries over 24 hours** | `_cleanup_old_traces()` prunes old traces in batches of 100 once `len > 1000`. | **Zero Leak** | Memory bounded to fixed footprint. |
| **Multiple worker threads record tokens simultaneously** | Protected by `self._lock` (`RLock`) in `record_tokens()` and `add_span()`. | **Zero Race** | In-process thread-safe. |

---

## 7. Interactive Experiment: Run a Synthetic Pipeline Trace

To inspect a live trace and verify span metrics, execute this in `.venv`:

```python
from app.infrastructure.observability.pipeline_tracer import (
    get_pipeline_tracer,
    PipelineStage,
    TraceContext
)

tracer = get_pipeline_tracer()

# 1. Start a top-level trace
trace = tracer.start_trace(query="What is the maternity leave entitlement?")

# 2. Simulate Stage 2: Normalization
with TraceContext(stage=PipelineStage.NORMALIZATION, tracer=tracer) as ctx:
    # simulated NLP work
    ctx.set_output(normalized_query="maternity leave entitlement")

# 3. Simulate Stage 7: LLM Generation with token recording
with TraceContext(stage=PipelineStage.LLM_GENERATION, tracer=tracer) as ctx:
    ctx.record_tokens(prompt_tokens=420, completion_tokens=85)
    ctx.set_output(model="llama-3.1-8b-instant")

# 4. End the trace
completed_trace = tracer.end_trace(total_tokens=505)

# Inspect outputs
print("Trace ID:", completed_trace.trace_id)
print("Total Duration:", f"{completed_trace.total_duration_ms:.2f}ms")
print("Total Tokens:", completed_trace.total_tokens)
for span in completed_trace.spans:
    print(f" -> Stage: {span.stage.value:<20} Duration: {span.duration_ms:.2f}ms Tokens: {span.tokens_used}")
```

---

## 8. Summary Checklist for Phase 3 Readiness

- [x] **8 Canonical Stages Modeled:** Standardized across all team components.
- [x] **Context Manager Usability:** `with TraceContext(...)` captures timings and errors automatically.
- [x] **Zero Dependencies:** Pure standard library (`dataclasses`, `time`, `threading`, `contextlib`).
- [x] **Bounded Memory:** Auto-pruning ring buffer prevents leaks.
- [x] **Phase 3 Hook Ready:** `set_observability_callback()` is pre-wired to handshake with Akaash's `ObservabilityManager`.
