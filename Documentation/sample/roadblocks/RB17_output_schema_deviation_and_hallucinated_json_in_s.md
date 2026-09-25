# RB17: Output Schema Deviation and Hallucinated JSON in Structured Citations

> **Category:** LLM Provider Failover, Latency & Rate Limits  
> **Severity:** HIGH | **Probability:** HIGH  
> **Blast Radius:** Chat UI crashes with JSON parse error; citations render as empty or raw syntax

---

## 1. Problem Description & Root Cause

When the fallback provider (e.g. Groq running Llama 3 8B) is engaged, it occasionally generates trailing markdown fences, conversational prefixes (`Here is the JSON you requested:`), or unescaped quotes inside JSON strings. `json.loads()` raises `JSONDecodeError`, breaking the chat API response contract.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Structured Output Schema Malformation             |
+-------------------------------------------------------------------------+
| Fallback LLM Response:                                                  |
| "Certainly! Here is your answer:                                        |
|  ```json                                                                |
|  {\"answer\": \"Vacation policy is 18 days \"exclusive\" of holidays\"}  |
|  ```"                                                                   |
|                                                                         |
| json.loads() fails with JSONDecodeError: expecting ',' delimiter        |
| [!] API returns HTTP 500 to frontend client                             |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Use regex-based JSON extraction (`re.search(r'\{.*\}', text, re.DOTALL)`) with lenient parsing.
2. Enforce schema repair via Pydantic model validation with fallback to raw string answer.
3. Enforce grammar constraints / structured outputs (JSON mode) at the provider API level.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
