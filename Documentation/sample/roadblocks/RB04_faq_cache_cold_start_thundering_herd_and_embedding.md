# RB04: FAQ Cache Cold-Start Thundering Herd and Embedding Model Lock Contention

> **Category:** Semantic Caching & Vector Store Corruption  
> **Severity:** HIGH | **Probability:** MEDIUM  
> **Blast Radius:** Pod startup timeout; 60+ second API response delays on cold restarts

---

## 1. Problem Description & Root Cause

On application boot or container cold-start, multiple concurrent requests arrive simultaneously before SentenceTransformer has completed embedding 200+ FAQ entries. Multiple threads attempt to initialize and lock the model, or requests queue up behind an uninitialized cache lock, triggering orchestrator timeout cascades.

---

## 2. Architectural Failure Dataflow

```text
+-------------------------------------------------------------------------+
| ARCHITECTURE FAILURE: Cold-Start Thundering Herd                        |
+-------------------------------------------------------------------------+
| FastAPI Server Startup                                                  |
|      |                                                                  |
|      v                                                                  |
| Incoming Request 1 ----+                                                |
| Incoming Request 2 ----+--> [FAQSimilarityCache.__init__ Lock Contention]|
| Incoming Request 3 ----+          |                                     |
|                                   v                                     |
|                       Heavy CPU: SentenceTransformer.encode(280 items)  |
|                       Duration: ~4.5 seconds per worker                 |
|                                   |                                     |
|                       [!] HTTP 504 Gateway Timeout on all 3 clients     |
+-------------------------------------------------------------------------+
```

---

## 3. Production Impact Assessment

- **Timeline Delay Impact:** High likelihood of sprint disruption if encountered during end-to-end integration or scale testing.
- **Data Integrity Risk:** Risk of inconsistent, stale, or out-of-scope policies being delivered to corporate users.
- **Operational Overhead:** Engineering time required to diagnose intermittent cache and retrieval bugs without explicit telemetry.

---

## 4. Concrete Mitigation & Prevention Architecture

1. Pre-warm and serialize FAQ embeddings during Docker build / deployment step into a precomputed `.npy` matrix.
2. Load precomputed embeddings via `np.load('data/faqs_matrix.npy')` in under 2ms instead of dynamic on-boot encoding.
3. Implement FastAPI lifespan event handlers (`@asynccontextmanager`) ensuring readiness probes fail until cache is warm.

---

## 5. Verification & Testing Strategy

- **Unit Test Coverage:** Automated pytest cases verifying edge-case conditions and isolation.
- **Contract Test Assertions:** Verification that API contracts and error statuses behave predictably under failure conditions.
- **Regression Monitoring:** Continuous validation via `PipelineTracer` telemetry spans.
