# RB30: Client-Side Timeout Disconnect During Prolonged RAG Fallback Causing Ghost LLM Invocations

> **Category:** Observability, Traceability & Production Deployment  
> **Severity:** MEDIUM | **Probability:** HIGH  
> **Blast Radius:** Wasted LLM API token spend; server thread hogging for abandoned queries

---

## 1. Problem Description & Root Cause

A complex multi-part query takes 18 seconds to resolve (retrieval + re-ranking + multi-turn synthesis). The user gets impatient and closes the browser tab or refreshes at second 12. The backend server continues generating tokens on OpenRouter, burning corporate API credits and GPU compute for an abandoned request.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Ghost LLM Execution on Client Disconnect          |
+-------------------------------------------------------------------------+
| User launches expensive query -> Closes browser tab after 10s           |
| Frontend disconnects TCP socket                                         |
|                                                                         |
| Backend FastApi / Thread does not monitor client disconnect             |
| LLM continues generating 1500 tokens on OpenRouter (cost incurred)     |
| Result: Wasted API spend & worker thread locked for 25 seconds          |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Monitor `fastapi.Request.is_disconnected()` in streaming generator loops.
2. Pass `asyncio.CancelledError` signals down to LLM HTTP client to abort in-flight requests immediately.
3. Enforce maximum request execution deadlines with automatic cancellation tokens.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
