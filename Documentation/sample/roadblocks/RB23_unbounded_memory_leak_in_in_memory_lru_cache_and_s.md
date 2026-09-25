# RB23: Unbounded Memory Leak in In-Memory LRU Cache and Session Memory Service

> **Category:** Concurrency, Session State & Database Deadlocks  
> **Severity:** HIGH | **Probability:** HIGH  
> **Blast Radius:** Out-Of-Memory (OOM) killer terminates Python backend process

---

## 1. Problem Description & Root Cause

Global dictionaries `_last_interaction`, `_pending_citations`, and `_alternative_answer_given` inside `query_orchestrator.py` store user context and evidence chunks indefinitely without a maximum size or TTL. After thousands of queries, the Python process memory balloons from 600MB to 4GB+ until the OS OOM killer terminates it.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Unbounded Memory Leak in Global State             |
+-------------------------------------------------------------------------+
| Query 1  -> _last_interaction['sess_1'] (Evidence: 50KB text)           |
| Query 2  -> _last_interaction['sess_2'] (Evidence: 50KB text)           |
| ...                                                                     |
| Query 50,000 -> 50,000 retained session dictionaries                    |
| RAM usage: 3.8 GB -> 4.2 GB                                             |
|                                                                         |
| [!] Linux Kernel OOM Killer sends SIGKILL to uvicorn worker             |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Replace plain `dict` structures with bounded `OrderedDict` or `cachetools.TTLCache(maxsize=1000, ttl=3600)`.
2. Implement an automated hourly state eviction routine for sessions older than 2 hours.
3. Store interaction state in Redis or SQLite rather than Python process heap.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
