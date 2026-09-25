# RB18: Silent Truncation of Streaming Tokens Leading to Malformed Markdown in UI

> **Category:** LLM Provider Failover, Latency & Rate Limits  
> **Severity:** MEDIUM | **Probability:** MEDIUM  
> **Blast Radius:** Unfinished sentences; feedback buttons fail to display due to missing relevance prompt

---

## 1. Problem Description & Root Cause

The model hits `max_tokens` (or token budget limits) midway through generating a response. Because the response was cut off abruptly, the closing prompt `\n\nWas this response relevant to your question?` is never generated. Streamlit regex checks fail to find `RELEVANCE_PROMPT`, so the 👍 / 👎 feedback buttons never render.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Max Token Truncation Cuts Off UI Controls         |
+-------------------------------------------------------------------------+
| Prompt generated -> LLM generates 512 tokens (Max Token reached)        |
| Answer text: '...the employee must submit Form B to the department head'|
| [!] Cut off before generating RELEVANCE_PROMPT                          |
|                                                                         |
| Streamlit UI logic:                                                     |
| if RELEVANCE_PROMPT in message.content: render_feedback_buttons()       |
| Result: No buttons rendered -> User relevance feedback loop is broken!  |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Guarantee in `QueryOrchestrator._finish()` that `RELEVANCE_PROMPT` is post-pended if absent.
2. Increase max output tokens for complex policy answers to 1024.
3. Separate conversational feedback triggers into explicit API metadata fields rather than embedded prompt strings.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
