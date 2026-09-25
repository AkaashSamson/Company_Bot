# RB08: Token Budget Overflow from High-Scoring Distractor Chunks Starving Grounding

> **Category:** Context Retrieval, Chunking & RAG Quality Gaps  
> **Severity:** HIGH | **Probability:** HIGH  
> **Blast Radius:** Orchestrator context truncated; LLM outputs 'I could not find that information'

---

## 1. Problem Description & Root Cause

When `RAG_MAX_CONTEXT_CHARS` is set to 12000, repetitive boilerplates (e.g. copyright notices, standard disclaimers, generic introductions) that match broad semantic queries fill up the available context window. The chunk containing the exact policy clause is pushed out of the candidate pool, triggering unnecessary fallbacks.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Context Window Distractor Starvation             |
+-------------------------------------------------------------------------+
| Query: 'Parental leave eligibility criteria'                            |
|                                                                         |
| Candidate Chunks:                                                       |
| [Chunk 1: 4000 chars] 'General HR Mission Statement and Core Values...' |
| [Chunk 2: 4500 chars] 'Employee Welfare and Wellness Overview...'      |
| [Chunk 3: 4000 chars] 'Document Control and Revision History...'        |
| Total chars = 12500 -> Truncation cutoff reached!                       |
|                                                                         |
| [!] Dropped Chunk 4: 'Section 4.2 Parental Leave: 26 weeks paid...'     |
| Result: LLM states 'Information not found in available documents.'      |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Apply Maximum Marginal Relevance (MMR) re-ranking or cross-encoder re-ranking to penalize duplicate/distractor content.
2. Strip headers, footers, and copyright boilerplate during document parsing.
3. Implement dynamic chunk sizing and evidence diversity filters in `retrieval_selection.py`.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
