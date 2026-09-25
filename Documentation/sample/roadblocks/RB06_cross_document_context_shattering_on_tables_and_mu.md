# RB06: Cross-Document Context Shattering on Tables and Multi-Page Policies

> **Category:** Context Retrieval, Chunking & RAG Quality Gaps  
> **Severity:** CRITICAL | **Probability:** HIGH  
> **Blast Radius:** LLM hallucinates compensation / leave numbers due to truncated table headers

---

## 1. Problem Description & Root Cause

HR policy documents containing compensation tiers, notice period matrices, or medical benefit limits are stored in Markdown or Word tables. Standard character/token chunking (e.g. 500-char chunks) splits table rows from their column headers. ChromaDB retrieves data rows without header context, causing the LLM to misattribute numbers.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Context Shattering in Chunking                    |
+-------------------------------------------------------------------------+
| Original Table:                                                         |
| | Role Level | Notice Period | Severance Multiplier |                   |
| | Executive  | 90 Days       | 3x Monthly Base      |                   |
| | Regular    | 30 Days       | 1x Monthly Base      |                   |
|                                                                         |
| Chunk 1: '| Role Level | Notice Period |' (Boundary split)              |
| Chunk 2: '| Executive | 90 Days | 3x |' (Headers missing!)             |
|                                                                         |
| User Query: 'What is the notice period for regular staff?'              |
| LLM only receives Chunk 2 without headers -> Hallucinates '90 Days'    |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Implement table-aware chunking that preserves parent table headers in every extracted table row chunk.
2. Use hierarchical chunking with parent-child document pointers in ChromaDB metadata.
3. Add structured markdown table preprocessing before vector store ingestion.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
