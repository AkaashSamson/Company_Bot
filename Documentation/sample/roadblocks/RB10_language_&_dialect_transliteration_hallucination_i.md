# RB10: Language & Dialect Transliteration Hallucination in Semantic Document Retrieval

> **Category:** Context Retrieval, Chunking & RAG Quality Gaps  
> **Severity:** MEDIUM | **Probability:** MEDIUM  
> **Blast Radius:** Zero retrieval matches for non-English queries or technical corporate abbreviations

---

## 1. Problem Description & Root Cause

Employees type corporate acronyms, project code words, or non-English phrases (e.g. 'P-Leave', 'WFH exception', 'Comp-off policy'). The query normalizer or embedding model fails to bridge phonetic or abbreviation distances, yielding similarity scores < 0.40 and causing premature fallback.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Acronym & Jargon Retrieval Drop                   |
+-------------------------------------------------------------------------+
| User Query: 'How to claim comp off after weekend release?'              |
| Document Text: 'Compensatory off-in-lieu policy for off-hours support'   |
|                                                                         |
| Embedding Distance: Cosine Similarity 0.61 (Threshold: 0.75)            |
| Retrieval Service: 0 chunks qualify                                     |
|                                                                         |
| [!] Orchestrator: 'I could not find that information...'                 |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Expand acronyms in `QueryNormalizer` using an enterprise terminology dictionary (e.g. 'comp off' -> 'compensatory off').
2. Implement hybrid sparse-dense retrieval (BM25 + Dense Vectors) to catch exact keyword matches.
3. Add continuous synonym expansion to the prompt resolution stage.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
