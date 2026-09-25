# RB13: Circular Department & Project Hierarchy Loops in Permission Resolution

> **Category:** Multi-Tenant RBAC / ABAC Security & Scoping  
> **Severity:** HIGH | **Probability:** LOW  
> **Blast Radius:** Stack overflow recursion in auth engine; API worker crash

---

## 1. Problem Description & Root Cause

In SQLite organization tables, Department A is configured as child of Department B, which is modified to be a child of Department C, which references Department A. When `AuthorizationEngine.get_descendant_departments()` runs recursive resolution during chat authorization, it enters an infinite loop, exhausting call stack depth.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Circular Hierarchy Recursion                      |
+-------------------------------------------------------------------------+
| Department Table:                                                       |
| Dept A (parent: Dept C) -> Dept B (parent: Dept A) -> Dept C (parent: B)|
|                                                                         |
| Auth Engine: resolve_effective_scope(user)                              |
|   -> get_children(A) -> B -> C -> A -> B -> C ...                       |
|                                                                         |
| [!] RecursionError: maximum recursion depth exceeded in comparison      |
| Server worker terminates abruptly; request drops                        |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Track `visited: set[int]` in all recursive department / project hierarchy traversals.
2. Add cycle detection validation in SQLAlchemy model insert/update hooks.
3. Enforce maximum hierarchy depth limit (e.g. max_depth=10) with descriptive exception logging.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
