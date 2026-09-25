# RB20: API Key Depletion Silent Deadlock in Background Conversation Logging

> **Category:** LLM Provider Failover, Latency & Rate Limits  
> **Severity:** MEDIUM | **Probability:** LOW  
> **Blast Radius:** Audit logs lost; intermittent server thread pool degradation

---

## 1. Problem Description & Root Cause

The background conversation logger or title summarizer uses the LLM to generate conversation titles or intent tags. When API credits expire or rate limits hit, background worker threads block or retry continuously, consuming thread pool executors and causing memory leaks.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Background Logger Thread Pool Starvation          |
+-------------------------------------------------------------------------+
| User Chat Request finished successfully                                 |
| Background Thread spawned: log_conversation()                           |
|                                                                         |
| Thread calls LLM for conversation topic tagging                         |
| Key expired -> HTTP 401 Unauthorized -> Retries 5 times with sleep(5s)  |
| 100 concurrent requests spawn 100 blocked background threads            |
| [!] Python ThreadPoolExecutor queue saturated; server stops processing  |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Isolate background tasks into bounded queues with `timeout=2.0` seconds.
2. Never perform LLM-dependent operations inside the critical logging path.
3. Implement fail-silent guards around `ConversationLogger`.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
