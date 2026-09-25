# RB24: Distributed Transaction Desynchronization Between SQLite User DB and MongoDB FAQs

> **Category:** Concurrency, Session State & Database Deadlocks  
> **Severity:** MEDIUM | **Probability:** LOW  
> **Blast Radius:** Dangling references in user profiles to non-existent FAQ documents

---

## 1. Problem Description & Root Cause

When an admin deletes a user or project in SQLite, the corresponding MongoDB FAQ entries and author metadata are left untouched. When subsequent queries reference the author ID, the application crashes on missing foreign key.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Distributed Dual-Database Desync                 |
+-------------------------------------------------------------------------+
| SQLite Database: User ID 44 deleted                                     |
| MongoDB FAQs: 12 entries have 'created_by_user': 44                      |
|                                                                         |
| Admin UI loads FAQs with author details -> Query joins user table       |
| [!] NoneType error: user record does not exist in SQLite                |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Implement soft deletes (`is_active=False`) rather than hard physical deletions.
2. Use defensive joins with fallback placeholder objects ('Former Employee').
3. Add periodic consistency reconciliation jobs.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
