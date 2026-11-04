# 🧠 Code-Grinder Deep Dive: Cache + LLM Stack

> **Mode**: Topic Driller — the full caching hierarchy and LLM client chain, every algorithm annotated.

---

## 🗺️ The Territory

```
app/
├── core/
│   └── cache_quality.py          (71 lines)  — Negative-response gate (cross-cutting)
├── infrastructure/
│   ├── llm/
│   │   ├── prompt_cache.py        (140 lines) — Semantic LRU cache for LLM prompts
│   │   ├── fallback_llm_provider.py (73 lines) — Primary → Fallback orchestrator
│   │   ├── openrouter_client.py   (224 lines) — Primary LLM (Claude 3.5 via HTTP)
│   │   └── groq_client.py          (71 lines) — Fallback LLM (Llama 3.1 via HTTP)
│   ├── faq/
│   │   └── faq_similarity_cache.py (176 lines) — Numpy matrix cosine search
│   └── cache/
│       ├── quality_aware_cache.py (1196 lines) — RBAC + TTL + quality-gated cache
│       └── dual_cache.py          (468 lines)  — LangCache + JSON fallback
└── use_cases/chat/
    └── rag_context_builder.py     (220 lines) — Prompt assembly from RAG chunks
```

### The Settings That Control Everything

```python
# app/core/settings.py — cache and LLM knobs
EMBEDDING_MODEL         = "sentence-transformers/all-MiniLM-L6-v2"  # shared by ALL caches + vector store

# Prompt LRU cache (PromptLRUCache)
LLM_CACHE_SIZE              = 128       # max entries
LLM_CACHE_SIMILARITY_THRESHOLD = 0.70  # semantic hit threshold

# FAQ similarity cache
FAQ_SIMILARITY_CACHE_ENABLED = True
FAQ_SIMILARITY_THRESHOLD    = 0.92     # strict: must be very similar
FAQ_JSON_PATH               = "data/faqs.json"

# Quality-aware semantic cache (InMemoryQualityAwareCache)
SEMANTIC_CACHE_SIMILARITY_THRESHOLD = ?  # per settings

# RAG retrieval quality
RAG_DISTANCE_THRESHOLD  = 0.60   # absolute max vector distance to include a chunk
RAG_DISTANCE_RELAXATION = 0.05   # relax past best distance by this amount
RAG_MIN_DISTANCE_GAP    = 0.10   # quality cliff detection gap
RAG_CANDIDATE_COUNT     = 8      # how many candidates to fetch from ChromaDB
RAG_MAX_EVIDENCE        = 4      # max chunks to include in context
RAG_MAX_CONTEXT_CHARS   = 12000  # total char budget for context window

# LLM providers
LLM_MODEL   = "openrouter/anthropic/claude-3.5-sonnet"  # primary
GROQ_MODEL  = "llama-3.1-8b-instant"                    # fallback
```

---

## 🏗️ The 5-Layer Cache Hierarchy

These caches are checked in a strict priority order — only on a complete miss at every layer does an LLM API call happen.

```
Incoming question
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 0: References Follow-up Gate                            │
│  (_pending_citations dict in QueryOrchestrator)                 │
│  Hit: return stored citations, 0 API calls, ~0ms               │
└──────────────────────────┬──────────────────────────────────────┘
                           │ MISS
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: Response Cache (optional, QueryOrchestrator)          │
│  (DualCache / InMemoryQualityAwareCache — exact or semantic key) │
│  Hit: return cached {answer, citations}, ~1ms                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │ MISS
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2: FAQSimilarityCache                                    │
│  (numpy matrix @ query_vec — vectorized cosine over all FAQs)   │
│  Threshold: 0.92 (very strict)                                  │
│  Hit: return FAQ answer, 0 API calls, ~5-20ms                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │ MISS
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: PromptLRUCache (inside FallbackLLMProvider)           │
│  (OrderedDict LRU, exact + semantic similarity)                 │
│  Threshold: 0.70 (looser than FAQ)                              │
│  Hit: return cached LLM response, 0 API calls, ~10-50ms         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ MISS
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4: LLM API Calls                                         │
│  FallbackLLMProvider:                                           │
│    1. Try OpenRouterClient (Claude 3.5) → ~500-2000ms           │
│    2. On LLMProviderError: Try GroqClient (Llama 3.1) → ~200ms  │
│    3. On both fail: raise LLMProviderError                      │
│  Store result in PromptLRUCache for future hits                 │
└─────────────────────────────────────────────────────────────────┘
```

**Total latency range:**
| Cache Layer | Latency | LLM Calls |
|------------|---------|-----------|
| Layer 0 (pending citations) | ~0ms | 0 |
| Layer 1 (response/quality cache) | ~1ms | 0 |
| Layer 2 (FAQ similarity) | ~5-20ms | 0 |
| Layer 3 (prompt LRU) | ~10-50ms | 0 |
| Layer 4 (primary LLM) | ~500-2000ms | 1 |
| Layer 4 (fallback LLM) | ~700-2500ms | 2 |

---

## 🚪 The Cross-Cutting Gate: `cache_quality.py` (71 lines)

This module is imported by EVERY cache layer. It is the single enforcement point that prevents "not found" responses from being cached and served to future users.

```python
_NEGATIVE_RESPONSE_PATTERNS = [
    # Pattern 1: "could not find / cannot locate / failed to retrieve"
    re.compile(r"\b(?:could not|cannot|can't|unable to|failed to)\s+(?:find|locate|retrieve|...)\b", re.IGNORECASE),

    # Pattern 2: "no relevant information / no documents / no guidance"
    re.compile(r"\bno\s+(?:relevant\s+|specific\s+|...)?(?:information|details?|data|documents?|...)\b", re.IGNORECASE),

    # Pattern 3: "not found/mentioned/covered in the provided documents"
    re.compile(r"\bnot\s+(?:found|mentioned|covered|...)\s+(?:in|within)\s+...(?:documents?|handbooks?|context|files?)\b", re.IGNORECASE),

    # Pattern 4: "does not contain / doesn't mention any information"
    re.compile(r"\b(?:does not|doesn't|...)\s+(?:contain|mention|provide|...)\s+...(?:information|details?|...)\b", re.IGNORECASE),

    # Pattern 5: access-denied responses
    re.compile(r"\brelevant information exists in a (?:project\s+)?document that you do not\s+(?:currently\s+)?have access to", re.IGNORECASE),

    # Pattern 6: "no specific document references are available"
    re.compile(r"\bno\s+specific\s+document\s+references\s+are\s+available\b", re.IGNORECASE),
]

def is_negative_response(text: Optional[str]) -> bool:
    """Never cache: refusals, non-answers, empty responses, access-denied messages."""
    if text is None: return True        # None is always negative
    if not text.strip(): return True    # Empty string is always negative
    normalized = re.sub(r"\s+", " ", text).strip()
    return any(pattern.search(normalized) for pattern in _NEGATIVE_RESPONSE_PATTERNS)
```

**Why Pattern 5 is special**: The access-denied response ("Relevant information exists in a document that you do not currently have access to") is a USER-SCOPED answer. User A can't access project X. User B CAN. If we cached User A's "access denied" answer, User B would get a wrong answer. Pattern 5 prevents this from being cached at ALL.

---

## ⚡ Layer 2: `FAQSimilarityCache` — Vectorized Startup (176 lines)

### Startup: Batch Embed Everything

```python
def __init__(self, faq_path=None, threshold=FAQ_SIMILARITY_THRESHOLD, ...):
    # Step 1: Load JSON
    faqs = json.loads(path.read_text(encoding="utf-8"))
    # faqs = [{"id": "f1", "question": "What is the leave policy?", "answer": "18 days..."}, ...]

    # Step 2: Load model ONCE
    model = SentenceTransformer(model_name)   # e.g., "all-MiniLM-L6-v2"

    # Step 3: Batch encode ALL questions at startup
    questions = [entry["question"] for entry in faqs]
    raw: np.ndarray = model.encode(
        questions,
        convert_to_numpy=True,
        normalize_embeddings=True,    # ← Unit-normalize: |v| = 1
        show_progress_bar=False,
    )
    # raw.shape = (N_faqs, embedding_dim)  e.g., (50, 384)

    self._entries = list(faqs)
    self._matrix = raw.astype(np.float32)   # Store as float32 matrix
    self._model = model                     # Reuse for queries
```

### Search: One Matrix Multiply

```python
def _search(self, question: str) -> Optional[dict]:
    # Step 1: Encode the incoming question (1 vector)
    query_vec = self._model.encode(
        [question],
        convert_to_numpy=True,
        normalize_embeddings=True,    # ← Unit-normalize query too
    )[0].astype(np.float32)           # shape: (384,)

    # Step 2: Cosine similarity for ALL FAQs in one operation
    # Because BOTH matrix rows AND query_vec are unit-normalized:
    #   cos(a, b) = dot(a, b) / (|a| * |b|) = dot(a, b) / (1 * 1) = dot(a, b)
    scores: np.ndarray = self._matrix @ query_vec   # (N,384) @ (384,) = (N,)
    # scores[i] = cosine_similarity(faq_question[i], incoming_question)

    # Step 3: Find best match
    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])

    # Step 4: Threshold gate
    if best_score >= self.threshold:   # 0.92 by default
        return {**self._entries[best_idx], "similarity": round(best_score, 4)}
    return None    # MISS
```

**Why `@` operator is cosine similarity here:**

When you normalize a vector to unit length (`normalize_embeddings=True`), its magnitude becomes 1. Cosine similarity is `dot(a, b) / (|a| · |b|)`. With both magnitudes = 1, this simplifies to just `dot(a, b)`. The `@` operator IS the dot product for numpy arrays. **Zero division, zero sqrt, zero loops** — pure BLAS-optimized matrix multiply.

**Why threshold = 0.92 (strict)?**

FAQs have canonical, pre-written answers. We only want to serve them when the match is near-perfect. At 0.92, a question like "How many annual leave days per year?" (0.95 similar to "How many annual leave days do we get?") would hit. "Tell me about the leave encashment policy" (0.75 similar) would miss and fall through to RAG. The FAQ cache is about **precision** not recall.

---

## 🔒 Layer 3: `PromptLRUCache` — Two-Mode Semantic LRU (140 lines)

### Data Structure

```python
self._entries: OrderedDict[str, tuple[str, list[float]]] = OrderedDict()
#              key: JSON-serialized messages     value: (response_text, embedding_vector)
```

`OrderedDict` is Python's built-in ordered dict. It tracks insertion order. Two operations make it an LRU:
- `move_to_end(key)` → promotes entry to "most recent"
- `popitem(last=False)` → removes "least recently used" entry

### `get()` — Two-Phase Search

```python
def get(self, messages) -> Optional[str]:
    if self.maxsize == 0:
        return None   # Cache disabled (maxsize=0 is a valid "off switch")

    key = self.make_key(messages)   # JSON serialize the messages list

    # ── PHASE 1: Exact match (O(1) hash lookup) ──────────────────────
    with self._lock:
        entry = self._entries.get(key)
        if entry is not None:
            self._entries.move_to_end(key)   # Promote to MRU position
            self._hits += 1
            return entry[0]   # entry = (response_text, vector) → return text

    # ── PHASE 2: Semantic similarity (O(N) scan) ──────────────────────
    # Note: _embed() is OUTSIDE the lock — it's slow (model inference)
    query_vector = self._embed(key)   # Generate embedding for incoming query

    with self._lock:   # Re-acquire lock for the scan
        best_key = None
        best_score = 0.0
        for cached_key, (_, cached_vector) in self._entries.items():
            score = self._cosine_similarity(query_vector, cached_vector)
            if score > best_score:
                best_key = cached_key
                best_score = score

        if best_key is not None and best_score >= self.similarity_threshold:  # 0.70
            self._entries.move_to_end(best_key)   # Promote matched key
            self._hits += 1
            return self._entries[best_key][0]

        self._misses += 1
        return None   # Both phases missed
```

**The lock-release between phases is intentional:**

`_embed()` calls `SentenceTransformer.encode()` — this can take 20-100ms on first call (model loading) and 5-20ms on subsequent calls. Holding `_lock` during this would block ALL other threads from reading the cache. By releasing the lock during embedding, other threads can still do fast exact-match lookups concurrently.

**The cost of this pattern**: Between Phase 1 miss and Phase 2 start, another thread could add an entry. The Phase 2 scan might miss it or find a slightly stale state. This is an **acceptable race** — worst case: a semantic miss that gets added 50ms later. Cache correctness doesn't require 100% consistency.

### `_embed()` — Lazy Model Loading + Smart Text Extraction

```python
def _embed(self, key: str) -> list[float]:
    if self._embedder is not None:
        return list(self._embedder(key))   # Injected custom embedder (for tests)

    # Smart extraction: only embed the USER message content, not the system prompt
    try:
        parsed = json.loads(key)
        if isinstance(parsed, list):
            embed_text = " ".join(
                message.get("content", "")
                for message in parsed
                if isinstance(message, dict) and message.get("role") == "user"
            ) or key
    except (TypeError, ValueError):
        embed_text = key

    # Lazy model loading: SentenceTransformer loads only on first cache miss
    if self._embedding_model is None:
        self._embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    return self._embedding_model.encode(embed_text, convert_to_numpy=True).tolist()
```

**Why only embed user messages?** The `messages` list includes the full system prompt (200-500 tokens). Two queries that differ only in their long system prompt but have the same user question should be considered semantically equivalent. Extracting only user content gives a more meaningful similarity signal.

### `make_key()` — Deterministic Serialization

```python
@staticmethod
def make_key(messages: Any) -> str:
    if isinstance(messages, str):
        return messages
    return json.dumps(messages, sort_keys=True, separators=(",", ":"))
    #                            ↑ sort_keys ensures field order is irrelevant
    #                                         ↑ compact (no spaces) → smaller, faster hashing
```

`sort_keys=True` is critical. Without it, `{"role": "user", "content": "hi"}` and `{"content": "hi", "role": "user"}` would produce different keys for identical messages.

### `put()` — Store with Eviction

```python
def put(self, messages, response: str) -> None:
    if self.maxsize == 0: return

    key = self.make_key(messages)
    vector = self._embed(key)    # Generate embedding BEFORE acquiring lock

    with self._lock:
        self._entries[key] = (response, vector)
        self._entries.move_to_end(key)   # Mark as most recently used

        # LRU eviction loop
        while len(self._entries) > self.maxsize:
            self._entries.popitem(last=False)   # Remove least recently used
```

`popitem(last=False)` removes the FIRST item in the OrderedDict — the one that was `move_to_end()`'d longest ago. The eviction loop runs until the cache is within `maxsize`.

### Pure Python Cosine Similarity

```python
@staticmethod
def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))    # dot product
    left_norm = math.sqrt(sum(v * v for v in left))         # |left|
    right_norm = math.sqrt(sum(v * v for v in right))       # |right|
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)
```

**Why NOT numpy here** (vs `FAQSimilarityCache`): The LRU cache stores individual `list[float]` vectors — not a matrix. It can't pre-normalize because new entries arrive one at a time. Each similarity check computes one vector pair. The overhead of numpy for a single vector-pair operation vs. pure Python is negligible; `FAQSimilarityCache` benefits from numpy because it computes N similarities at once.

---

## 🌟 Layer 1: `InMemoryQualityAwareCache` — The Full-Featured Cache (1196 lines)

This is the most feature-complete cache in the codebase. It wraps everything with:

1. **TTL expiration** — entries auto-expire after `ttl_seconds` (default 3600s)
2. **LRU eviction** — oldest-accessed entry removed when `max_entries` exceeded
3. **Semantic similarity search** — numpy dot product across stored key embeddings
4. **RBAC isolation** — entries scoped to roles, projects, or documents
5. **Document freshness** — if a cited document is updated, the cached answer is evicted
6. **Quality gate** — `CacheQualityValidator` decides whether a response is worth caching

### The RBAC Access Control

```python
def _check_rbac_access(self, entry, role=None, roles=None, project_ids=None, document_ids=None, is_admin=False) -> bool:
    if is_admin: return True    # Admins bypass all restrictions

    entry_role = entry.assigned_role       # Role this answer was generated for
    entry_docs = entry.document_ids        # Documents cited in this answer
    entry_projs = entry.project_ids        # Projects the docs belong to

    # Public entries with no restrictions: always accessible
    if entry.is_public and not entry_role and not entry_docs and not entry_projs:
        return True

    caller_roles = {r.lower() for r in ([role] if role else []) + list(roles or [])}

    if "admin" in caller_roles:
        return True

    # 1. Role check: answer must be for caller's role (or less restricted)
    if entry_role and entry_role.lower() not in caller_roles:
        return False   # ← RBAC DENIAL

    # 2. Project check: caller must be authorized for at least one of the entry's projects
    if entry_projs and project_ids is not None:
        caller_projs = {p.lower() for p in project_ids}
        if not ({p.lower() for p in entry_projs} & caller_projs):
            return False   # ← No project overlap

    # 3. Document check: caller must be authorized for ALL documents cited
    if entry_docs and document_ids is not None:
        caller_docs = {d.lower() for d in document_ids}
        for edoc in entry_docs:
            if edoc.lower() not in caller_docs:
                return False   # ← One unauthorized document = deny all

    return True
```

**The asymmetric document rule**: A cache miss due to RBAC returns `None` — it triggers a fresh RAG + LLM call scoped to the user's actual authorization. The result of THAT call is stored as a NEW cache entry with the user's `assigned_role` + `document_ids`. Over time, each role/user builds up its own scoped cache entries.

### The Quality Gate — C.R.E.A.T.E. Framework

```python
class CacheQualityValidator:
    """C.R.E.A.T.E. quality gate:
    - Distance Score Thresholds: <0.60 STRONG, 0.60-0.70 BORDERLINE, 0.70-0.85 WEAK, >=0.85 INVALID
    - Lexical Grounding Target: >= 0.20
    - Separation Gap Target: >= 0.10
    - Evidence Count: >= 1 for RAG
    - Confidence: >= 0.60
    - Negative response: never cache
    """

    def validate(self, query, response, confidence, evidence_count, evidence_distances, ...) -> QualityValidationResult:
        # Gate 1: Non-empty
        if not response.strip():
            return FAIL("Empty or whitespace response cannot be cached")

        # Gate 2: Confidence floor
        if confidence < self.min_confidence_threshold:   # default 0.60
            return FAIL(f"Confidence {confidence:.2f} below threshold")

        # Gate 3: Retrieval distance quality
        if evidence_distances:
            min_dist = min(evidence_distances)
            level = self.classify_distance(min_dist)
            # INVALID (>= 0.85): fail. WEAK (0.70-0.85): allowed but flags borderline.
            if level == EvidenceQualityLevel.INVALID or min_dist >= self.max_distance_threshold:
                return FAIL(f"Best distance {min_dist:.3f} is INVALID")

        # Gate 4: RAG needs evidence
        if self.require_evidence_for_rag and source == RAG_GENERATED and evidence_count < 1:
            return FAIL("RAG requires at least 1 evidence chunk")

        # Gate 5: Lexical grounding (fraction of response words found in context)
        if lexical_grounding is not None and lexical_grounding < self.min_lexical_grounding:
            # If allow_review=True: REVIEW (still cached but flagged)
            # If allow_review=False: FAIL (not cached)
            ...

        # Gate 6: Separation gap (quality cliff between evidence chunks)
        if separation_gap < self.min_separation_gap:
            # Just a warning — doesn't reject

        # Gate 7: Negative response check
        if is_negative_response(response):
            return FAIL("Negative/unverified response cannot be cached")

        return PASS
```

**`EvidenceQualityLevel` classification:**

```python
@staticmethod
def classify_distance(distance: float) -> EvidenceQualityLevel:
    if distance < 0.60:   return STRONG      # High confidence retrieval
    elif distance < 0.70: return BORDERLINE  # Usable but marginal
    elif distance < 0.85: return WEAK        # Risky — may be off-topic
    else:                 return INVALID     # Should not be used
```

Remember: ChromaDB returns **distance** (lower = more similar). A distance of 0.85 means the retrieved chunk is only marginally related to the query.

### Document Freshness Check (in `get()`)

```python
def get(self, cache_key, ..., document_timestamps=None):
    ...
    entry = self._cache.get(cache_key)   # or semantic match

    # Check TTL
    if entry.is_expired(self.ttl_seconds):
        self._remove_entry(cache_key); return None

    # RBAC check
    if not self._check_rbac_access(entry, ...): return None

    # Document freshness check
    if entry.metadata.doc_last_updated and document_timestamps:
        for doc_id, cached_ts in entry.metadata.doc_last_updated.items():
            current_ts = document_timestamps.get(doc_id)
            if current_ts and current_ts > cached_ts:
                # Document was updated AFTER this answer was cached → stale!
                self._remove_entry(cache_key)
                self._stats["stale_document_evictions"] += 1
                logger.info("Stale cache entry evicted: doc %s updated", doc_id)
                return None
```

When a new document version is uploaded, any cached answer that cited that document is immediately invalidated on the next access. The `doc_last_updated` dict in `CacheEntryMetadata` stores `{document_id: timestamp_float}` for each cited document.

---

## 🔁 The DualCache — Resilient Persistence (468 lines)

```
get(cache_key, original_query):
    1. Try LangCache (external distributed semantic cache)
       ├── Available + query provided → langcache.search(prompt=original_query)
       ├── Hit → return DualCacheEntry(source="langcache")
       └── Miss / unavailable → continue
    2. Try JSONLocalCache (in-memory dict + JSON file on disk)
       ├── Hit with is_negative_response → evict from JSON + return None
       ├── Hit (valid) → return DualCacheEntry(source="json")
       └── Miss → return None

put(cache_key, original_query, response, ...):
    1. is_negative_response(response) → SKIP write entirely
    2. Try LangCache.set(prompt, response)  → may fail silently
    3. JSONLocalCache.put(entry) → ALWAYS written (fallback guarantee)
    4. Atomic write: json.dump → temp file → os.replace
```

### The Background Sync Thread

```python
def _start_sync_thread(self) -> None:
    def sync_loop():
        while True:
            time.sleep(self._sync_interval)   # default 60 seconds
            try:
                self._sync_json_to_langcache()
            except Exception as e:
                logger.error("dual_cache sync failed: %s", e)

    thread = threading.Thread(target=sync_loop, daemon=True)
    thread.start()
    # daemon=True: the thread dies automatically when the main process exits
    # No cleanup needed — no risk of blocking shutdown
```

**Why daemon thread**: A non-daemon thread would keep the Python process alive even after uvicorn shuts down. `daemon=True` means the OS can terminate this thread at any time when the main thread exits. Since `sync_json_to_langcache()` is non-critical (LangCache is optional), losing a sync in-progress on shutdown is acceptable.

### The Singleton Pattern — Double-Checked Locking

```python
_dual_cache: Optional[DualCache] = None
_dual_cache_lock = threading.Lock()

def get_dual_cache(langcache_config=None, json_fallback_path=None) -> DualCache:
    global _dual_cache
    if _dual_cache is None:               # Fast path: check without lock
        with _dual_cache_lock:
            if _dual_cache is None:       # Slow path: re-check INSIDE lock
                _dual_cache = DualCache(...)
    return _dual_cache
```

This is **double-checked locking** — the classic pattern for lazy singletons. The first check avoids acquiring the lock on every call (lock is expensive when there's contention). The second check inside the lock prevents two threads that both passed the first check from both creating a `DualCache`.

---

## 🤖 The LLM Clients

### `GroqClient` — The Minimal Fallback (71 lines)

```python
class GroqClient(LLMProvider):
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
    # ↑ OpenAI-compatible API. Same JSON shape as OpenAI's endpoint.

    def __init__(self, api_key=GROQ_API_KEY, model=GROQ_MODEL, timeout=60.0, max_tokens=400):
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        # Persistent httpx.Client: TCP/TLS handshake done ONCE per server lifecycle
        # vs. requests.get() which creates a new connection every time

    def generate(self, messages) -> str:
        if not self.api_key:
            raise LLMProviderError("GROQ_API_KEY is not configured.")

        payload = {"model": self.model, "messages": messages, "max_tokens": self.max_tokens}

        response = self._client.post(self.BASE_URL, json=payload)

        if response.is_error:
            # ← SANITIZE before logging — strips "Bearer gsk_abc123" from error body
            raise LLMProviderError(f"Groq returned HTTP {response.status_code}: {_sanitize_response_body(response.text)}")

        content = response.json()["choices"][0]["message"]["content"]
        if not content:
            raise LLMProviderError("Groq returned an empty response.")
        return content
```

**`_sanitize_response_body()`** — the API-key scrubber:

```python
def _sanitize_response_body(body: str, max_length: int = 1000) -> str:
    sanitized = body[:max_length]   # Truncate first (error bodies can be huge)
    sanitized = re.sub(r"(?i)bearer\s+[a-z0-9._-]+", "Bearer [REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)(?:gsk_|sk-)[a-z0-9_-]+", "[REDACTED_KEY]", sanitized)
    return sanitized
```

**Why `max_length=1000` before regex**: Regex backtracking on very long strings can be O(N²) in worst cases. Truncating to 1000 chars first is a defense against catastrophic backtracking on malicious/unexpected error payloads.

### `OpenRouterClient` — The Full-Featured Primary (224 lines)

Everything in `GroqClient`, plus three features:

**Feature 1: `_strip_reasoning()` — Thinking-model post-processing**

```python
_THINKING_HEADER = re.compile(
    r"^(#+\s*)?"                            # optional markdown heading
    r"(\d+[\.]\s*)?"                        # optional "1."
    r"(\*{1,2})?"                           # optional bold marker
    r"(analyze|analysis|thinking process|"
    r"let me (look|check|find|search)|"
    r"i need to|i will|i must)...",
    re.IGNORECASE,
)

def _strip_reasoning(raw: str) -> str:
    # Step 1: Strip XML think tags: <think>...</think>
    text = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", raw, flags=re.DOTALL).strip()

    # Step 2: Find LAST "thinking header" line
    lines = text.splitlines()
    last_header_idx = -1
    for i, line in enumerate(lines):
        if _THINKING_HEADER.search(line.strip()) or _INSTRUCTION_ECHO.search(line.strip()):
            last_header_idx = i

    if last_header_idx == -1:
        return text   # No thinking headers — return as-is

    # Step 3: Return only what's AFTER the last thinking section
    after = "\n".join(lines[last_header_idx + 1:]).strip()
    if not after:
        # Edge case: thinking was entire output → return last paragraph
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        return paragraphs[-1] if paragraphs else text
    return after
```

**Why "LAST" thinking header?** Some models emit multiple reasoning sections:
```
1. Analyze context
   [reasoning...]
2. Formulate response
   [more reasoning...]
3. Final answer:
   Annual leave is 18 days per year. Would you like references?
```
Taking content after the LAST header correctly extracts "Annual leave is 18 days per year."

**Feature 2: Null-response retry**

```python
raw = data["choices"][0]["message"]["content"]

if not raw:
    # Some models return null when system prompt is too long.
    # Retry with ONLY the last user message (no system prompt).
    payload["messages"] = [{"role": "user", "content": payload["messages"][-1]["content"]}]
    response = self._client.post(self.BASE_URL, json=payload)
    data = response.json()
    raw = data["choices"][0]["message"]["content"]

if not raw:
    raise LLMProviderError("OpenRouter returned an empty response.")
```

**Feature 3: Token tracking pipeline**

```python
def generate(self, messages) -> str:
    response = self._client.post(...)
    data = response.json()
    raw = data["choices"][0]["message"]["content"]
    
    self._track_tokens(data)         # → TokenTracker singleton
    self._add_tokens_to_langsmith(data)  # → LangSmith run metadata
    
    return _strip_reasoning(raw)

def _track_tokens(self, response_data: dict) -> None:
    usage = response_data.get("usage", {})
    tracker = get_token_tracker()    # ← Module-level singleton
    tracker.track(
        model=self.model,
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        session_id=self.session_id,
        cache_hit=False,
        provider="openrouter",
    )
```

---

## 📊 The Token Tracker — In-Process Analytics (352 lines)

```python
class TokenTracker:
    """Thread-safe in-memory history of all LLM calls."""

    def __init__(self, max_history: int = 10000):
        self._lock = Lock()               # threading.Lock (not RLock — no reentrant use)
        self._history: List[TokenUsage] = []

    def track(self, model, prompt_tokens, completion_tokens, session_id, cache_hit, provider) -> TokenUsage:
        usage = TokenUsage(
            timestamp=datetime.now(),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            session_id=session_id,
            cache_hit=cache_hit,
            provider=provider,
        )
        with self._lock:
            self._history.append(usage)
            if len(self._history) > self.max_history:
                self._history = self._history[-self.max_history:]   # Trim oldest
        return usage
```

**The trim operation `self._history[-max_history:]`** creates a new list of the last N items. This is O(N) — for `max_history=10000`, this only fires once every 10000 calls, so the amortized cost is O(1). Alternative: `collections.deque(maxlen=10000)` would be O(1) always, but `list` is fine at this scale.

**Aggregation methods — O(N) scans:**

```python
def get_by_model(self, model: str) -> AggregatedTokens:
    aggregated = AggregatedTokens()
    with self._lock:
        for usage in self._history:
            if usage.model == model:
                aggregated.update(usage)   # Adds tokens, updates averages
    return aggregated

def get_all_models(self) -> Dict[str, AggregatedTokens]:
    stats_by_model = defaultdict(AggregatedTokens)
    with self._lock:
        for usage in self._history:
            stats_by_model[usage.model].update(usage)
    return dict(stats_by_model)
```

**`AggregatedTokens.update()`** maintains running totals and recalculates averages inline:

```python
def update(self, usage: TokenUsage) -> None:
    self.total_tokens += usage.total_tokens
    self.prompt_tokens += usage.prompt_tokens
    self.completion_tokens += usage.completion_tokens
    self.call_count += 1
    if usage.cache_hit:
        self.cached_calls += 1
    if self.call_count > 0:
        self.avg_tokens_per_call = self.total_tokens / self.call_count
        self.avg_prompt_tokens = self.prompt_tokens / self.call_count
        self.avg_completion_tokens = self.completion_tokens / self.call_count
```

**The singleton pattern** uses lazy initialization (no double-checked locking):

```python
_global_tracker: Optional[TokenTracker] = None

def get_token_tracker() -> TokenTracker:
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = TokenTracker()
    return _global_tracker
```

This is safe in CPython because the GIL prevents two threads from simultaneously executing the `if` check and the assignment. In a GIL-free Python (e.g., future free-threaded Python), this would need double-checked locking.

---

## 📝 `RAGContextBuilder` — The Prompt Assembler (220 lines)

This is where retrieved document chunks become an LLM-ready prompt.

```python
def build_messages(self, question, context_chunks, include_system_prompt=True) -> list[dict]:
    messages = []
    if include_system_prompt:
        messages.append({"role": "system", "content": self.build_system_prompt()})
    messages.append({"role": "user", "content": self.build_user_prompt(question, context_chunks)})
    return messages
```

**`build_system_prompt()`** — the behavioral contract:

```python
return (
    "You are a helpful HR assistant. Your role is to provide accurate answers "
    "based exclusively on the HR policy documents provided to you.\n\n"
    "Guidelines:\n"
    "- Answer ONLY using the provided document context\n"
    "- Be concise (2-4 sentences)\n"
    "- If information is not in the context, say 'I could not find that information...'\n"
    "- Do not add external knowledge or assumptions\n"
    "- End with: 'Would you like to see the references for this?'"
)
```

> [!IMPORTANT]
> The phrase "I could not find that information in the available documents" is INTENTIONALLY specified here, because `is_negative_response()` in `cache_quality.py` detects this exact phrase and blocks it from being cached. The system is designed so that the LLM's "not found" answer is always freshly generated, never served from cache.

**`build_user_prompt()`** — the context assembly with budget enforcement:

```python
def build_user_prompt(self, question, context_chunks, include_references=True) -> str:
    formatted_chunks = []
    total_chars = 0

    for i, chunk in enumerate(context_chunks, 1):
        text = chunk.get("text", "").strip()
        if not text: continue

        chunk_lines = []
        if self.include_metadata and "metadata" in chunk:
            section = chunk["metadata"].get("section", f"Section {i}")
            chunk_lines.append(f"[{section}]")   # e.g., "[19.3 Leave Application Process]"
        chunk_lines.append(text)
        if "distance" in chunk:
            chunk_lines.append(f"(relevance: {1 - chunk['distance']:.2%})")  # 0.3 dist → "70.00% relevant"

        chunk_text = "\n".join(chunk_lines)

        # Budget gate — stop adding chunks if over limit
        if total_chars + len(chunk_text) > self.max_context_chars:   # 12000 chars
            break

        formatted_chunks.append(chunk_text)
        total_chars += len(chunk_text) + 2   # +2 for separator

    context = "\n\n".join(formatted_chunks)

    return "\n".join([
        "Document Context:",
        "=" * 50,
        context,
        "=" * 50,
        f"\nQuestion: {question}",
        "\nInstructions: Answer using ONLY the document context above. "
        "Write 2-4 sentences. No analysis — just the answer. "
        "End with: 'Would you like to see the references for this?'",
    ])
```

The `"=" * 50` separator visually separates context from question in the LLM's attention. Models attend to structure — this visual delineation helps prevent the LLM from conflating context and instructions.

---

## 📐 Cross-Cutting Cache Patterns

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Negative-response gate** | All 4 cache write paths | Never cache "not found" or "access denied" answers |
| **`normalize_embeddings=True`** | FAQSimilarityCache, QualityAwareCache | Unit-normalize → dot product = cosine similarity |
| **`matrix @ query_vec`** | FAQSimilarityCache, QualityAwareCache | BLAS-vectorized N-similarity in one op |
| **Lazy model loading** | PromptLRUCache, QualityAwareCache | SentenceTransformer loads only on first miss |
| **Lock-release during embedding** | PromptLRUCache.get() | Avoids holding lock during slow model inference |
| **`OrderedDict` + `move_to_end()`** | PromptLRUCache | O(1) LRU promotion without reimplementing linked list |
| **`daemon=True` threads** | DualCache sync thread | Thread dies with process, no shutdown hang |
| **Double-checked locking** | DualCache singleton | Lock-free fast path after initialization |
| **Atomic JSON write** | JSONLocalCache, FAQCache | `write_to_temp → os.replace()` for crash safety |
| **`httpx.Client` (persistent)** | OpenRouterClient, GroqClient | TCP/TLS amortized across many requests |
| **API key sanitization** | GroqClient, OpenRouterClient | Strip Bearer tokens before logging errors |

---

## 🔥 Drill Questions

### Q1: `PromptLRUCache.get()` releases the `_lock` between Phase 1 and Phase 2. Could this cause a bug where the semantic match is stale?

> **A**: Yes, but it's an acceptable race. Between releasing the lock after Phase 1 miss and re-acquiring it for Phase 2, another thread could evict the best match (LRU eviction). When Phase 2 scans, it checks `self._entries.items()` which at that point might not contain the optimal match. The worst outcome: a semantic miss that would have hit with perfect synchrony. The cache would correctly miss and let the LLM generate a response. No corruption, no wrong answers — just a slightly lower cache hit rate. The tradeoff (slow embedding outside lock vs. perfect consistency) is the right call here.

### Q2: `FAQSimilarityCache` uses `normalize_embeddings=True` at both encode-time and query-time. `PromptLRUCache` does NOT normalize. What happens if a PromptLRUCache entry has a very long user message?

> **A**: Long messages produce embeddings with a larger magnitude (sum of squared components is larger). The `_cosine_similarity()` function correctly normalizes by dividing by both norms (`left_norm * right_norm`), so magnitude doesn't affect the cosine score. The issue is different: `PromptLRUCache` embeds the FULL JSON-serialized messages including system prompt. If a short question like "leave policy?" is stored with a 400-token system prompt, its embedding vector is dominated by system-prompt terms. A future query "what is leave?" with a different (shorter) system prompt may fail to match semantically even though the user intent is identical. This is why the `_embed()` method extracts only user-role messages — but it only does this for the ENCODING step, not for how vectors were previously stored. Inconsistency here could cause artificial misses.

### Q3: `InMemoryQualityAwareCache.get()` checks document freshness using `document_timestamps`. Who provides these timestamps?

> **A**: The caller of `.get()` is responsible for providing `document_timestamps: dict[str, float]` — typically the API layer or the `QueryOrchestrator`, which would need to look up current `updated_at` timestamps from the database for documents cited in the cached entry. If the caller doesn't provide `document_timestamps`, the freshness check is skipped (the `if entry.metadata.doc_last_updated and document_timestamps:` condition fails). This means the freshness feature is only active when the caller explicitly opts in with fresh timestamps — it's opt-in by design, not automatic.

### Q4: The `DualCache.put()` skips writing if `is_negative_response(response)` is True. But `get()` also checks and EVICTS negative responses found in the JSON cache. Why have both?

> **A**: Defense in depth. `put()` prevents new negatives from entering. The `get()` eviction handles: (1) entries written before `is_negative_response()` was implemented (legacy data), (2) entries where a response that was valid when written later became classified as negative after a pattern update, (3) corruption or manual JSON edits. The `get()` eviction is a "self-healing" mechanism — as users ask questions, stale negative entries are automatically pruned from the JSON cache on access, keeping the cache clean without requiring a separate maintenance job.

### Q5: `TokenTracker.track()` uses `threading.Lock` (not `RLock`). Could this deadlock?

> **A**: No, because `Lock` can deadlock only if the SAME thread tries to acquire it twice (recursive acquisition). `track()` is a leaf function — it acquires the lock, appends, releases, and returns. It never calls any other function that would try to acquire the same lock. `RLock` is needed only when the same thread might re-enter the locked section (e.g., a logger that triggers another track call). Here, `Lock` is correct and slightly faster than `RLock` (RLock has extra overhead tracking the owning thread).

### Q6: `OpenRouterClient._strip_reasoning()` finds the LAST thinking header and returns everything after it. What if the LLM writes a valid answer header like "**Answer:**" that matches `_THINKING_HEADER`?

> **A**: The `_THINKING_HEADER` regex is carefully scoped. It only matches lines starting with words like "analyze", "analysis", "thinking process", "let me look/check/find/search", "examine", "formulate". The word "Answer" is NOT in the pattern. The `_INSTRUCTION_ECHO` pattern matches lines starting with "- question", "- instructions", "- answer using" — but not a standalone "**Answer:**". A header like "**Answer:**" alone would NOT trigger a match. However, if the LLM wrote "**Let me formulate an answer:**", `formulate` IS in the pattern and WOULD strip the actual answer. This is an edge case the regex doesn't handle perfectly — a more robust approach would be `<answer>...</answer>` XML tags.

### Q7: `PromptLRUCache.maxsize=0` disables the cache. What's the benefit of supporting `maxsize=0` explicitly instead of just not creating a cache?

> **A**: Dependency injection and testability. `FallbackLLMProvider` always receives a `cache: PromptLRUCache | None` parameter. If cache is `None`, the code needs null checks everywhere: `if self.cache: cached = self.cache.get(...)`. With `maxsize=0`, the cache OBJECT exists and `get()` always returns `None` (MISS) — the interface is uniform. Tests can inject `PromptLRUCache(maxsize=0)` to get guaranteed cache-bypass without needing to restructure the dependency. It's the **Null Object pattern at the configuration level** — instead of `None`, use a zero-capacity object that behaves like "always miss".
