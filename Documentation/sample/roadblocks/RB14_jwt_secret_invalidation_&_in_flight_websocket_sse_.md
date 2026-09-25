# RB14: JWT Secret Invalidation & In-Flight WebSocket/SSE Disconnect State Corruption

> **Category:** Multi-Tenant RBAC / ABAC Security & Scoping  
> **Severity:** MEDIUM | **Probability:** MEDIUM  
> **Blast Radius:** Broken chat streaming; orphan session memory records accumulate in RAM

---

## 1. Problem Description & Root Cause

When the backend server restarts or `AUTH_SECRET_KEY` is rotated, active Streamlit sessions holding expired JWT tokens send requests. Mid-stream response generation fails with HTTP 401, leaving `_pending_citations` and `_last_interaction` dictionaries with orphaned, uncollected session objects.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: JWT Invalidation Mid-Stream State Corruption      |
+-------------------------------------------------------------------------+
| Active Streamlit Session (session_id='sess_8812')                       |
| Chat call initiated -> LLM begins streaming tokens                      |
| Server restarts / Key Rotated -> Token becomes invalid                  |
|                                                                         |
| Client receives HTTP 401 Unauthorized mid-response                      |
| Session memory in orchestrator holds pending locks & uncommitted spans  |
| [!] Memory leak: session state never cleaned up                         |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Implement session cleanup TTL timers using background reaper threads (`_last_interaction` eviction after 1 hour).
2. Handle JWT expiration gracefully in Streamlit frontend with automatic session re-authentication modal.
3. Enforce idempotent session initialization in `SessionMemoryService`.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
