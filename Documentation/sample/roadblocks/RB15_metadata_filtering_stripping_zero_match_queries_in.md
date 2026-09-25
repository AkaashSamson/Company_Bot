# RB15: Metadata Filtering Stripping Zero-Match Queries into Fallback Information Exposure

> **Category:** Multi-Tenant RBAC / ABAC Security & Scoping  
> **Severity:** HIGH | **Probability:** MEDIUM  
> **Blast Radius:** Users receive unauthorized document fragments through fallback RAG answers

---

## 1. Problem Description & Root Cause

A user queries a project they lack permission to view. The orchestrator's probe method `_probe_unauthorized_relevance()` runs to detect if information exists outside their scope to provide contact details. If the probe accidentally leaks the document snippet or summary into the returned message, the user learns the confidential contents without being granted project membership.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Unauthorized Probe Information Bleed              |
+-------------------------------------------------------------------------+
| Query: 'What is Project Titan acquisition budget?'                      |
| User Scope: Restricted (No Titan access)                                |
|                                                                         |
| Orchestrator runs _probe_unauthorized_relevance()                       |
| Bug: Formatted answer includes: 'Project Titan budget of $5M is locked. |
|      Please contact project manager Jane Doe for access.'               |
|                                                                         |
| [!] Confidential budget figure ($5M) leaked in the denial message!      |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Ensure `_probe_unauthorized_relevance()` only returns boolean existence flags and metadata contact names.
2. Never pass text content of unauthorized chunks into LLM generation or fallback string templates.
3. Enforce unit tests that verify zero text leakage on access denial responses.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
