# RB01: Vector Store Dimension Mismatch on Embedding Model Hot-Swaps

> **Category:** Semantic Caching & Vector Store Corruption  
> **Severity:** CRITICAL | **Probability:** HIGH  
> **Blast Radius:** Total vector retrieval outage; ChromaDB / FAQSimilarityCache crashes on startup or query

---

## 1. Problem Description & Root Cause

During Phase 3 optimization, the team decides to upgrade EMBEDDING_MODEL from 'sentence-transformers/all-MiniLM-L6-v2' (384 dimensions) to 'BAAI/bge-large-en-v1.5' (1024 dimensions) or an OpenAI/Cohere embedding endpoint. ChromaDB collections created with 384 dimensions fail with dimension mismatch errors when queried with 1024-dimension query vectors, and FAQSimilarityCache._matrix fails matrix multiplication (@) with query vectors.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Vector Dimension Mismatch                        |
+-------------------------------------------------------------------------+
| Incoming Query ---> [Embedder: BGE-Large (1024-dim)]                    |
|                            |                                            |
|                            v                                            |
|               query_vector: shape (1024,)                               |
|                            |                                            |
|                            v                                            |
|        Matrix Dot Product: self._matrix @ query_vec                     |
|                 Shape (N, 384) @ (1024,)                                |
|                            |                                            |
|                            v                                            |
|            [!] ValueError: operands could not be broadcast!            |
|            Server returns HTTP 500 on all chat / FAQ endpoints          |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Implement collection metadata versioning in ChromaDB and vector stores with explicit 'embedding_dim' and 'model_name' tags.
2. Build an automated re-indexing migration CLI command (`python -m app.cli reindex --model <name>`).
3. Enforce startup validation gates that assert query embedding shape matches store dimensions before accepting HTTP traffic.
4. Maintain dual collection blue/green swap during model transitions.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
