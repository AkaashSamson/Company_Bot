# RB19: Asymmetric Fallback Provider Token Limits Triggering Mid-Conversation Context Clippings

> **Category:** LLM Provider Failover, Latency & Rate Limits  
> **Severity:** HIGH | **Probability:** MEDIUM  
> **Blast Radius:** HTTP 400 Bad Request on fallback provider; total query failure

---

## 1. Problem Description & Root Cause

Primary provider supports 128k context (e.g. Claude 3.5 Sonnet / GPT-4o), while fallback provider (e.g. Groq Llama 3 8B) only supports an 8k context window. When an 11k prompt fails on the primary provider, the fallback immediately rejects the request with `context_length_exceeded`.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Asymmetric Context Window Fallback Crash          |
+-------------------------------------------------------------------------+
| Prompt constructed: 11,500 tokens (Fits Primary 128k limit)             |
|                                                                         |
| Primary Provider throws HTTP 503 Service Unavailable                     |
| Fallback Provider engaged: Groq Llama 3 (8,192 token limit)             |
|                                                                         |
| [!] Groq API: HTTP 400 'maximum context length is 8192 tokens'          |
| Fallback fails immediately without attempting answer generation         |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Dynamically prune conversation history and context chunks in `FallbackLLMProvider` before dispatching to lower-context models.
2. Configure model-specific maximum input token limits in settings.
3. Enforce context compression when switching to secondary providers.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
