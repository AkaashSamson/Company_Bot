# 10 Potential Architectural & Operational Roadblocks with Unique Edge Cases (KnowLayer V3)

> **Document:** KnowLayer V3 Critical Failure Modes, Edge Cases & Preemptive Mitigations  
> **Applicable Sprints:** Phase 3, Phase 4, Phase 5  
> **Status:** Active Risk Matrix & Engineering Directives  

---

### Roadblock 1: Cold-Start Synchronous Model Loading Blocks Event Loop (The 30s Timeout)

```text
[Uvicorn Starts]
       |
       v
lifespan() -> init_orchestrator() -> ChromaVectorStore() -> loads SentenceTransformer (all-MiniLM-L6-v2)
       |
       +---> [SYNCHRONOUS CPU THREAD BLOCKED FOR 45 SECONDS]
       |
       v
Incoming /health HTTP GET probe arrives -> Worker cannot process request! -> [TIMEOUT / CRASH]
```

* **The Unique Edge Case:** Observed during automated deployments and `./setup.ps1`:
  `[HEALTH] Waiting for FastAPI backend to become ready... [TIMEOUT]`.
* **Why it happens:** In `app/main.py:lifespan`, `init_orchestrator()` loads heavy PyTorch embedding weights and warms persistence synchronously inside the main async event loop thread. On cold starts or machines without GPU acceleration, downloading or initializing the transformer model takes 35–60 seconds. Because the single worker thread is blocked executing synchronous Python code, **Uvicorn cannot accept incoming socket connections on `/health`**.
* **Mitigation:**
  Run `init_orchestrator()` in a background worker thread via `asyncio.to_thread(init_orchestrator)` or load embeddings lazily on the first retrieval request rather than blocking the FastAPI startup gate.

---

### Roadblock 2: Multi-Worker Race Conditions Corrupting Local JSON Caches

```text
Uvicorn Worker Process 1 (PID 1001)            Uvicorn Worker Process 2 (PID 1002)
   Memory: self._lock (RLock)                     Memory: self._lock (RLock)
               |                                              |
      [Acquires Lock 1]                              [Acquires Lock 2]
               |                                              |
  Opens data/semantic_cache.json                 Opens data/semantic_cache.json
  Writes 45,000 bytes                            Writes 48,000 bytes
               \                                            /
                +---------------------+--------------------+
                                      |
                           [COLLISION ON OS DISK]
                    JSON file truncated / syntax corrupted!
```

* **The Unique Edge Case:** `threading.RLock()` in `dual_cache.py` only synchronizes threads **within a single Python process**.
* **Why it happens:** When KnowLayer is deployed to production with multiple worker processes (`uvicorn app.main:app --workers 4`), each worker has its own independent heap and its own `RLock`. If Worker 1 and Worker 2 complete queries at the exact same millisecond, both call `json.dump()` on `data/semantic_cache.json`. One worker overwrites the other, causing `json.decoder.JSONDecodeError: Unterminated string starting at line...` on the next server reboot.
* **Mitigation:**
  Use atomic file replacement via temporary file swap:
  Write to `data/semantic_cache.json.tmp` and use `os.replace()` (which is atomic at the OS level on both Windows and Linux), or use SQLite / Redis for multi-worker caches.

---

### Roadblock 3: RBAC Scope Leakage via Unscoped Semantic Cache Hits

```text
User A (Admin / Executive Access) asks:
"What is the bonus payout percentage for VP roles?"
                |
                v
Pipeline executes RAG -> Retrieves confidential Executive Project Doc -> Caches answer under:
cache_key = "hash(bonus payout percentage vp roles)"
                |
-----------------------------------------------------------------------------------------
2 hours later...
User B (Junior Engineer / No Executive Access) asks:
"What is the bonus payout percentage for VP roles?"
                |
                v
Cache checks: Does cache_key exist? -> YES! -> Returns Cached Executive Salary Data!
[DATA BREACH: User B received unauthorized data without touching ChromaDB's where_filter!]
```

* **The Unique Edge Case:** Caching a response without binding the cache key to the caller's authorization scope.
* **Why it happens:** In Phase 2, `QualityAwareCache` and `DualCache` hash normalized queries (`cache_key = hash(query)`). But KnowLayer enforces multi-tenant authorization (`authorized_project_ids`). If an Admin queries a policy that pulls from a restricted project, that answer gets cached globally. If an unprivileged employee asks the same question, a naive cache check serves the answer directly—completely bypassing ChromaDB’s `where_filter`!
* **Mitigation:**
  Namespace all cache keys with the caller's authorized scope hash:
  `cache_key = f"{scope_hash}:{intent}:{normalized_query_hash}"`.

---

### Roadblock 4: Git Merge Carnage on the Hot File (`query_orchestrator.py` in Phase 4)

```text
                         [Phase 2 Feature Branches]
                                     |
    +-----------------+--------------+-----------------+-----------------+
    |                 |                                |                 |
[Akaash Branch]  [Abhinav Branch]                [Neha Branch]     [Roshan Branch]
AK-1.3 (Memory)  AB-3.2 (Normalizer)             NE-4.2 (Rewriter)  RO-1.2 (Scope)
AK-4 (Fallback)  AB-4.2 (Cache Hook)             NE-1.3 (Logging)
                 AB-6.2 (Tracing Hook)
    |                 |                                |                 |
    +-----------------+--------------+-----------------+-----------------+
                                     |
               (All 4 try to merge into query_orchestrator.py)
                                     v
                        [FATAL GIT MERGE CONFLICTS]
              Every single method in QueryOrchestrator broken!
```

* **The Unique Edge Case:** 4 developers making non-orthogonal modifications to the exact same 300-line method (`QueryOrchestrator.answer()`).
* **Why it happens:** Neha inserts a query rewriter at line 575; Abhinav inserts cache lookups at line 512 and tracing spans across every stage; Akaash inserts session memory at line 260; Roshan changes project authorization. If teammates merge out of order, Git cannot resolve indentation and context blocks, halting sprint progress for days.
* **Mitigation:**
  Strict adherence to the **Phase 4 Hot File Sequential Gate**:
  **Step 4.1 (Akaash)** -> **Step 4.2 (Abhinav)** -> **Step 4.3 (Neha)** -> **Step 4.4 (Akaash)**. Only ONE person touches `query_orchestrator.py` at a time.

---

### Roadblock 5: Cross-Encoder Reranker CPU Latency Spike (200ms -> 5,000ms)

```text
[ChromaDB Vector Search] (Bi-Encoder: Fast Cosine Similarity)
Fetches top-15 candidate chunks in 35ms
          |
          v
[Neha's Cross-Encoder Reranker (NE-5.1)]
Concatenates query with EACH of the 15 chunks:
Input: [CLS] Query [SEP] Chunk 1 [SEP] ... [CLS] Query [SEP] Chunk 15 [SEP]
          |
          v
[15 Full Transformer Neural Forward Passes on CPU]
Latency: 15 chunks * 300ms/chunk = 4,500ms!
Streamlit user interface hangs -> User reloads browser -> Sends duplicate query -> Queue explodes!
```

* **The Unique Edge Case:** A Cross-Encoder does not use pre-calculated vector embeddings; it performs full self-attention across the query and chunk text simultaneously.
* **Why it happens:** In Task `NE-5.1`, candidate chunks are reranked to pick the top 4. On a local development machine or server without an Nvidia GPU, passing 15 large text chunks through a cross-encoder model like `cross-encoder/ms-marco-MiniLM-L-6-v2` consumes 100% CPU and causes a multi-second latency spike per user request.
* **Mitigation:**
  Cap reranker input to top-8 candidates instead of top-15, enforce a maximum character length per chunk (500 chars), and set a fallback timeout: if reranking takes $> 500\text{ms}$, return top vector chunks directly.

---

### Roadblock 6: False-Positive Rejections in `cache_quality.py` on Valid Negative Policies

```text
Employee Query: "Can I encash my sick leave during probation?"

Correct Policy Answer from Manual:
"Sick leave encashment is not provided under company policy. Employees do not have 
the option to convert unused sick days to cash."
                      |
                      v
      +------------------------------------------------+
      | cache_quality.py: is_negative_response()       |
      | Matches Pattern 3: r"\bnot\s+provided\b"       |
      | Matches Pattern 4: r"\bdo not\s+have\b"        |
      +------------------------------------------------+
                      |
                      v
[FALSE POSITIVE: Quality Gate thinks this is a model refusal!]
- Answer is REJECTED from Cache.
- Citation suppression triggers -> Bot wipes citations!
- User is told: "Could not find information regarding this policy."
```

* **The Unique Edge Case:** An authoritative policy whose literal content is a negative rule (e.g., *"Leaves do not carry over"*, *"No compensation is provided"*).
* **Why it happens:** In `cache_quality.py`, regex patterns like `r"\bnot\s+provided\b"` and `r"\bdoes not\s+contain\b"` are designed to catch LLM refusals (*"Information is not provided in documents"*). But when a policy explicitly forbids something, the LLM correctly explains that the benefit is *not provided*. The quality gate treats the valid answer as a hallucination/refusal.
* **Mitigation:**
  Anchor regex patterns to document references: only flag as refusal if the negation targets *information/documents* (e.g., `not mentioned in the policy`), NOT when it targets *benefits/actions* (e.g., `leave is not provided`).

---

### Roadblock 7: In-Memory Teams Webhook ASGI Self-Deadlock (Task AK-2.3)

```text
[Microsoft Teams Webhook HTTP POST arrives at FastAPI]
          |
          v
app/infrastructure/channels/teams/adapter.py
Receives webhook on FastAPI worker thread
          |
          v
Calls: requests.post("http://127.0.0.1:8000/api/chat", json=payload)  <-- Synchronous blocking HTTP call!
          |
          v
[DEADLOCK]: The single Uvicorn worker thread is waiting for requests.post() to finish,
but requests.post() cannot be answered because the only worker thread is busy waiting!
          |
          v
Request hangs until Teams drops the webhook with 504 Gateway Timeout.
```

* **The Unique Edge Case:** Dispatching internal API requests to the same server using synchronous network clients.
* **Why it happens:** In Task `AK-2.3`, Akaash's Teams adapter accepts webhooks and dispatches requests to `POST /api/chat`. If this is implemented with `requests.post()` rather than invoking the internal Python service directly (`QueryOrchestrator.answer()`) or using an async client (`httpx.AsyncClient`), single-worker dev servers deadlock immediately.
* **Mitigation:**
  Never make an outbound loopback HTTP call to `127.0.0.1`. The Teams adapter should directly instantiate and invoke `QueryOrchestrator` in-process.

---

### Roadblock 8: Memory Exhaustion & OCR Crash on Large Scanned Documents (Roshan)

```text
[User uploads 50-page scanned Benefits Guide (25MB .pdf / .docx)]
                         |
                         v
app/infrastructure/ingestion/image_extractor.py extracts 50 full-page TIFF/PNG rasters
                         |
                         v
pytesseract.image_to_string() loops over 50 uncompressed 300-DPI bitmaps:
RAM Consumption: 50 pages * 60MB bitmap in memory = 3.0 GB RAM!
                         |
                         v
Container Memory Limit (2GB) Exceeded -> [Linux Kernel OOM Killer sends SIGKILL]
FastAPI backend terminates abruptly; all active chat sessions killed!
```

* **The Unique Edge Case:** Unbounded raster allocation during document ingestion.
* **Why it happens:** In Task `RO-7.2` & `RO-7.3`, processing scanned documents or `.docx` embedded images via Tesseract OCR allocates uncompressed raw pixel buffers in Pillow. Large documents will spike memory past container limits, crashing the entire application server.
* **Mitigation:**
  Enforce strict ingestion guardrails: max 10 images per document, resize rasters to a max width of 1200px before running OCR, and run OCR in a separate process/worker with memory limits.

---

### Roadblock 9: Conversational Context Token Explosion on Fast/Free LLM Models

```text
Turn 1: User asks 200-word question -> Bot answers with 400 words
Turn 2: User asks 200-word question -> Bot answers with 400 words
...
Turn 6: Session Memory buffer has accumulated 6 turns = ~3,600 tokens
           +
Retrieved RAG Evidence context from ChromaDB (4 chunks) = ~3,000 tokens
           +
System Prompt + Guardrails + Relevance Prompts = ~600 tokens
           =
TOTAL PROMPT SIZE = 7,200 tokens!
           |
           v
Model configured: Groq (llama-3.1-8b-instant, TPM limit: 6,000 tokens/min)
Result: HTTP 429 Rate Limit / HTTP 400 Context Length Exceeded!
Outage Fallback activates on every single message after Turn 4!
```

* **The Unique Edge Case:** Sliding history window ($k=6$) combined with large RAG contexts exceeding model token limits.
* **Why it happens:** Task `AK-1.1` implements a sliding buffer of 6 turns. If both user and bot generate detailed responses, the chat history alone can consume 4,000+ tokens. When prepended to 4 RAG chunks, the total prompt exceeds provider limits (e.g. Groq free tier rate limits of 6,000 TPM or local model context limits), triggering constant provider failures.
* **Mitigation:**
  Prune conversation history based on **token count** rather than turn count: cap conversation history to a maximum of 1,000 tokens, summarizing older turns rather than storing full text.

---

### Roadblock 10: ChromaDB Concurrent Access File Locking Between Ingestion and Chat

```text
Thread A (HR Admin in Streamlit):
Uploads new Leave_Policy.docx -> provisioner.py calls store.add_documents()
           |
           v
ChromaDB acquires write lock on .chroma/chroma.sqlite3
           |
           +-------------------> [DB WRITE IN PROGRESS (takes 1.5 seconds)]
                                              |
Thread B (Employee in Chat):                  |
Asks "How many casual leaves do I get?"       |
QueryOrchestrator calls store.query()         |
Attempts to acquire read lock on SQLite       |
                                              v
                              [sqlite3.OperationalError: database is locked]
                              Vector retrieval fails -> Bot returns empty answer!
```

* **The Unique Edge Case:** ChromaDB’s embedded SQLite backend locking up under concurrent write/read operations.
* **Why it happens:** In embedded mode, ChromaDB uses SQLite for metadata and SQLite locks the entire database file during writes. If an HR administrator uploads a document while employees are actively chatting with the bot, concurrent queries will crash with `database is locked`.
* **Mitigation:**
  Configure SQLite connection timeout in Chroma (`timeout=30.0`), use a write-queue for document provisioning, or run ChromaDB as a standalone client-server service (`chroma run --path .chroma`) rather than embedded file mode.

---

### Summary Risk Matrix for Sprint Planning

| # | Roadblock Area | Primary Owner | Severity | Sprint Phase | Immediate Preemptive Action |
| :-: | :--- | :--- | :---: | :---: | :--- |
| **1** | **Cold-Start 30s Timeout** | Architecture / AB | **CRITICAL** | Now (Phase 2/3) | Wrap `init_orchestrator()` in `asyncio.to_thread`. |
| **2** | **Multi-Worker Cache Corruption** | Abhinav (AB-4/AB-14) | **HIGH** | Phase 3 | Implement atomic temporary file replacement (`os.replace`). |
| **3** | **RBAC Scope Leakage via Cache** | Abhinav (AB-4/AB-3.4) | **CRITICAL** | Phase 3 | Namespace cache keys with `authorized_project_ids` hash. |
| **4** | **Hot File Merge Carnage** | All Teammates | **HIGH** | Phase 4 | Strictly enforce sequential merge gates (4.1 -> 4.2 -> 4.3). |
| **5** | **Cross-Encoder CPU Spikes** | Neha (NE-5.1) | **MEDIUM** | Phase 3 | Cap candidates to 8 and set a 500ms fallback timeout. |
| **6** | **Quality Gate False Positives** | Abhinav (AB-5.1) | **MEDIUM** | Phase 3 | Narrow regex refusal patterns to target documents/records only. |
| **7** | **Teams ASGI Loopback Deadlock** | Akaash (AK-2.3) | **CRITICAL** | Phase 3 | Invoke `QueryOrchestrator` directly in-process; avoid HTTP. |
| **8** | **OCR Out-Of-Memory Crashes** | Roshan (RO-7.2) | **HIGH** | Phase 3 | Downsample image resolution and cap pages per upload. |
| **9** | **Context Token Window Exceeded** | Akaash (AK-1.1) | **MEDIUM** | Phase 3/4 | Token-bounded history buffer instead of fixed 6 turns. |
| **10**| **ChromaDB SQLite File Locking** | Architecture | **HIGH** | Phase 3/5 | Configure SQLite busy timeout to 30s. |
