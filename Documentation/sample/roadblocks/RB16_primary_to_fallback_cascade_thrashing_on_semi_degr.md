# RB16: Primary-to-Fallback Cascade Thrashing on Semi-Degraded HTTP 504 / 429

> **Category:** LLM Provider Failover, Latency & Rate Limits  
> **Severity:** CRITICAL | **Probability:** HIGH  
> **Blast Radius:** 30-second user latency spikes; exhaustion of secondary fallback rate limits

---

## 1. Problem Description & Root Cause

OpenRouter experiences intermittent 15-second latency spikes and HTTP 429 throttling. `FallbackLLMProvider` waits for the primary request to time out (15s), catches the error, and then retries against Groq. Groq rate-limits under the sudden burst, failing as well. Total user wait time exceeds 35 seconds, causing UI connection aborts.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Cascading Failover Thrashing                      |
+-------------------------------------------------------------------------+
| Client Request                                                          |
|      |                                                                  |
|      v                                                                  |
| [Primary: OpenRouter] ---> [15s Timeout / HTTP 429 Spike]               |
|      |                                                                  |
|      v (Fallback triggered after 15s delay)                             |
| [Secondary: Groq]     ---> [Instant HTTP 429 Rate Limit Exceeded]       |
|      |                                                                  |
|      v                                                                  |
| [!] 32s Total Latency -> Streamlit client drops connection              |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Implement an active Circuit Breaker pattern with exponential backoff in `FallbackLLMProvider`.
2. When primary fails 3 consecutive times, immediately route to fallback without waiting for 15s timeout.
3. Maintain short connection timeouts (5s) and automated health-check pings.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
