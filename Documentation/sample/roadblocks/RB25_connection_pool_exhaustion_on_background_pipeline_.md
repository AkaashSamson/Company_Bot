# RB25: Connection Pool Exhaustion on Background Pipeline Tracer Telemetry Export

> **Category:** Concurrency, Session State & Database Deadlocks  
> **Severity:** MEDIUM | **Probability:** MEDIUM  
> **Blast Radius:** File descriptor / TCP socket leak; backend stops responding to HTTP requests

---

## 1. Problem Description & Root Cause

Every query traced by `PipelineTracer` creates HTTP connections or background threads to export trace events to LangSmith or local metrics. When network latency to LangSmith increases, connections remain in `ESTABLISHED` or `CLOSE_WAIT`, eventually exhausting open file descriptors (`errno 24: Too many open files`).

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Telemetry Connection Exhaustion                   |
+-------------------------------------------------------------------------+
| 100 concurrent requests -> 100 LangSmith span export attempts            |
| LangSmith API response latency spikes to 8s                             |
| Open TCP connections accumulate: 1024 (ULIMIT reached)                  |
|                                                                         |
| [!] OSError: [Errno 24] Too many open files                             |
| Server cannot accept incoming client sockets                            |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Use a single shared connection pool with `httpx.Client(limits=Limits(max_connections=20))`.
2. Export traces asynchronously via a non-blocking background queue with dropped event threshold.
3. Enforce strict timeout (1.5s) on all telemetry exports.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
