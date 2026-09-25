# RB21: SQLite Database Lock Contention ('database is locked') Under Concurrent Sessions

> **Category:** Concurrency, Session State & Database Deadlocks  
> **Severity:** CRITICAL | **Probability:** HIGH  
> **Blast Radius:** HTTP 500 Internal Server Error for concurrent users; corrupted database WAL

---

## 1. Problem Description & Root Cause

SQLite operates with database-level write locks. When 10+ employees use Company-Bot simultaneously, concurrent write operations (writing audit logs, updating session messages, saving user activity) trigger `sqlite3.OperationalError: database is locked`, failing user queries.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: SQLite Concurrency Lock Contention               |
+-------------------------------------------------------------------------+
| User 1: Write Conversation Log ----+                                    |
| User 2: Write User Profile Update -+--> [knowlayer.db SQLite Write Lock]|
| User 3: Insert Audit Trail --------+          |                         |
|                                               v                         |
|                                    Busy Timeout Exceeded (>5000ms)      |
|                                               |                         |
|                         [!] sqlite3.OperationalError: database is locked|
|                         HTTP 500 error returned to User 3               |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Enable SQLite Write-Ahead Logging (`PRAGMA journal_mode=WAL;`) and increase busy timeout (`PRAGMA busy_timeout=10000;`).
2. Route high-volume audit logs to asynchronous background batch workers.
3. Provide seamless migration path to PostgreSQL for multi-user production environments.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
