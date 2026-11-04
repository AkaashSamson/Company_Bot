# Observability Architecture & Implementation Guide (V3)

**Author:** Akaash Samson  
**Module:** `app.infrastructure.observability` & `app.domain.ports.observability`  
**Tasks Implemented:** Task AK-3.1 (Phase 1), Task AK-3.2 (Phase 2), Task AK-3.4 (Phase 3 Subsystem 3)  
**Target Audience:** Core Pipeline Contributors (Akaash, Abhinav, Neha, Roshan)

---

## 1. Executive Summary & Problem Context

### The Problem in V2
In V2, application observability suffered from tight coupling and vendor lock-in:
1. `QueryOrchestrator` directly imported concrete LangSmith helpers (`from app.infrastructure.observability.langsmith_integration import add_tokens_to_current_run`).
2. Hardcoded `@traceable` decorators directly imported from `langsmith` were scattered across pipeline methods.
3. If LangSmith credentials were absent or telemetry failed, execution either emitted warning noise or failed to capture metrics.
4. Switching to alternative observability platforms (e.g., self-hosted Langfuse, Arize Phoenix, or offline local logging) was impossible without modifying business logic.

### The V3 Solution: Hexagonal Observability
V3 introduces a strict **Ports and Adapters** (Hexagonal) architecture:
- **Domain Port:** [app/domain/ports/observability.py](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/domain/ports/observability.py) defines standard vendor-neutral abstractions (`BaseObservabilityProvider`, `TraceSpanPort`, `TokenUsage`).
- **Concrete Adapters:** Fully decoupled infrastructure providers ([LangfuseProvider](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/langfuse_provider.py), [PhoenixProvider](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/phoenix_provider.py), [NullObservabilityProvider](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/null_provider.py)).
- **Routing & Singleton:** [ObservabilityManager](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/manager.py) manages dynamic runtime switching and provides a process-wide singleton (`get_observability_manager()`).
- **Zero Caller Coupling:** Callers (`QueryOrchestrator`, `PipelineTracer`) import only the domain port or manager. Telemetry backends can be switched on the fly via `.env` or API with **zero code changes** in business logic.

---

## 2. Architecture & Component Interaction

```
┌────────────────────────────────────────────────────────────────────────┐
│                        CALLER LAYER (Use Cases)                        │
│   QueryOrchestrator.answer()  /  PipelineTracer (Task AB-6.1)          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Calls create_trace() & record_llm_call()
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       DOMAIN PORT (Contracts)                          │
│   [BaseObservabilityProvider Protocol]  ── uses ──> [TokenUsage VO]   │
│   [TraceSpanPort Protocol]                                            │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Implements
┌───────────────────────────────────┴────────────────────────────────────┐
│                    INFRASTRUCTURE LAYER (Adapters)                     │
│                                                                        │
│                      [ObservabilityManager]                            │
│                 (Central Facade, Router & Singleton)                   │
│                                   │                                    │
│          ┌────────────────────────┼────────────────────────┐           │
│          ▼                        ▼                        ▼           │
│  [LangfuseProvider]       [PhoenixProvider]      [NullProvider]        │
│  - Langfuse SDK v4        - OpenTelemetry SDK    - Zero Network Calls  │
│  - REST Ingestion         - OpenInference Attrs  - Safe Unit Tests     │
│  - Cloud & Self-Hosted    - Port 6006 Collector  - Offline Fast-Path   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Domain Contracts (Task AK-3.1)

Located in [app/domain/ports/observability.py](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/domain/ports/observability.py):

### 3.1 `TokenUsage` (Frozen Value Object)
A vendor-agnostic container for token consumption metrics.
```python
@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if self.total_tokens == 0 and (self.prompt_tokens > 0 or self.completion_tokens > 0):
            object.__setattr__(self, "total_tokens", self.prompt_tokens + self.completion_tokens)
```
* **Immutability:** `frozen=True` ensures token counts cannot be mutated once recorded.
* **Auto-Calculation:** Automatically calculates `total_tokens` if omitted.

### 3.2 `TraceSpanPort` (Context Manager Protocol)
```python
@runtime_checkable
class TraceSpanPort(Protocol):
    def end(self, outputs: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None: ...
    def __enter__(self) -> "TraceSpanPort": ...
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...
```

### 3.3 `BaseObservabilityProvider` / `ObservabilityPort`
```python
@runtime_checkable
class BaseObservabilityProvider(Protocol):
    def create_trace(
        self,
        name: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TraceSpanPort: ...

    def record_llm_call(
        self,
        model: str,
        token_usage: TokenUsage,
        latency_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None: ...

    def flush(self) -> None: ...
```

---

## 4. Concrete Infrastructure Implementations (Task AK-3.2 & AK-3.4)

### 4.1 `LangfuseProvider` ([app/infrastructure/observability/langfuse_provider.py](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/langfuse_provider.py))
Built following the official [Langfuse AI Skill](https://github.com/langfuse/skills) best practices:
1. **SDK v4 Integration:** Uses official `langfuse.Langfuse` client (`langfuse>=4.15.0`).
2. **Canonical Observation Types:** Automatically infers observation types (`as_type`):
   - Vector Search / ChromaDB $\rightarrow$ `as_type="retriever"`
   - LLM Generation $\rightarrow$ `as_type="generation"`
   - Guardrails & Safety $\rightarrow$ `as_type="guardrail"`
   - Intermediate Steps $\rightarrow$ `as_type="span"`
3. **Conversational Context:** Injects `session_id` and `user_id` so traces group naturally into conversations in the Langfuse Sessions UI.
4. **Token Usage Structure:** Passes tokens via `usage_details={"input": prompt, "output": completion, "total": total}`.
5. **Robust Credential Parsing:** Strips quotes and whitespace from `.env` strings (e.g. `"https://jp.cloud.langfuse.com"` $\rightarrow$ `https://jp.cloud.langfuse.com`). Supports both `LANGFUSE_BASE_URL` and `LANGFUSE_HOST`.
6. **Fail-Safe Resilience:** Catches network timeouts and connection errors; logs warnings without crashing caller execution.

### 4.2 `PhoenixProvider` ([app/infrastructure/observability/phoenix_provider.py](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/phoenix_provider.py))
1. Native integration for Arize Phoenix (`http://localhost:6006`).
2. Adheres to OpenInference semantic attributes:
   - `llm.model_name`
   - `llm.token_count.prompt`, `llm.token_count.completion`, `llm.token_count.total`
   - `llm.latency_ms`
3. Maintains lifetime counters (`total_spans_recorded`, `total_llm_calls_recorded`) and flushed history buffers for test validation.

### 4.3 `ObservabilityManager` ([app/infrastructure/observability/manager.py](file:///c:/DEV/Training_Projects/Training_Team_Project/Company_Bot/app/infrastructure/observability/manager.py))
Acts as the central router and implements `BaseObservabilityProvider`:
- **Default Resolution:** Reads `settings.OBSERVABILITY_PROVIDER` (`"null"`, `"langfuse"`, `"phoenix"`).
- **Dynamic Switching:** `manager.switch_provider("langfuse")` or `manager.set_provider(custom_provider)`.
- **Process Singleton (Task AK-3.4):** `get_observability_manager()` provides thread-safe singleton access across all application modules.
- **Test Reset:** `reset_observability_manager()` allows fixtures to clear singleton state between tests.

---

## 5. How Future Tasks Build on This Foundation

### 5.1 Task AB-6.1 & AB-6.3: Pipeline Tracing Engine (Owner: Abhinav)
* **What Abhinav Builds:** `app/infrastructure/observability/pipeline_tracer.py`.
* **What Abhinav Consumes:**
  ```python
  from app.domain.ports.observability import TokenUsage
  from app.infrastructure.observability.manager import get_observability_manager

  class PipelineTracer:
      def __init__(self, session_id: str = None, user_id: str = None):
          # Acquire the active provider from Akaash's singleton
          self.provider = get_observability_manager()
          self.session_id = session_id
          self.user_id = user_id

      def trace_stage(self, stage: PipelineStage):
          # Opens span via active provider (Langfuse / Phoenix / Null)
          return self.provider.create_trace(
              name=f"stage:{stage.value}",
              session_id=self.session_id,
              user_id=self.user_id
          )
  ```
* **The 8 Pipeline Stages to Trace:**
  1. `CONTEXT_REWRITE`: LLM pronoun resolution latency.
  2. `NORMALIZATION`: Query cleaning and typo fix latency.
  3. `CACHE_LOOKUP`: Cache hit/miss evaluation.
  4. `VECTOR_RETRIEVAL`: ChromaDB nearest-neighbor lookup.
  5. `RERANKING`: Cross-encoder scoring latency.
  6. `QUALITY_GATE`: Grounding & confidence evaluation.
  7. `LLM_GENERATION`: Primary LLM completion and token recording.
  8. `POST_GUARDRAILS`: Output safety and citation check.

### 5.2 Task AK-3.3: Groq Token Standardization (Owner: Akaash)
* **Target File:** `app/infrastructure/llm/groq_client.py`.
* **What to Implement:** Parse standard OpenAI-compatible usage object returned by Groq API:
  ```python
  from app.domain.ports.observability import TokenUsage

  usage_data = raw_response.get("usage", {})
  token_usage = TokenUsage(
      prompt_tokens=usage_data.get("prompt_tokens", 0),
      completion_tokens=usage_data.get("completion_tokens", 0),
      total_tokens=usage_data.get("total_tokens", 0),
  )
  ```

### 5.3 Task AB-4.2: Semantic Cache Tracing (Owner: Abhinav)
* **Target File:** `app/use_cases/chat/query_orchestrator.py` & cache module.
* **Telemetry Contract:**
  - **On Cache Hit:** Mark `stage:cache_lookup` with `output={"cache_hit": True}`. Return immediately. Downstream stages are skipped. Trace completes with **0 LLM tokens** and **<10ms latency**.
  - **On Cache Miss:** Mark `stage:cache_lookup` with `output={"cache_hit": False}`. Continue to vector retrieval and LLM generation. Trace records full latency and token counts.

### 5.4 Phase 4 Hot File Gate: `query_orchestrator.py` (Owner: Abhinav & Akaash)
During Phase 4, the existing legacy lines in `query_orchestrator.py` must be upgraded:

| Legacy Line in `query_orchestrator.py` | Legacy Implementation | V3 Target Implementation |
| :--- | :--- | :--- |
| Line 14 | `from app.infrastructure.observability.tracer import traceable` | `from app.infrastructure.observability.pipeline_tracer import PipelineTracer, PipelineStage` |
| Line 20 | `from app.infrastructure.observability.langsmith_integration import add_tokens_to_current_run` | **DELETE** (Tokens dispatched via `PipelineTracer.record_llm_call`) |
| Line 159 | `@traceable(name="QueryOrchestrator.answer", run_type="chain")` | Managed via `tracer = PipelineTracer(session_id, user_id)` |
| Line 438 | `@traceable(name="FAQSimilarityCache.search", run_type="retriever")` | `with tracer.trace_stage(PipelineStage.CACHE_LOOKUP):` |
| Line 444 | `@traceable(name="RAGRetrieval", run_type="retriever")` | `with tracer.trace_stage(PipelineStage.VECTOR_RETRIEVAL):` |
| Line 450 | `@traceable(name="LLMGenerate", run_type="llm")` | `with tracer.trace_stage(PipelineStage.LLM_GENERATION):` |
| Lines 382-391 | `add_tokens_to_current_run(...)` | `tracer.record_llm_call(model, token_usage)` |

---

## 6. Environment & Configuration Reference

Configure telemetry in `.env`:

```ini
# Observability Backend: "null" (default/testing), "langfuse", or "phoenix"
OBSERVABILITY_PROVIDER=langfuse

# Langfuse Configuration (Cloud or Self-Hosted)
LANGFUSE_PUBLIC_KEY="pk-lf-..."
LANGFUSE_SECRET_KEY="sk-lf-..."
LANGFUSE_BASE_URL="https://jp.cloud.langfuse.com" # or "http://localhost:3000"

# Arize Phoenix Configuration
PHOENIX_COLLECTOR_ENDPOINT="http://localhost:6006/v1/traces"
PHOENIX_PROJECT_NAME="company-bot"
```

---

## 7. Verification & Quality Assurance

Run the test suite on branch `p1-akaash`:
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_session_memory_service.py tests/unit/test_observability.py tests/unit/test_observability_manager.py
```

### Coverage Assurances:
1. **Contract Adherence:** Verified that all providers implement `BaseObservabilityProvider` and `TraceSpanPort`.
2. **Pluggability:** Verified runtime switching between `NullObservabilityProvider`, `LangfuseProvider`, and `PhoenixProvider` without restarting Python interpreter.
3. **Fail-Safe Execution:** Verified that unreachable servers (connection refused, timeouts) produce clean logger warnings and **never raise unhandled exceptions** to the caller.
4. **Test Isolation:** Automatic pytest fixture `clean_manager_singleton` guarantees zero state leakage between tests.
