# Company Bot LLM + ChromaDB Architecture

## High-Level Data Flow

```
┌─────────────────┐
│   User Input    │
│  "How to apply  │
│   for leave?"   │
└────────┬────────┘
         │
         ▼
    ┌────────────────────────────────┐
    │   QueryOrchestrator.answer()   │
    │    Orchestrates full pipeline  │
    └────────┬───────────────────────┘
             │
             ├──────────────────────────────────────┐
             │                                      │
             ▼                                      ▼
    ┌─────────────────────────┐       ┌──────────────────────────┐
    │  FAQ Similarity Cache   │       │   (If FAQ miss)          │
    │  (In-memory embedding   │       │  ChromaDB Retrieval      │
    │   search over FAQs)     │       │  (Query expansion +      │
    │                         │       │   relevance filtering)   │
    │  FAST: <10ms            │       │                          │
    │  Hit Rate: ~10-15%      │       │  MEDIUM: 500ms-1s        │
    └────────┬────────────────┘       └──────────┬───────────────┘
             │                                   │
         [HIT]                               [MISS or NOT FAQ]
             │                                   │
             │                                   ▼
             │                        ┌──────────────────────────┐
             │                        │  RAGContextBuilder       │
             │                        │  Formats retrieved       │
             │                        │  chunks into LLM prompt  │
             │                        └──────────┬───────────────┘
             │                                   │
             │                                   ▼
             │                        ┌──────────────────────────┐
             │                        │  System Prompt           │
             │                        │  "Answer ONLY from       │
             │                        │   provided context..."   │
             │                        │                          │
             │                        │  User Prompt             │
             │                        │  "[Section Title]"       │
             │                        │  "{formatted chunks}"    │
             │                        │  "Question: ..."         │
             │                        └──────────┬───────────────┘
             │                                   │
             │                                   ▼
             │                        ┌──────────────────────────┐
             │                        │  LLM Generation          │
             │                        │  (OpenRouter/Claude)     │
             │                        │  (with Groq fallback)    │
             │                        │                          │
             │                        │  SLOW: 1-3 seconds       │
             │                        │  (Cached: <1ms)          │
             │                        └──────────┬───────────────┘
             │                                   │
             └───────────────────────┬───────────┘
                                     │
                                     ▼
                        ┌────────────────────────┐
                        │  Format Response       │
                        │  + Extract Citations   │
                        │  + Save to MongoDB     │
                        └────────┬───────────────┘
                                 │
                                 ▼
                        ┌────────────────────────┐
                        │  Return to User        │
                        │  Answer + Citations    │
                        │  + Cache Metadata      │
                        └────────────────────────┘
```

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     APPLICATION LAYER                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              QueryOrchestrator (Orchestrator)           │   │
│  │  • Manages entire pipeline                              │   │
│  │  • Dispatches to cache layers & LLM                     │   │
│  │  • Builds return object with citations                  │   │
│  └─────┬──────────────────────────────────────────────────┬┘   │
└────────┼──────────────────────────────────────────────────┼──────┘
         │                                                   │
    ┌────┴───────────────────────┐                    ┌─────┴────────┐
    │                            │                    │              │
┌───▼────────────────┐   ┌──────▼─────────────┐   ┌──▼──────────────┐
│  FAQ Layer         │   │ RAG Layer          │   │ LLM Layer       │
├────────────────────┤   ├────────────────────┤   ├─────────────────┤
│ FAQSimilarityCache │   │ RetrievalService   │   │OpenRouterClient │
│ • Load FAQs at     │   │ • ChromaDB query   │   │ • Primary LLM   │
│   startup          │   │ • Query expansion  │   │                 │
│ • Embed questions  │   │ • Distance filter  │   │ GroqClient      │
│ • Cosine similarity│   │ • Deduplication    │   │ • Fallback LLM  │
│   search           │   │ • Character limit  │   │                 │
│ • Return match or  │   │                    │   │ PromptLRUCache  │
│   None             │   │                    │   │ • In-mem cache  │
│ SPEED: <10ms       │   │ SPEED: 500ms-1s    │   │ • Thread-safe   │
└────────────────────┘   └────────────────────┘   │ SPEED: <1ms     │
                                                  └─────────────────┘

           ┌────────────────────────────────────────────────────┐
           │         RAGContextBuilder (Formatters)            │
           ├────────────────────────────────────────────────────┤
           │ • build_system_prompt()                            │
           │   → System message guiding LLM behavior            │
           │ • build_user_prompt()                              │
           │   → Formats ChromaDB chunks with metadata          │
           │ • build_messages()                                 │
           │   → Complete message list for LLM                  │
           │ • format_evidence_for_citations()                  │
           │   → Citation objects for user                      │
           └────────────────────────────────────────────────────┘

           ┌────────────────────────────────────────────────────┐
           │       Infrastructure Layer (Observability)         │
           ├────────────────────────────────────────────────────┤
           │ • LangSmith Tracing                                │
           │   - Trace each LLM call                            │
           │   - Track retrieval performance                    │
           │   - Debug slow responses                           │
           │ • Structured Logging                               │
           │   - Pipeline steps                                 │
           │   - Cache hits/misses                              │
           │   - Error tracking                                 │
           └────────────────────────────────────────────────────┘
```

## Request Processing Sequence Diagram

```
User              Browser          FastAPI           QueryOrchestrator
 │                  │                  │                  │
 ├─ Ask Question ──→│                  │                  │
 │                  ├─ POST /api/chat ─→│                  │
 │                  │                  ├─ answer() ───────→│
 │                  │                  │                  ├─ Check FAQ Cache
 │                  │                  │                  │  (FAQSimilarityCache)
 │                  │                  │                  │
 │                  │                  │                  ├─ FAQ MISS
 │                  │                  │                  │
 │                  │                  │                  ├─ Resolve Query
 │                  │                  │                  │  (ConversationQueryResolver)
 │                  │                  │                  │
 │                  │                  │                  ├─ Retrieve Docs
 │                  │                  │                  │  (RetrievalService)
 │                  │                  │                  │
 │                  │                  │                  ├─ Build Context
 │                  │                  │                  │  (RAGContextBuilder)
 │                  │                  │                  │
 │                  │                  │                  ├─ Generate LLM Response
 │                  │                  │                  │  (OpenRouterClient)
 │                  │                  │                  │
 │                  │                  │                  ├─ Extract Citations
 │                  │                  │                  │  (ProvenanceService)
 │                  │                  │                  │
 │                  │                  │  return result ←─┤
 │                  │ JSON Response ←──┤
 │ Display Answer ←─│
 │
```

## Cache Layer Architecture

```
                    ┌──────────────────────┐
                    │  User Question       │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────────────────┐
                    │  Layer 1: FAQ Cache              │
                    │  FAQSimilarityCache (Semantic)   │
                    │  • Questions embedded at startup │
                    │  • Cosine similarity search      │
                    │  • Hits: ~10-15%                 │
                    │  • Speed: <10ms                  │
                    └──────────┬───────────────────────┘
                               │
                          [MISS]│
                               │
                               ▼
                    ┌──────────────────────────────────┐
                    │  ChromaDB Retrieval              │
                    │  RetrievalService                │
                    │  • Query ChromaDB for chunks     │
                    │  • Relevance filtering           │
                    │  • Deduplication                 │
                    └──────────┬───────────────────────┘
                               │
                               ▼
                    ┌──────────────────────────────────┐
                    │  Layer 2: LLM Response Cache     │
                    │  PromptLRUCache (Exact Match)    │
                    │  • Exact hash of full prompt     │
                    │  • Hits: ~20-30%                 │
                    │  • Speed: <1ms                   │
                    └──────────┬───────────────────────┘
                               │
                          [MISS]│
                               │
                               ▼
                    ┌──────────────────────────────────┐
                    │  LLM API Call                    │
                    │  OpenRouterClient / GroqClient   │
                    │  • Primary: Claude 3.5 Sonnet    │
                    │  • Fallback: Llama 3.1           │
                    │  • Speed: 1-3 seconds            │
                    └──────────────────────────────────┘
```

## Data Flow: ChromaDB to LLM

```
┌─────────────────────────────────────────────────────────────┐
│  ChromaDB Collection                                        │
│  (hr_policy_docs)                                           │
│                                                             │
│  Document 1:        Document 2:        Document 3:         │
│  {                  {                  {                   │
│    id: "doc1",      id: "doc2",        id: "doc3",         │
│    text: "...",     text: "...",       text: "...",        │
│    embedding: [...] embedding: [...]   embedding: [...]    │
│  }                  }                  }                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ retrieval_service.retrieve(query)
                       ▼
        ┌──────────────────────────────────────┐
        │  RetrievalService                    │
        │                                      │
        │  1. Query expansion                  │
        │     "leave?" → ["leave?",            │
        │                 "annual leave",      │
        │                 "entitlement"]       │
        │                                      │
        │  2. ChromaDB search per part         │
        │     Returns: top_k candidates        │
        │                                      │
        │  3. Deduplication + filtering        │
        │     - Remove duplicates              │
        │     - Distance threshold check       │
        │     - Character limit               │
        │                                      │
        │  Output: List[dict] with:            │
        │    - text: chunk content             │
        │    - distance: relevance score       │
        │    - metadata: section, source, etc  │
        └────────────────────┬─────────────────┘
                             │
                             ▼
        ┌──────────────────────────────────────┐
        │  RAGContextBuilder                   │
        │                                      │
        │  1. Format chunks with metadata      │
        │     "[Leave Policy]"                 │
        │     "Employees receive 18 days..."   │
        │     "(relevance: 95%)"               │
        │                                      │
        │  2. Build system prompt              │
        │     "Answer ONLY from context..."    │
        │                                      │
        │  3. Build user prompt                │
        │     "Question: {query}"              │
        │                                      │
        │  Output: List[dict] messages:        │
        │    - role: "system" / "user"         │
        │    - content: formatted text         │
        └────────────────────┬─────────────────┘
                             │
                             ▼
        ┌──────────────────────────────────────┐
        │  OpenRouterClient.generate()         │
        │                                      │
        │  POST https://openrouter.ai/api/... │
        │  {                                   │
        │    "model": "claude-3.5-sonnet",     │
        │    "messages": [...],                │
        │    "max_tokens": 400                 │
        │  }                                   │
        │                                      │
        │  Response:                           │
        │  "Employees receive 18 days of       │
        │   Annual Leave per year. They can    │
        │   carry forward up to 10 unused...   │
        │                                      │
        │   Would you like references?"        │
        └────────────────────┬─────────────────┘
                             │
                             ▼
        ┌──────────────────────────────────────┐
        │  ProvenanceService                   │
        │  (Citation Extraction)               │
        │                                      │
        │  From selected_evidence, extract:    │
        │  [                                   │
        │    {                                 │
        │      "source": "HR Policy",          │
        │      "section": "Leave Policy",      │
        │      "text": "Full chunk text..."    │
        │    }                                 │
        │  ]                                   │
        └────────────────────┬─────────────────┘
                             │
                             ▼
        ┌──────────────────────────────────────┐
        │  Return to User                      │
        │  {                                   │
        │    "answer": "...",                  │
        │    "citations": [],                  │
        │    "cache_hit": false,               │
        │    "matched_faq": null               │
        │  }                                   │
        └──────────────────────────────────────┘
```

## Configuration Tuning Impact

```
┌──────────────────────────────────────────────────────────┐
│  Configuration                   Impact                  │
├──────────────────────────────────────────────────────────┤
│  RAG_DISTANCE_THRESHOLD ↓         More docs retrieved    │
│                        ↑         Fewer docs retrieved    │
├──────────────────────────────────────────────────────────┤
│  RAG_MAX_EVIDENCE ↓               Faster LLM, less info  │
│                ↑                 Slower LLM, more info   │
├──────────────────────────────────────────────────────────┤
│  RAG_CANDIDATE_COUNT ↓            Faster retrieval       │
│                   ↑             Slower retrieval         │
├──────────────────────────────────────────────────────────┤
│  FAQ_SIMILARITY_THRESHOLD ↓       More FAQ hits          │
│                         ↑        Fewer FAQ hits          │
├──────────────────────────────────────────────────────────┤
│  LLM_MODEL → claude-3.5           Better accuracy        │
│         → llama-3.1              Faster response         │
└──────────────────────────────────────────────────────────┘
```

## Error Handling Flow

```
                    ┌──────────────┐
                    │  User Query  │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────────┐
                    │  FAQ Cache Hit?  │
                    └──────┬───────┬───┘
                           │       │
                        YES│       │NO
                           │       └─→ ┌──────────────────┐
                           │           │ ChromaDB Search  │
                           │           └────┬─────────┬───┘
                           │                │         │
                           │             HIT│         │MISS
                           │                │         │
                           │                │         ▼
                           │                │    No Results?
                           │                │    │
                           │                │    ├→ Return:
                           │                │    │  "I could not find..."
                           │                │    │
                           │                │    └→ Cache miss
                           │                │
                           │                ▼
                           │           ┌──────────────────┐
                           │           │ Build Prompt     │
                           │           │ + Generate LLM   │
                           │           └────┬─────────┬───┘
                           │                │         │
                           │            SUCCESS│  │FAILURE
                           │                │   │
                           ▼                │   │
                    ┌───────────────────────┘   │
                    │                           │
                    ▼                           ▼
            Return Answer            Retry with Fallback
            + Citations               (Groq LLM)
            + Cache Hit?                  │
                                          ▼
                                  Return Fallback Answer
                                  or Error
```

This architecture ensures reliable, auditable, and performant RAG-powered question answering using your company's HR documents.
