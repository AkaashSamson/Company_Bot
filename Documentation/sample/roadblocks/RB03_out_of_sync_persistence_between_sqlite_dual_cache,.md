# RB03: Out-of-Sync Persistence Between SQLite Dual-Cache, MongoDB FAQ Store, and Disk JSON

> **Category:** Semantic Caching & Vector Store Corruption  
> **Severity:** HIGH | **Probability:** MEDIUM  
> **Blast Radius:** Ghost FAQ responses reappear after deletion; inconsistency across worker nodes

---

## 1. Problem Description & Root Cause

When an entry is modified or deleted via administrative tools or relevance feedback, one storage tier is updated (e.g. SQLite database) while `data/faqs.json` or MongoDB `faqs` collection retains the stale entry. Multi-worker deployments (e.g. Gunicorn/Uvicorn workers) hold distinct memory-mapped copies of the cache matrix, leading to intermittent cache hits on dead records.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Multi-Tier Cache Desynchronization               |
+-------------------------------------------------------------------------+
| Client Admin Action: DELETE FAQ entry 'P.1'                             |
|      |                                                                  |
|      +---> Worker 1: deletes from data/faqs.json (in-memory cleared)    |
|      +---> Worker 2: in-memory _matrix NEVER notified (STALE!)          |
|      +---> MongoDB: update fails on network timeout (DIRTY!)            |
|                                                                         |
| User query hits Worker 2 -> Stale FAQ answer returned!                  |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Implement a single unified CacheInvalidationEvent pub/sub or file-watch hook (using watchdog or SQLite WAL notification).
2. Centralize cache write operations through a UnitOfWork pattern.
3. Add atomic file swap (`with_suffix('.tmp') -> replace`) and explicit in-memory matrix invalidation callbacks.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
