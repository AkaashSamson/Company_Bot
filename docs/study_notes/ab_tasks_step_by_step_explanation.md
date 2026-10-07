# KnowLayer V3: Step-by-Step Technical Guide for Abhinav (AB Tasks)

**Target Version:** KnowLayer V3 Enterprise  
**Author / Assignee:** Abhinav (AB)  
**Location:** `docs/study_notes/ab_tasks_step_by_step_explanation.md`  
**Instruction Framework:** `teach-me` | `explainer` | `topic-driller` | `code-grinder`  
**Diagram Format:** Pure ASCII (Renderable anywhere without external plugins)

---

## Master Architecture & Roadmap for Abhinav (AB)

```
+========================================================================================================+
|                                      ABHINAV'S SYSTEM ARCHITECTURE                                     |
+========================================================================================================+
|                                                                                                        |
|   [Inbound Query]                                                                                      |
|          |                                                                                             |
|          v                                                                                             |
|   +------------------------------------------------------------------------------------------------+   |
|   | 1. Query Normalization & Intent Routing                                                        |   |
|   |    - AB-3.1: QueryNormalizer (Casing, boundary fix, clean, hash)                              |   |
|   |    - AB-3.3: SynonymClusterEngine (POS noun tagging, lemmatization, cosine clustering)          |   |
|   |    - AB-3.4: QueryIntentClassifier (PROCEDURAL vs PERSONAL_BALANCE vs POLICY_GENERAL)          |   |
|   +------------------------------------------------------------------------------------------------+   |
|          |                                                                                             |
|          +--------------------------------------+                                                      |
|          | (Cache Key: "intent:hash")           |                                                      |
|          v                                      v                                                      |
|   +---------------------------------------+  +-----------------------------------------------------+   |
|   | 2. Quality-Aware Semantic Cache       |  | 8. Pipeline Tracer (AB-6.1 / AB-6.2 / AB-6.3)        |   |
|   |    - AB-4 & AB-4.2: QualityAwareCache |  |    - 8 Execution Spans (Context, Normalization,     |   |
|   |    - Hit: Instant exit (< 5ms)        |  |      Cache, Retrieval, Rerank, Quality Gate,        |   |
|   |    - Miss: Proceeds to Retrieval      |  |      LLM Generation, Post Guardrails)               |   |
|   +---------------------------------------+  |    - ObservabilityManager dispatch (Langfuse)       |   |
|          | (On Cache Miss)                   +-----------------------------------------------------+   |
|          v                                                              ^                              |
|   +----------------------------------------------------------------+    |                              |
|   | 3. Evidence Quality Gate (AB-5.1 & AB-5.2)                      |    |                              |
|   |    - RetrievalQualityGate: Cosine distance, lexical grounding, |    |                              |
|   |      separation gap (d2 - d1)                                  |    |                              |
|   |    - Hard cutoff: distance >= 0.85 -> INVALID (Early Exit)     |    |                              |
|   |    - STRONG / BORDERLINE -> Proceed to LLM                     |    |                              |
|   +----------------------------------------------------------------+    |                              |
|          |                                                              |                              |
|          v                                                              |                              |
|   +----------------------------------------------------------------+    |                              |
|   | 4. Resilient LLM Layer & Circuit Breaker (AB-1.1, 1.2, AB-2)   |----+                              |
|   |    - AB-2: Standardized LLMResponse & LLMResponseBuilder       |                                   |
|   |    - AB-1.1: ProviderHealthMonitor & ProviderErrorTracker      |                                   |
|   |      (HEALTHY -> DEGRADED -> OPEN -> RECOVERING)               |                                   |
|   |    - AB-1.2: Client Health Integration (OpenRouter / Groq)     |                                   |
|   |    - FallbackLLMProvider: Outage resilient rerouting           |                                   |
|   +----------------------------------------------------------------+                                   |
|          |                                                                                             |
|          v                                                                                             |
|   +------------------------------------------------------------------------------------------------+   |
|   | 5. Cache Validation & Verification Gate                                                        |   |
|   |    - CacheQualityValidator: Validate confidence >= 0.70 & non-negative before cache write     |   |
|   |    - Discards low-grounding or negative responses from cache storage                           |   |
|   +------------------------------------------------------------------------------------------------+   |
|                                                                                                        |
+========================================================================================================+
```

---

## Module 1: Task AB-2 — Standardized LLM Response Contract & Aggregator

**File:** `app/infrastructure/llm/llm_response.py`

### 1.1 `teach-me` (Foundational Intuition)
Imagine running an international cargo logistics hub where different couriers drop off packages. Courier A gives you shipping weights in pounds and delivery receipts as paper invoices. Courier B gives you weights in kilograms and returns status via an SMS webhook. If your warehouse software tries to handle every single courier's peculiar habits across every aisle, your operations will collapse into chaotic spaghetti.

Task **AB-2** creates a **Universal Shipping Standard**: whether a prompt is answered by OpenRouter, Groq, an in-memory mock engine, or a semantic cache hit, the response is wrapped inside an identical `LLMResponse` envelope. It guarantees uniform status codes, exact token measurements, and standardized error messaging.

---

### 1.2 `explainer` (Architectural Flow & State Diagram)
The module establishes immutable enums and strongly-typed data structures:
- `LLMProviderName`: Standardized identifier (`OPENROUTER`, `GROQ`, `UNKNOWN`).
- `LLMResponseStatus`: State indicators (`SUCCESS`, `PARTIAL`, `CACHED`, `FAILED`, `TIMEOUT`, `RATE_LIMITED`).
- `LLMTokenUsage`: Unified token bookkeeping (`prompt_tokens`, `completion_tokens`, `total_tokens`, `cache_hit`).
- `LLMResponseBuilder`: Fluent builder pattern ensuring invariant validation before object instantiation.
- `ResponseAggregator`: Thread-safe sliding window tracking moving averages of latency, throughput, and error rates per provider.

```
       [Raw Provider Response (Groq / OpenRouter / Cache)]
                                |
                                v
                    +-----------------------+
                    |  LLMResponseBuilder   |
                    +-----------------------+
                                |
             +------------------+------------------+
             |                                     |
             v                                     v
   [Valid Generation]                     [Provider Exception]
   - Status: SUCCESS / CACHED             - Status: FAILED / TIMEOUT
   - Latency: end - start                 - Latency: failure elapsed
   - Tokens: (prompt, completion)         - Error: error string
             |                                     |
             +------------------+------------------+
                                |
                                v
                        [ LLMResponse ]
                                |
             +------------------+------------------+
             |                                     |
             v                                     v
  [QueryOrchestrator]                     [ResponseAggregator]
  Returns response to user                Updates rolling stats &
  and Streamlit UI                        p95 latency metrics
```

---

### 1.3 `topic-driller` (Corner Cases, Gotchas & Failure Modes)
1. **The Zero-Total Token Anomaly:**
   - *Problem:* Certain providers or cached responses omit the `total_tokens` field or set it to `0`. If financial telemetry relies on `total_tokens`, costs will be miscalculated.
   - *Defense:* In `LLMTokenUsage.to_dict()`, if `total_tokens == 0`, it dynamically auto-sums `prompt_tokens + completion_tokens`.
2. **Cache Cost Bleed:**
   - *Problem:* When returning a cached response (`LLMResponseStatus.CACHED`), naive implementations might count the cached text tokens as billed completion tokens.
   - *Defense:* Cached responses set `cache_hit=True` in `LLMTokenUsage` and zero out execution latency (`latency_ms=0.0`), isolating cache lookups from provider billing metrics.
3. **Thread-Safe Metric Mutation:**
   - *Problem:* In high-concurrency environments, multiple worker threads calling `ResponseAggregator.record()` simultaneously can induce race conditions on moving averages.
   - *Defense:* The aggregator employs a `threading.Lock()` mutex wrapping window buffer updates and counter increments.

---

### 1.4 `code-grinder` (Concrete Code Breakdown)
In `app/infrastructure/llm/llm_response.py`:

```python
@dataclass
class LLMTokenUsage:
    """Unified token accounting across providers."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_hit: bool = False

    def to_dict(self) -> dict:
        total = self.total_tokens
        if total == 0:
            total = self.prompt_tokens + self.completion_tokens
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": total,
            "cache_hit": self.cache_hit,
        }

@dataclass
class LLMResponse:
    """Standardized response contract for all LLM interactions."""
    content: str
    provider: LLMProviderName
    model_name: str
    status: LLMResponseStatus = LLMResponseStatus.SUCCESS
    token_usage: LLMTokenUsage = field(default_factory=LLMTokenUsage)
    latency_ms: float = 0.0
    error_message: Optional[str] = None
    raw_response: Optional[dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)

    @property
    def is_success(self) -> bool:
        return self.status in (LLMResponseStatus.SUCCESS, LLMResponseStatus.CACHED)
```

The fluent builder pattern enforces clean construction:
```python
response = (
    LLMResponseBuilder()
    .with_provider(LLMProviderName.GROQ)
    .with_model("llama-3.3-70b-versatile")
    .with_content(generated_text)
    .with_tokens(prompt_tokens=120, completion_tokens=42)
    .with_latency(start_timestamp)
    .build()
)
```

---

## Module 2: Tasks AB-1.1 & AB-1.2 — Circuit Breaker & Provider Health Monitoring

**Files:** `app/infrastructure/llm/provider_health.py`, `app/infrastructure/llm/provider_error_tracker.py`, `app/infrastructure/llm/openrouter_client.py`, `app/infrastructure/llm/groq_client.py`

### 2.1 `teach-me` (Foundational Intuition)
When an electrical appliance in your home shorts out, the fuse box circuit breaker snaps open instantly to cut the current. If it didn't, the wiring inside your walls would overheat and catch fire.

In web systems, when an external API like OpenRouter or Groq suffers an outage (returning `503 Service Unavailable` or `429 Too Many Requests`), continuing to send hundreds of user queries will cause requests to pile up, thread pools to exhaust, and the entire application to lock up.
The **Circuit Breaker** automatically cuts off traffic to a failing provider, reroutes queries to a healthy backup provider, and cautiously checks if the primary provider has recovered before restoring full traffic.

---

### 2.2 `explainer` (Architectural Flow & Circuit State Machine)
The system tracks provider states via `HealthStatus`:
- `HEALTHY`: Error rate is normal. All requests pass through.
- `DEGRADED`: Occasional errors or elevated latency. Requests pass through with warnings.
- `OPEN`: Failure threshold exceeded (default: 3 consecutive failures). The breaker trips! All requests are immediately rejected locally without making a network call (`can_execute() -> False`), forcing instant failover.
- `RECOVERING` (Half-Open): Cooldown timer (default: 60s) has elapsed. The breaker allows a single "canary" request through to test the provider.
  - If the canary succeeds $\to$ State transitions to `HEALTHY`.
  - If the canary fails $\to$ State reverts immediately to `OPEN` for another cooldown cycle.

```
                  +---------------------------+
                  |          HEALTHY          |<------------------------+
                  +---------------------------+                         |
                     |                     ^                            |
         Failure > 0 |                     | Consecutive Successes      |
                     v                     |                            |
                  +---------------------------+                         |
                  |         DEGRADED          |                         |
                  +---------------------------+                         |
                     |                                                  |
Consecutive Failures |                                                  |
        >= 3         v                                                  |
                  +---------------------------+                         | Canary
                  |           OPEN            |                         | Succeeded
                  +---------------------------+                         |
                     |                                                  |
    Cooldown (60s)   |                                                  |
       Elapsed       v                                                  |
                  +---------------------------+                         |
                  |        RECOVERING         |-------------------------+
                  +---------------------------+
                     |
                     | Canary Failed
                     v
             (Re-trips to OPEN)
```

The `ProviderErrorTracker` parses HTTP status codes and exceptions into two categories:
- **Transient / Retryable**: `429 Rate Limit`, `502 Bad Gateway`, `503 Service Unavailable`, `TimeoutError` $\to$ Triggers exponential backoff retry and failure tracking.
- **Terminal / Fail-Fast**: `401 Unauthorized`, `403 Forbidden`, `InvalidAPIKey` $\to$ Fails immediately without wasting retries.

---

### 2.3 `topic-driller` (Corner Cases, Gotchas & Failure Modes)
1. **Canary Thundering Herd in Asynchronous Environments:**
   - *Problem:* If 50 concurrent requests hit the circuit breaker the instant the 60-second cooldown expires, all 50 threads might see that the cooldown is over and flood the broken provider with 50 simultaneous "canary" requests.
   - *Defense:* `can_execute()` uses a strict mutex lock. Only the *very first* thread transitions the provider state from `OPEN` to `RECOVERING` and receives `True`. The other 49 threads immediately receive `False` and are diverted to the fallback provider.
2. **Streamlit Live Dashboard Reflection (AB-1.2):**
   - *Mechanism:* Every call in `openrouter_client.py` and `groq_client.py` registers its outcome via `record_success()` or `record_failure()`. Streamlit's sidebar reads `get_status_summary()` to render real-time health badges (🟢 Healthy, 🟡 Degraded, 🔴 Outage) without requiring manual browser refreshes.

---

### 2.4 `code-grinder` (Concrete Code Breakdown)
In `app/infrastructure/llm/provider_health.py`:

```python
class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    OPEN = "open"
    RECOVERING = "recovering"

class ProviderHealthMonitor:
    def __init__(self, failure_threshold: int = 3, cooldown_period: float = 60.0):
        self.failure_threshold = failure_threshold
        self.cooldown_period = cooldown_period
        self._lock = threading.Lock()
        self._states: dict[ProviderType, HealthStatus] = {
            ProviderType.OPENROUTER: HealthStatus.HEALTHY,
            ProviderType.GROQ: HealthStatus.HEALTHY,
        }
        self._consecutive_failures: dict[ProviderType, int] = {p: 0 for p in ProviderType}
        self._last_failure_times: dict[ProviderType, float] = {p: 0.0 for p in ProviderType}

    def can_execute(self, provider: ProviderType) -> bool:
        """Evaluate circuit breaker state for dispatch."""
        with self._lock:
            state = self._states[provider]
            if state in (HealthStatus.HEALTHY, HealthStatus.DEGRADED):
                return True
            if state == HealthStatus.OPEN:
                now = time.time()
                # Check if cooldown has elapsed to allow a single canary
                if now - self._last_failure_times[provider] > self.cooldown_period:
                    logger.info(f"Circuit for {provider} entering RECOVERING (canary test)")
                    self._states[provider] = HealthStatus.RECOVERING
                    return True
                return False
            if state == HealthStatus.RECOVERING:
                # Canary is currently in flight; block other requests
                return False
            return False

    def record_failure(self, provider: ProviderType, error: Optional[Exception] = None) -> None:
        with self._lock:
            self._consecutive_failures[provider] += 1
            self._last_failure_times[provider] = time.time()
            failures = self._consecutive_failures[provider]
            if failures >= self.failure_threshold:
                self._states[provider] = HealthStatus.OPEN
                logger.error(f"Circuit for {provider} TRIPPED to OPEN ({failures} consecutive failures)")
            else:
                self._states[provider] = HealthStatus.DEGRADED
```

---

## Module 3: Task AB-3.1 — Query Normalizer Core & Cache Key Hashing

**File:** `app/use_cases/chat/query_normalizer.py`

### 3.1 `teach-me` (Foundational Intuition)
Users type queries in completely unpredictable ways:
- `"What is the sickleave policy?"`
- `"  what   is  the   sick leave policy??? "`
- `"WHAT IS THE SICK LEAVE POLICY"`

To an exact-match cache or database lookup, these three queries look like completely different entities. If your cache relies on raw string equality, you will suffer unnecessary cache misses, forcing expensive vector searches and LLM calls for questions the system has already answered!

The **Query Normalizer** acts as an automated proofreader and standardizer: it collapses erratic whitespace, strips irrelevant punctuation, splits fused words, normalizes domain vocabulary, and produces a clean, deterministic cache key.

---

### 3.2 `explainer` (Architectural Flow & Normalization Pipeline)
The normalization pipeline runs deterministically in five distinct stages:

```
Raw Query: "  What is the sickleave balance??? "
                     |
                     v
 [Stage 1: Lowercase & Strip]
 "what is the sickleave balance???"
                     |
                     v
 [Stage 2: Word Boundary Separation]
 "what is the sick leave balance???"
                     |
                     v
 [Stage 3: Punctuation Stripping]
 "what is the sick leave balance"
                     |
                     v
 [Stage 4: Domain Synonym Mapping]
 "what is the sick leave balance" (canonical form)
                     |
                     v
 [Stage 5: Deterministic Hash Key Generation]
 Key: "norm:7e8a9f02b1c3d4e5"
```

---

### 3.3 `topic-driller` (Corner Cases, Gotchas & Failure Modes)
1. **Unintended Substring Collisions:**
   - *Problem:* A simple `.replace("leave", " leave ")` would corrupt words like `"colleague"` into `"col league"` or `"clever"` into `"c lever"`.
   - *Defense:* Word boundary detection uses explicit boundary lookaheads or a curated regex mapping (`BOUNDARY_REPLACEMENTS = {"sickleave": "sick leave", "annualleave": "annual leave", "casualleave": "casual leave"}`) to ensure only intended compounds are separated.
2. **Idempotency Guarantee:**
   - *Contract:* The normalization function is strictly idempotent:
     $$\text{normalize}(\text{normalize}(q)) \equiv \text{normalize}(q)$$
     Applying normalization multiple times will never alter the resulting string after the first pass.

---

### 3.4 `code-grinder` (Concrete Code Breakdown)
In `app/use_cases/chat/query_normalizer.py`:

```python
class QueryNormalizer:
    BOUNDARY_REPLACEMENTS = {
        "sickleave": "sick leave",
        "annualleave": "annual leave",
        "casualleave": "casual leave",
        "maternityleave": "maternity leave",
        "paternityleave": "paternity leave",
        "leavesavailable": "leaves available",
        "workfromhome": "work from home",
    }

    DOMAIN_SYNONYMS = {
        "vacation": "leave",
        "pto": "leave",
        "timeoff": "leave",
        "wfh": "work from home",
    }

    def normalize(self, query: str) -> str:
        """Idempotent multi-stage query normalization."""
        if not query or not query.strip():
            return ""
        text = query.lower().strip()

        # 1. Apply word boundary fixes
        for fused, split in self.BOUNDARY_REPLACEMENTS.items():
            text = re.sub(rf"\b{fused}\b", split, text)

        # 2. Strip excess punctuation (retain hyphens in words)
        text = re.sub(r"[^\w\s-]", " ", text)

        # 3. Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # 4. Map domain synonyms
        words = text.split()
        normalized_words = [self.DOMAIN_SYNONYMS.get(w, w) for w in words]
        return " ".join(normalized_words)

    def generate_cache_key(self, query: str, prefix: str = "norm") -> str:
        """Create a deterministic SHA-256 truncated cache signature."""
        cleaned = self.normalize(query)
        query_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}:{query_hash}"
```

---

## Module 4: Task AB-3.3 — POS Noun Filtering, Lemmatization & Vector Synonym Clustering

**File:** `app/use_cases/chat/synonym_clustering.py`

### 4.1 `teach-me` (Foundational Intuition)
In enterprise communications, employees refer to the exact same concept using different terminology:
- Employee 1 asks: *"What are the company perks?"*
- Employee 2 asks: *"What allowances are provided?"*
- Employee 3 asks: *"What benefits do I get?"*

If your bot only performs keyword matches, it will fail to connect *"perks"* to the official policy titled *"Employee Allowances and Benefits"*.
Task **AB-3.3** bridges this semantic gap by:
1. Identifying **nouns** in queries and documents using grammatical Part-of-Speech (POS) tagging (ignoring non-substantive words like "the", "can", "I").
2. Stripping words down to their root dictionary form (**Lemmatization**: `"allowances"` $\to$ `"allowance"`).
3. Measuring semantic distance using vector embeddings to group related words into **Synonym Clusters**.

---

### 4.2 `explainer` (Architectural Flow & Clustering Pipeline)

```
Document Text & Inbound Queries
               |
               v
    [Part-of-Speech Tagger] ===> Extracts tags: NN, NNS, NNP, NNPS
               |
               v
        [Lemmatizer]        ===> Normalizes plurals ("perks" -> "perk")
               |
               v
   [Vector Embeddings Model] ===> Generates dense vector representations
               |
               v
   [Cosine Similarity Matrix]
   Threshold check: cos_sim(v_i, v_j) >= 0.82
               |
               v
   +-----------------------------------------------------------+
   | Discovered Synonym Clusters:                              |
   | Cluster 1: {"allowance", "perk", "benefit", "stipend"}    |
   | Cluster 2: {"leave", "vacation", "holiday", "time-off"}   |
   +-----------------------------------------------------------+
               |
               v
  Feed into QueryNormalizer.DOMAIN_SYNONYMS
```

---

### 4.3 `topic-driller` (Corner Cases, Gotchas & Failure Modes)
1. **POS Ambiguity ("Leave" as Noun vs Verb):**
   - *Example:* In *"I want to leave early"*, *"leave"* is a verb (`VB`). In *"Apply for sick leave"*, *"leave"* is a noun (`NN`).
   - *Resolution:* The tagger evaluates context. If preceded by modal verbs or infinitives (*"to"*, *"can"*), the token is tagged as a verb and ignored. If preceded by a determiner, adjective, or noun (*"sick"*, *"annual"*), it is tagged as a noun and processed.
2. **Semantic Drift from Loose Thresholds:**
   - *Risk:* If cosine similarity threshold is set too low (e.g. 0.65), completely distinct entities like `"salary"` and `"deduction"` would cluster together, causing severe retrieval cross-talk. Setting a strict threshold ($\ge 0.82$) guarantees high-precision clusters.

---

### 4.4 `code-grinder` (Concrete Code Breakdown)
In `app/use_cases/chat/synonym_clustering.py`:

```python
class SynonymClusterEngine:
    def __init__(self, similarity_threshold: float = 0.82):
        self.similarity_threshold = similarity_threshold
        self.lemmatizer = WordNetLemmatizer()

    def extract_noun_lemmas(self, text: str) -> list[str]:
        """Extract and lemmatize all noun tokens."""
        tokens = word_tokenize(text)
        tagged = pos_tag(tokens)
        nouns = [
            self.lemmatizer.lemmatize(word.lower(), pos="n")
            for word, tag in tagged
            if tag in ("NN", "NNS", "NNP", "NNPS") and len(word) > 2
        ]
        return list(set(nouns))

    def cluster_synonyms(self, terms: list[str], embedding_fn: Callable[[list[str]], list[list[float]]]) -> dict[str, str]:
        """Cluster terms based on pairwise cosine similarity >= threshold."""
        if not terms:
            return {}
        vectors = embedding_fn(terms)
        clusters: dict[str, str] = {}
        visited = set()

        for i, term_a in enumerate(terms):
            if term_a in visited:
                continue
            head = term_a
            clusters[head] = head
            visited.add(head)
            for j in range(i + 1, len(terms)):
                term_b = terms[j]
                if term_b in visited:
                    continue
                similarity = self._cosine_similarity(vectors[i], vectors[j])
                if similarity >= self.similarity_threshold:
                    clusters[term_b] = head
                    visited.add(term_b)
        return clusters
```

---

## Module 5: Task AB-3.4 — Query Intent Disambiguation & Semantic Routing

**File:** `app/use_cases/chat/query_intent_classifier.py`

### 5.1 `teach-me` (Foundational Intuition)
Consider two employee questions:
1. *"How do I apply for maternity leave on the portal?"*
2. *"How many maternity leaves do I have left?"*

Notice that both questions contain the keywords *"maternity leave"*.
- Question 1 is **Procedural**: the user needs step-by-step instructions from the employee handbook on how to use the HR portal.
- Question 2 is **Personal Entitlement / Balance**: the static PDF handbook *does not know* this user's personal leave balance! Only the real-time HRMS database has that information.

If the chatbot treats both questions the same way, it might respond to Question 2 with: *"Employees are granted 26 weeks of maternity leave"*, which fails to answer the user's specific question about their personal balance.
Task **AB-3.4** categorizes user queries by intent so they are routed properly and cached under dedicated namespaces.

---

### 5.2 `explainer` (Architectural Flow & Intent Routing)
Queries are categorized into three core intents:
- `QueryIntent.PROCEDURAL`: Keywords indicating workflows or processes (`"apply"`, `"submit"`, `"portal"`, `"steps"`, `"approval"`).
- `QueryIntent.PERSONAL_BALANCE`: Keywords indicating personal balances (`"balance"`, `"remaining"`, `"how many days"`, `"left"`, `"my leave"`).
- `QueryIntent.POLICY_GENERAL`: Standard policy questions regarding rules and definitions.

```
Incoming Query: "How many casual leaves do I have left?"
                        |
                        v
           [QueryIntentClassifier]
                        |
    +-------------------+-------------------+
    |                   |                   |
    v (Procedural)      v (Personal Balance)v (General Policy)
[PROCEDURAL]        [PERSONAL_BALANCE]   [POLICY_GENERAL]
    |                   |                   |
    |                   +---> Injects warning into system prompt:
    |                         "Direct employee to check personal
    |                          balance in HRMS dashboard."
    |                   |
    +-------------------+-------------------+
                        |
                        v
          Intent-Prefixed Cache Key:
     "bal:leave:remaining_balance_hash"
   (Completely isolated from "proc:..." keys!)
```

---

### 5.3 `topic-driller` (Corner Cases, Gotchas & Failure Modes)
1. **Intent-Isolated Cache Partitions:**
   - *Problem:* If Cache Key generation does not include the intent prefix, a procedural query (*"Casual leave"*) could return a cached answer originally generated for a personal balance query (*"Casual leave balance"*).
   - *Defense:* The intent tag is injected directly into the cache key namespace (`proc:...` vs `bal:...` vs `gen:...`), preventing cache collision between different query types.
2. **Priority Ordering on Hybrid Queries:**
   - *Example:* *"How do I check my remaining leave balance on the portal?"* contains both procedural terms (*"portal"*) and balance terms (*"remaining leave balance"*).
   - *Rule:* Personal balance detection takes priority over procedural classification, because providing ungrounded personal data is a higher-severity error than omitting workflow steps.

---

### 5.4 `code-grinder` (Concrete Code Breakdown)
In `app/use_cases/chat/query_intent_classifier.py`:

```python
class QueryIntent(Enum):
    PROCEDURAL = "procedural"
    PERSONAL_BALANCE = "personal_balance"
    POLICY_GENERAL = "policy_general"

class QueryIntentClassifier:
    PROCEDURAL_TERMS = {"apply", "submit", "portal", "workflow", "steps", "approval", "process", "route"}
    BALANCE_TERMS = {"how many", "balance", "remaining", "left", "accrued", "my leave", "quota", "entitlement"}

    def classify(self, query: str) -> QueryIntent:
        """Classify query intent with priority rules."""
        lowered = query.lower()
        
        # Check personal entitlement first (highest risk)
        if any(term in lowered for term in self.BALANCE_TERMS):
            return QueryIntent.PERSONAL_BALANCE
            
        # Check procedural workflow
        if any(term in lowered for term in self.PROCEDURAL_TERMS):
            return QueryIntent.PROCEDURAL
            
        return QueryIntent.POLICY_GENERAL
```

---

## Module 6: Tasks AB-4 & AB-4.2 — Quality-Aware Semantic Cache

**Files:** `app/infrastructure/cache/quality_aware_cache.py`, `app/use_cases/chat/query_orchestrator.py`

### 6.1 `teach-me` (Foundational Intuition)
Standard caching systems are passive: whatever the backend generates, the cache stores.
If an employee asks an obscure question, the vector database returns irrelevant chunks, and the LLM hallucinates an inaccurate answer, a naive cache will store that hallucinated response. For the next 24 hours, every employee asking that question will receive the same hallucinated answer!

Task **AB-4** implements a **Quality-Aware Cache**: it validates responses before caching them. Only answers that have passed the Retrieval Quality Gate with high confidence scores and verified citations are stored. Unverified or low-confidence responses are discarded immediately.

---

### 6.2 `explainer` (Architectural Flow & Cache Gate)
The cache infrastructure consists of:
- `InMemoryQualityAwareCache`: Thread-safe, LRU-evicting memory cache with TTL expiration.
- `CacheQualityValidator`: Quality gate ensuring confidence score $\ge 0.70$, evidence count $\ge 1$, and non-negative response content.
- `CacheEntryMetadata`: Stores origin source (`RAG_GENERATED`, `FAQ_MATCHED`, `SEMANTIC_CACHE`), confidence metrics, and citations.

```
LLM Generated Response + Retrieval QualityScore
                       |
                       v
           [CacheQualityValidator]
                       |
      +----------------+----------------+
      |                                 |
Confidence < 0.70  OR             Confidence >= 0.70  AND
Negative / Refusal Content        Verified Evidence Found
      |                                 |
      v                                 v
   [DISCARD]                     [STORE IN CACHE]
Response served to user          Saved with TTL & metadata
(Never stored in cache!)         (Available for instant replay)
```

In `query_orchestrator.py`:
1. **Pre-Retrieval Phase:** Checks `cache.get(normalized_query)`. On a hit, returns immediately ($\le 5\text{ms}$ latency, zero LLM tokens consumed).
2. **Post-Retrieval Phase:** On a cache miss, processes the RAG pipeline. If the generated answer passes `CacheQualityValidator.is_cacheable()`, it writes the entry to the cache.

---

### 6.3 `topic-driller` (Corner Cases, Gotchas & Failure Modes)
1. **The Negative Response Poisoning Bug:**
   - *Problem:* A query like *"What is the policy for bringing pets to work?"* might return *"This information is not mentioned in company documents."* If this response is cached, and an official Pet Policy is uploaded to the system two hours later, the cache will continue returning the old negative response until the TTL expires!
   - *Defense:* `CacheQualityValidator` inspects the response text using refusal pattern heuristics (`"not mentioned"`, `"could not find"`, `"do not have"`). Negative responses are **never** cached.
2. **Document Invalidation Handshake:**
   - When an administrator uploads a revised document via `app/use_cases/organization/document_management.py`, the cache triggers `invalidate_by_source("rag_generated")` or clears relevant keys, ensuring stale answers are evicted.

---

### 6.4 `code-grinder` (Concrete Code Breakdown)
In `app/infrastructure/cache/quality_aware_cache.py`:

```python
class CacheQualityValidator:
    MIN_CONFIDENCE_THRESHOLD = 0.70
    NEGATIVE_PATTERNS = [
        "not mentioned", "cannot find", "do not have",
        "could not find", "no information", "not found"
    ]

    @classmethod
    def is_cacheable(cls, quality_score: QualityScore, response_text: str) -> tuple[bool, str]:
        """Strict validation of response quality before cache admission."""
        if quality_score.quality_level == EvidenceQualityLevel.INVALID:
            return False, "Evidence quality level is INVALID"
            
        if quality_score.overall_score < cls.MIN_CONFIDENCE_THRESHOLD:
            return False, f"Confidence {quality_score.overall_score:.2f} < threshold {cls.MIN_CONFIDENCE_THRESHOLD}"
            
        lowered = response_text.lower()
        if any(pat in lowered for pat in cls.NEGATIVE_PATTERNS):
            return False, "Negative response detected; not cacheable"
            
        return True, "Validated"
```

Integration in `app/use_cases/chat/query_orchestrator.py`:
```python
# 1. Cache Lookup
with self._tracer.trace_stage(PipelineStage.CACHE_LOOKUP) as span:
    cached_entry = self._cache.get(normalized_query)
    if cached_entry:
        span.set_metadata("cache_hit", True)
        return cached_entry.to_response()

# ... Vector Retrieval & LLM Generation ...

# 2. Quality Gate & Cache Storage
is_cacheable, reason = CacheQualityValidator.is_cacheable(quality_score, generated_text)
if is_cacheable:
    self._cache.put(
        key=normalized_query,
        response_text=generated_text,
        confidence=quality_score.overall_score,
        citations=formatted_citations,
    )
```

---

## Module 7: Tasks AB-5.1 & AB-5.2 — Multi-Dimensional Retrieval Quality Gate

**Files:** `app/use_cases/chat/retrieval_quality.py`, `app/use_cases/chat/retrieval_service.py`

### 7.1 `teach-me` (Foundational Intuition)
Vector search relies on geometric nearest-neighbor math: even if you ask a completely irrelevant question like *"How do I pilot an airplane?"*, ChromaDB will still return the 4 "closest" chunks in your employee handbook! Those chunks might discuss booking flight tickets for business travel, with a high distance score of 0.89.

If you pass those irrelevant chunks to an LLM, the model will try to combine them into an answer and end up hallucinating.
The **Retrieval Quality Gate** functions as an automated evaluation checkpoint. It assesses retrieved chunks across multiple dimensions—distance, lexical token overlap, and distance separation. If the evidence falls below standards, it rejects the chunks and terminates the request early, without invoking the LLM.

---

### 7.2 `explainer` (Architectural Flow & Multi-Dimensional Scoring)
The quality gate classifies evidence into four levels:
- `STRONG`: Vector distance $< 0.60$, high lexical overlap. High confidence.
- `BORDERLINE`: Vector distance between $0.60$ and $0.70$. Handled with cautious prompt framing.
- `WEAK`: Vector distance between $0.70$ and $0.85$. Low confidence.
- `INVALID`: Vector distance $\ge 0.85$ or lexical overlap is zero. **Hard rejection and early exit.**

```
Retrieved Candidate Chunks (Top-k from ChromaDB)
                       |
                       v
           [RetrievalQualityGate]
                       |
        Multi-Dimensional Evaluation:
        1. Cosine Distance Score: S_dist = 1.0 - (d1 / 0.85)
        2. Lexical Grounding Overlap: S_ground = Jaccard(query, chunk)
        3. Standout Separation Gap: S_gap = clamp(2 * (d2 - d1))
                       |
                       v
         Composite Confidence Calculation:
   Score = (0.50 * S_dist) + (0.35 * S_ground) + (0.15 * S_gap)
                       |
        +--------------+--------------+
        |                             |
Distance >= 0.85   OR           Distance < 0.85  AND
Score < Threshold               Score >= Threshold
        |                             |
        v                             v
[EvidenceQualityLevel.INVALID]  [EvidenceQualityLevel.STRONG / BORDERLINE]
Triggers Early Exit:            Proceed to LLM generation
"Information not found."        with verified context
(Zero LLM token costs!)
```

---

### 7.3 `topic-driller` (Corner Cases, Gotchas & Failure Modes)
1. **Single-Candidate Index Out-of-Bounds ($k < 2$):**
   - *Problem:* The standout separation gap calculation compares the first and second candidates:
     $$\Delta = d_{\text{top2}} - d_{\text{top1}}$$
     If the vector store returns only one matching chunk ($k = 1$), accessing `chunks[1]` raises an `IndexError`.
   - *Defense:* The calculation is guarded:
     ```python
     separation_gap = (chunks[1].distance - top_distance) if len(chunks) > 1 else 0.0
     ```
2. **Semantic Mirages (Vector Proximity without Factual Match):**
   - *Problem:* Dense embeddings occasionally place texts close together due to similar grammatical style or sentence length, despite having zero keywords in common.
   - *Defense:* The lexical grounding dimension calculates token overlap between query nouns and chunk text. If lexical overlap is 0.0, the overall score is penalized, preventing semantic mirages from slipping through.

---

### 7.4 `code-grinder` (Concrete Code Breakdown)
In `app/use_cases/chat/retrieval_quality.py`:

```python
class EvidenceQualityLevel(Enum):
    STRONG = "strong"          # distance < 0.60
    BORDERLINE = "borderline"  # 0.60 <= distance < 0.70
    WEAK = "weak"              # 0.70 <= distance < 0.85
    INVALID = "invalid"        # distance >= 0.85 (Hard cutoff)

class RetrievalQualityGate:
    HARD_DISTANCE_CUTOFF = 0.85

    def evaluate(self, query: str, chunks: list[RetrievedChunk]) -> QualityScore:
        """Evaluate candidate evidence across multiple quality dimensions."""
        if not chunks:
            return QualityScore(overall_score=0.0, quality_level=EvidenceQualityLevel.INVALID)

        top_distance = chunks[0].distance

        # Hard rejection cutoff
        if top_distance >= self.HARD_DISTANCE_CUTOFF:
            return QualityScore(
                overall_score=0.0,
                distance_score=0.0,
                grounding_score=0.0,
                separation_gap=0.0,
                evidence_count=len(chunks),
                quality_level=EvidenceQualityLevel.INVALID,
            )

        # 1. Distance Score
        dist_score = max(0.0, 1.0 - (top_distance / self.HARD_DISTANCE_CUTOFF))

        # 2. Lexical Grounding Score
        ground_score = self._compute_lexical_grounding(query, chunks[0].content)

        # 3. Separation Gap (Guarded against k < 2)
        gap = (chunks[1].distance - top_distance) if len(chunks) > 1 else 0.0
        gap_score = min(1.0, max(0.0, gap * 2.0))

        # Weighted Composite Confidence Score
        overall = (0.50 * dist_score) + (0.35 * ground_score) + (0.15 * gap_score)
        level = self._classify_level(top_distance, overall)

        return QualityScore(
            overall_score=overall,
            distance_score=dist_score,
            grounding_score=ground_score,
            separation_gap=gap,
            evidence_count=len(chunks),
            quality_level=level,
        )
```

---

## Module 8: Tasks AB-6.1, AB-6.2 & AB-6.3 — 8-Stage Pipeline Tracing Engine

**Files:** `app/infrastructure/observability/pipeline_tracer.py`, `app/infrastructure/observability/manager.py`

### 8.1 `teach-me` (Foundational Intuition)
When a user reports: *"The bot took 5 seconds to answer my question!"*, how do you determine what caused the delay?
- Did OpenRouter take 4.5 seconds to generate tokens?
- Did ChromaDB stall during retrieval?
- Did query normalization get stuck in a regex loop?
- Did reranking consume excessive time?

Without structured timing metrics, your application is a black box. Task **AB-6.1** instruments a stopwatch across **8 distinct stages** of the query pipeline. Every request generates a detailed trace recording exact latencies, token counts, and execution status for each step.

---

### 8.2 `explainer` (Architectural Flow & Stage Instrumentation)
The tracing engine tracks 8 canonical stages:
1. `CONTEXT_REWRITE`: Multi-turn conversational pronoun resolution.
2. `NORMALIZATION`: Query cleaning, boundary fixing, and canonicalization.
3. `CACHE_LOOKUP`: Exact, semantic, and FAQ cache lookup.
4. `VECTOR_RETRIEVAL`: ChromaDB nearest-neighbor search.
5. `RERANKING`: Cross-encoder candidate reranking.
6. `QUALITY_GATE`: Multi-dimensional evidence quality evaluation.
7. `LLM_GENERATION`: LLM generation and streaming.
8. `POST_GUARDRAILS`: Citation formatting and cache storage.

```
Incoming Turn
      |
      v
 [PipelineTracer.start_trace(session_id, query)]
      |
      +---> [Stage 1: CONTEXT_REWRITE]   --> span: {latency_ms: 180, tokens: 55}
      +---> [Stage 2: NORMALIZATION]     --> span: {latency_ms: 1.2}
      +---> [Stage 3: CACHE_LOOKUP]      --> span: {latency_ms: 2.8, hit: False}
      +---> [Stage 4: VECTOR_RETRIEVAL]  --> span: {latency_ms: 68.4, chunks: 15}
      +---> [Stage 5: RERANKING]         --> span: {latency_ms: 95.1, top_k: 4}
      +---> [Stage 6: QUALITY_GATE]      --> span: {latency_ms: 2.1, score: 0.94}
      +---> [Stage 7: LLM_GENERATION]    --> span: {latency_ms: 1250.0, tokens: 245}
      +---> [Stage 8: POST_GUARDRAILS]   --> span: {latency_ms: 3.9}
      |
      v
 [Trace Completed & Dispatched]
 Dispatches structured trace to LangfuseProvider and Admin Telemetry
```

---

### 8.3 `topic-driller` (Corner Cases, Gotchas & Failure Modes)
1. **Crash-Resilient Span Closure:**
   - *Problem:* If an uncaught exception occurs during LLM generation, an ordinary timing block might never execute its stop logic, leaving the trace open and corrupting metrics.
   - *Defense:* `trace_stage()` is implemented as a context manager. The `finally` block ensures that even during an unhandled exception, `end_time` is recorded, `span.status = "error"` is set, and the partial trace is cleanly finalized.
2. **Disjoint Multi-Tenant Threading:**
   - *Problem:* Concurrent requests from different users must not overwrite each other's spans.
   - *Defense:* Spans are tied to individual `TraceContext` instances stored in thread-local storage or passed explicitly through the execution context.

---

### 8.4 `code-grinder` (Concrete Code Breakdown)
In `app/infrastructure/observability/pipeline_tracer.py`:

```python
class PipelineStage(Enum):
    CONTEXT_REWRITE = "context_rewrite"
    NORMALIZATION = "normalization"
    CACHE_LOOKUP = "cache_lookup"
    VECTOR_RETRIEVAL = "vector_retrieval"
    RERANKING = "reranking"
    QUALITY_GATE = "quality_gate"
    LLM_GENERATION = "llm_generation"
    POST_GUARDRAILS = "post_guardrails"

@dataclass
class StageSpan:
    stage: PipelineStage
    start_time: float
    end_time: float = 0.0
    duration_ms: float = 0.0
    status: str = "success"
    tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

class PipelineTracer:
    @contextmanager
    def trace_stage(self, stage: PipelineStage) -> Generator[StageSpan, None, None]:
        """Context manager span for timing and tracking individual stages."""
        span = StageSpan(stage=stage, start_time=time.time())
        try:
            yield span
        except Exception as exc:
            span.status = "error"
            span.metadata["error"] = str(exc)
            raise
        finally:
            span.end_time = time.time()
            span.duration_ms = (span.end_time - span.start_time) * 1000.0
            self._record_span(span)
```

Usage in `app/use_cases/chat/query_orchestrator.py`:
```python
with self._tracer.trace_stage(PipelineStage.LLM_GENERATION) as span:
    response = self._llm_provider.generate(prompt=rag_prompt)
    span.tokens = response.token_usage.total_tokens
    span.metadata["provider"] = response.provider.value
```

---

## Module 9: Task AB-7 — Verification & Evaluation Matrix

To validate that all implementations under Abhinav's scope operate correctly without regressions, the test suite executes targeted verification across four test suites:

```
+========================================================================================================+
|                                  ABHINAV'S UNIT & CONTRACT TEST GATES                                  |
+========================================================================================================+
|  1. tests/unit/test_quality_aware_cache.py                                                             |
|     - Verifies LRU eviction and TTL expiration.                                                        |
|     - Verifies rejection of responses with confidence scores < 0.70.                                   |
|     - Verifies exclusion of negative/refusal responses from cache storage.                             |
|                                                                                                        |
|  2. tests/unit/test_retrieval_quality.py                                                               |
|     - Verifies hard distance cutoff (distance >= 0.85 -> INVALID).                                     |
|     - Verifies classification: STRONG, BORDERLINE, WEAK, INVALID.                                      |
|     - Verifies safe separation gap calculation when k < 2.                                             |
|                                                                                                        |
|  3. tests/unit/test_pipeline_tracing.py                                                                |
|     - Verifies 8-stage naming compliance.                                                              |
|     - Verifies latency calculation and token accumulation.                                             |
|     - Verifies error capture during unhandled exceptions.                                              |
|                                                                                                        |
|  4. tests/unit/test_dual_cache.py                                                                      |
|     - Verifies cache namespace isolation between FAQ, Semantic, and RAG caches.                        |
+========================================================================================================+
```

### Full Regression Command
```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_quality_aware_cache.py tests\unit\test_retrieval_quality.py tests\unit\test_pipeline_tracing.py tests\unit\test_dual_cache.py -v -p no:cacheprovider
```

---

## Complete Deliverables Summary

| Task ID | Component Name | Key Artifact | Status |
|:---|:---|:---|:---:|
| **AB-2** | Standardized LLM Response Contract | `app/infrastructure/llm/llm_response.py` | Completed |
| **AB-1.1** | Circuit Breaker & Health Monitor | `app/infrastructure/llm/provider_health.py` | Completed |
| **AB-1.2** | Client Health Integration | `openrouter_client.py`, `groq_client.py` | Completed |
| **AB-3.1** | Query Normalizer Core | `app/use_cases/chat/query_normalizer.py` | Completed |
| **AB-3.3** | POS Noun Filtering & Synonym Clustering | `app/use_cases/chat/synonym_clustering.py` | Completed |
| **AB-3.4** | Query Intent Disambiguation & Routing | `app/use_cases/chat/query_intent_classifier.py` | Completed |
| **AB-4** | Quality-Aware Semantic Cache | `app/infrastructure/cache/quality_aware_cache.py` | Completed |
| **AB-5.1** | Multi-Dimensional Retrieval Quality Gate | `app/use_cases/chat/retrieval_quality.py` | Completed |
| **AB-6.1** | 8-Stage Pipeline Tracing Engine | `app/infrastructure/observability/pipeline_tracer.py` | Completed |
| **AB-7** | Evaluation & Verification Suite | `tests/unit/test_quality_aware_cache.py` | Verified |
