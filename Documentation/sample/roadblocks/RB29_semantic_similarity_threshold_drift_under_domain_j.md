# RB29: Semantic Similarity Threshold Drift Under Domain Jargon Expansion

> **Category:** Observability, Traceability & Production Deployment  
> **Severity:** HIGH | **Probability:** HIGH  
> **Blast Radius:** False cache hits; completely unrelated answers returned to nuanced queries

---

## 1. Problem Description & Root Cause

The similarity threshold is statically configured to 0.92 in `settings.py`. In enterprise HR and IT contexts, many completely different policies share 90% of their vocabulary (e.g. 'Leave without pay for medical reasons' vs 'Leave without pay for educational reasons'). The static threshold triggers false positive hits.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Semantic Threshold False Positive Drift           |
+-------------------------------------------------------------------------+
| Cached FAQ: 'Leave without pay for educational sabbatical'              |
| Incoming:   'Leave without pay for medical emergency'                   |
|                                                                         |
| Vocabulary overlap: 85%                                                 |
| Cosine Similarity: 0.931 (Threshold: 0.920)                             |
|                                                                         |
| [!] FALSE CACHE HIT!                                                    |
| User seeking medical emergency leave is told to submit university proof! |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Implement dynamic domain-adaptive thresholding based on question length and noun-phrase specificity.
2. Mandate key entity extraction: ensure core subject nouns (e.g. 'medical' vs 'educational') match exactly before cache hit.
3. Use cross-encoder re-ranking for borderline similarity scores between 0.88 and 0.95.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
