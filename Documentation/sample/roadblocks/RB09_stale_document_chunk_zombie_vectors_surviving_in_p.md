# RB09: Stale Document Chunk Zombie Vectors Surviving In-Place File Re-Uploads

> **Category:** Context Retrieval, Chunking & RAG Quality Gaps  
> **Severity:** HIGH | **Probability:** HIGH  
> **Blast Radius:** Conflicting old and new policies returned simultaneously, confusing employees

---

## 1. Problem Description & Root Cause

An administrator re-uploads an updated HR handbook ('HR_Policy_2026_v2.docx'). The ingestion service generates new chunk IDs (or fails to purge old chunk vectors associated with the previous document ID). Both outdated 2024 leave policies and new 2026 policies coexist in ChromaDB, producing contradictory answers.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Zombie Chunk Vector Persistence                   |
+-------------------------------------------------------------------------+
| 2024 Handbook: 'Annual leave is 14 days.' (Doc ID: doc-01)              |
| 2026 Handbook: 'Annual leave is 18 days.' (Doc ID: doc-02)              |
|                                                                         |
| ChromaDB Collection state after re-upload:                              |
| - chunk_doc01_04: '14 days' (STALE ZOMBIE)                              |
| - chunk_doc02_04: '18 days' (CURRENT)                                   |
|                                                                         |
| Retrieval returns BOTH -> LLM says 'Leave is both 14 days and 18 days.' |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Enforce transactional document replacement: delete all chunks with matching `document_id` or `filename` before inserting new vectors.
2. Add document version hash checking and purge orphaned vectors during startup or maintenance tasks.
3. Include `valid_from` and `is_active` boolean metadata filtering in vector queries.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
