# RB11: Authorization Boundary Leakage via Shared Vector Search Indices

> **Category:** Multi-Tenant RBAC / ABAC Security & Scoping  
> **Severity:** CRITICAL | **Probability:** MEDIUM  
> **Blast Radius:** Confidential financial/payroll data visible to unauthorized project members

---

## 1. Problem Description & Root Cause

ChromaDB stores all enterprise documents in a single flat collection. If `authorized_project_ids` metadata filtering is bypassed, misconfigured, or contains an empty list `[]` treated as 'no filter' rather than 'no access', restricted project documents are included in candidate retrieval for low-privilege users.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Cross-Project Vector Search Leak                 |
+-------------------------------------------------------------------------+
| User: Junior Developer (Authorized: [Project-Alpha])                    |
| Query: 'Client billing rates and hourly margin'                         |
|                                                                         |
| ChromaDB query: where={'$or': [{'project_id': 'Project-Alpha'}, ...]}    |
| Flaw: Empty project filter defaults to ALL documents                    |
|                                                                         |
| [!] Top chunk returned from Project-Secret-Finance!                     |
| Citations expose confidential executive client contracts                |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Implement defense-in-depth: Enforce explicit post-retrieval authorization verification in `ProvenanceService`.
2. Default to FAIL-CLOSED: if `authorized_project_ids == []` and user is not admin, deny search immediately.
3. Maintain separated collection partitions or tenant IDs at the vector database layer.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
