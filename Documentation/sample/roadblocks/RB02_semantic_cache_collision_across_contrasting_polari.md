# RB02: Semantic Cache Collision Across Contrasting Polarities (Negation Blindness)

> **Category:** Semantic Caching & Vector Store Corruption  
> **Severity:** HIGH | **Probability:** HIGH  
> **Blast Radius:** Incorrect policy answers served to users; compliance and HR liability

---

## 1. Problem Description & Root Cause

A user asks 'Are contract workers entitled to annual leave?' (Answer: No). A subsequent user asks 'Are contract workers NOT entitled to annual leave?' or 'Can contract workers take annual leave?'. Cosine similarity between negated and affirmative sentences with small transformer models often exceeds 0.94, causing the cache to return the affirmative answer for a negative question, completely reversing HR policy meaning.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Semantic Negation Blindness                       |
+-------------------------------------------------------------------------+
| User A Query: 'Is moonlighting permitted under employee handbook?'     |
| Output: 'Moonlighting is strictly prohibited without prior approval.'  |
|                                                                         |
| User B Query: 'Is moonlighting NOT prohibited under handbook?'         |
| Embedding Cosine Similarity: 0.952 (Threshold: 0.920)                  |
|                                                                         |
| [!] CACHE HIT -> Returns 'strictly prohibited' as answer to whether     |
|     it is NOT prohibited, misleading employee.                          |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Implement lexical polarity checking (presence of 'not', 'never', 'prohibited', 'allowed') before approving cache hits.
2. Utilize the DualCache / QualityAwareCache validation rules to mandate semantic contradiction check before cache return.
3. Maintain bidirectional sentiment/polarity guardrails in `app/infrastructure/cache/quality_aware_cache.py`.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
