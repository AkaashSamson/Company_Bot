# End-to-End Query Processing Architecture in KnowLayer V3

This document provides a comprehensive, component-by-component architectural deep dive into how a query moves from user input in the frontend to final answer delivery, including caching, security scoping, vector retrieval, reranking, quality gates, and generation.

---

## 1. High-Level Architecture Flow Diagram (Plain Text Box Diagram)

```text
================================================================================================================================
                                          KNOWLAYER V3 - END-TO-END QUERY LIFECYCLE
================================================================================================================================

 [👤 User]
     │
     ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. CLIENT & PRESENTATION LAYER                                                                                              │
│    File: streamlit_app/app.py                                                                                                │
│    • Captures user question, session_id, conversation_history, and optional project_id                                       │
│    • Sends HTTP POST -> http://localhost:8000/api/chat                                                                       │
└────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────┘
                                                 │
                                                 ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. API & SECURITY GATEWAY                                                                                                    │
│    Files: app/api/routes/chat.py | app/api/dependencies.py | app/domain/services/authorization_engine.py                      │
│    • get_chat_principal: Extracts user identity & JWT claims                                                                 │
│    • AuthorizationEngine: Builds AuthorizationScope (roles, project_ids, document_ids, is_admin)                             │
└────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────┘
                                                 │
                                                 ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. QUERY ORCHESTRATOR ENTRY & RELEVANCE FEEDBACK CHECK                                                                       │
│    File: app/use_cases/chat/query_orchestrator.py (QueryOrchestrator.answer)                                                 │
│    • PipelineTracer starts trace (app/infrastructure/observability/pipeline_tracer.py)                                       │
│    • Checks if turn is feedback ("Yes" -> returns pending citations; "No" -> evicts cache & generates alternative answer)    │
└────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────┘
                                                 │ (New Question)
                                                 ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 4. QUERY NORMALIZATION & POS SYNONYM CLUSTERING                                                                              │
│    Files: app/use_cases/chat/query_normalizer.py | app/use_cases/chat/synonym_clustering.py                                  │
│    • Cleans conversational boilerplate ("please tell me", "what is")                                                         │
│    • POS Noun extraction (NN, NNS, NNP, NNPS) & Canonical Lemmatization ("leaves" -> "leave", "policies" -> "policy")       │
│    • Synonym cluster expansion via cosine similarity (e.g. "medical" -> "health insurance")                                  │
│    • Outputs: normalized_query & canonical cache_key                                                                         │
└────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────┘
                                                 │
                                                 ▼
                             ┌───────────────────────────────────────┐
                             │ 5. SEMANTIC CACHE LOOKUP              │
                             │    app/infrastructure/cache/          │
                             │    - langcache_adapter.py (Redis)     │
                             │    - quality_aware_cache.py (RAM)     │
                             └───────────────────┬───────────────────┘
                                                 │
                        ┌────────────────────────┴────────────────────────┐
                 [Cache Hit]                                       [Cache Miss]
                        │                                                 │
                        ▼                                                 ▼
       ┌─────────────────────────────────┐               ┌───────────────────────────────────────┐
       │ Cache Read Quality Gate         │               │ 6. FAQ SIMILARITY CACHE LOOKUP        │
       │ app/core/cache_quality.py       │               │    app/infrastructure/faq/            │
       │ (Reject if negative refusal)    │               │    - faq_similarity_cache.py          │
       └──────────────┬──────────────────┘               │    - data/faqs.json                   │
                      │                                  └───────────────────┬───────────────────┘
              ┌───────┴───────┐                                              │
           [Valid]        [Negative]                            ┌────────────┴────────────┐
              │               │                          [FAQ Hit]                    [FAQ Miss]
              │               ▼ (Evict cache)                   │                         │
              │         ┌─────────────┐                         ▼                         ▼
              │         │ Continues to│             ┌───────────────────────┐ ┌─────────────────────────┐
              │         │ FAQ stage   │             │ Return Curated Answer │ │ 7. MULTI-TURN RESOLVER  │
              │         └─────────────┘             │ + FAQ Citation        │ │    app/use_cases/chat/    │
              │                                     └───────────┬───────────┘ │    conversation_query_  │
              │                                                 │             │    resolver.py          │
              │                                                 │             └───────────┬─────────────┘
              │                                                 │                         │ (Resolved Context Query)
              │                                                 │                         ▼
              │                                                 │             ┌─────────────────────────┐
              │                                                 │             │ 8. VECTOR RETRIEVAL     │
              │                                                 │             │    app/use_cases/chat/  │
              │                                                 │             │    retrieval_service.py │
              │                                                 │             │    app/infrastructure/  │
              │                                                 │             │    vector/chroma_client │
              │                                                 │             │    (ChromaDB: .chroma/) │
              │                                                 │             │    + RBAC Meta Filter   │
              │                                                 │             └───────────┬─────────────┘
              │                                                 │                         │ (Top-K Chunks)
              │                                                 │                         ▼
              │                                                 │             ┌─────────────────────────┐
              │                                                 │             │ 9. RERANKER & QUALITY   │
              │                                                 │             │    GATE                 │
              │                                                 │             │    app/use_cases/chat/  │
              │                                                 │             │    retrieval_quality.py │
              │                                                 │             │    - HIGH/MED/LOW/INSUF │
              │                                                 │             └───────────┬─────────────┘
              │                                                 │                         │
              │                                                 │             ┌───────────┴─────────────┐
              │                                                 │      [Pass Quality]             [Insufficient]
              │                                                 │             │                         │
              │                                                 │             ▼                         ▼
              │                                                 │ ┌───────────────────────┐ ┌───────────────────────┐
              │                                                 │ │ 10. RAG PROMPT BUILD  │ │ Fallback Refusal:     │
              │                                                 │ │ app/use_cases/chat/   │ │ "Information not found│
              │                                                 │ │ rag_context_builder.py│ │ in documents."        │
              │                                                 │ └───────────┬───────────┘ └───────────┬───────────┘
              │                                                 │             │                         │
              │                                                 │             ▼                         │
              │                                                 │ ┌───────────────────────┐             │
              │                                                 │ │ 11. LLM GENERATION    │             │
              │                                                 │ │ app/infrastructure/   │             │
              │                                                 │ │ llm/fallback_llm_     │             │
              │                                                 │ │ provider.py           │             │
              │                                                 │ │ Primary: Groq         │             │
              │                                                 │ │ (llama-3.3-70b)       │             │
              │                                                 │ │ Fallback: OpenRouter  │             │
              │                                                 │ │ (gemini-2.5-flash)    │             │
              │                                                 │ └───────────┬───────────┘             │
              │                                                 │             │                         │
              │                                                 │             ▼                         │
              │                                                 │ ┌───────────────────────┐             │
              │                                                 │ │ 12. PROVENANCE &      │             │
              │                                                 │ │ CITATIONS             │             │
              │                                                 │ │ app/use_cases/chat/   │             │
              │                                                 │ │ provenance_service.py │             │
              │                                                 │ └───────────┬───────────┘             │
              │                                                 │             │                         │
              │                                                 │             ▼                         │
              │                                                 │ ┌───────────────────────┐             │
              │                                                 │ │ 13. CACHE WRITEBACK   │             │
              │                                                 │ │ (Quality Gate: Skip   │             │
              │                                                 │ │ if negative refusal;  │             │
              │                                                 │ │ Store with Doc IDs,   │             │
              │                                                 │ │ Timestamps & Role)    │             │
              │                                                 │ └───────────┬───────────┘             │
              │                                                 │             │                         │
              ▼                                                 ▼             ▼                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 14. SAFE CONVERSATION LOGGING, TRACER END & CLIENT RESPONSE                                                                  │
│     Files: app/infrastructure/logging/conversation_logger.py | app/infrastructure/observability/pipeline_tracer.py           │
│     • Writes query/response audit log to data/conversation_logs/                                                             │
│     • Completes PipelineTracer stage spans and reports token usage to LangSmith                                              │
│     • Returns ChatResponse JSON to Streamlit UI                                                                              │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Step-by-Step Execution Lifecycle

### Step 1: Client Query Submission
- **File**: [streamlit_app/app.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/streamlit_app/app.py)
- **Role**:
  - The employee types a query into the Streamlit chat widget or selects an HR topic.
  - The frontend constructs a JSON payload containing `question`, `session_id`, `conversation_history`, and optional `project_id`.
  - Dispatches an asynchronous HTTP `POST` request to FastAPI at `http://localhost:8000/api/chat`.

### Step 2: Authentication & RBAC Scope Resolution
- **Files**:
  - [app/api/routes/chat.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/api/routes/chat.py)
  - [app/api/dependencies.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/api/dependencies.py)
  - [app/domain/services/authorization_engine.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/domain/services/authorization_engine.py)
- **Role**:
  - `get_chat_principal` extracts caller identity and roles from JWT / session header.
  - `AuthorizationEngine.authorization_scope(principal, project_id)` determines exact permissions:
    - `is_admin`: True for global admins.
    - `project_ids`: List of projects the user is authorized to access.
    - `document_ids`: Explicit document access grants.
    - `include_unassigned`: Whether public/unassigned company policies are included.

### Step 3: Orchestrator Invocation & Pipeline Tracing
- **Files**:
  - [app/use_cases/chat/query_orchestrator.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/query_orchestrator.py#L251)
  - [app/infrastructure/observability/pipeline_tracer.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/observability/pipeline_tracer.py)
- **Role**:
  - `QueryOrchestrator.answer(...)` begins execution.
  - Decorator `@traceable` registers this trace run with **LangSmith**.
  - Pipeline tracer captures timing across each distinct stage: Normalization, Cache Lookup, Retrieval, Quality Gate, and Generation.

### Step 4: Relevance & Follow-up Detection
- **File**: [app/use_cases/chat/query_orchestrator.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/query_orchestrator.py#L304-L370)
- **Role**:
  - Checks if the user's turn is user feedback (e.g., *"Yes, show references"* or *"No, not helpful"*).
  - If the user says **"Yes"**: returns the pending citations held from the previous turn.
  - If the user says **"No / Not helpful"**: automatically evicts the previous response from cache, generates an alternative answer or surfaces raw document citations, and clears cache keys.

### Step 5: Lexical Normalization, POS Tagging & Lemmatization
- **Files**:
  - [app/use_cases/chat/query_normalizer.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/query_normalizer.py)
  - [app/use_cases/chat/synonym_clustering.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/synonym_clustering.py)
- **Role**:
  - Strips conversational boilerplate (*"can you tell me"*, *"please explain"*).
  - Performs Part-of-Speech (POS) tagging to extract noun phrases (`NN`, `NNS`, `NNP`, `NNPS`).
  - Canonical lemmatization converts plurals and inflections to root forms (e.g., `leaves` -> `leave`, `policies` -> `policy`).
  - Expands domain synonyms via vector clustering mappings (e.g., `medical` -> `health insurance`).
  - Produces a standardized `cache_key` and clean search query.

### Step 6: Semantic Caching Tier (LangCache & QualityAwareCache)
- **Files**:
  - [app/infrastructure/cache/langcache_adapter.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/cache/langcache_adapter.py)
  - [app/infrastructure/cache/quality_aware_cache.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/cache/quality_aware_cache.py)
  - [app/core/cache_quality.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/core/cache_quality.py)
- **Role**:
  - **RBAC Isolation**: Cache lookup verifies user roles and permitted document IDs match the entry's access envelope.
  - **Document Freshness**: Verifies document timestamps have not changed since caching.
  - **Read Quality Gate**: If a cached response contains negative refusal patterns (*"I don't know"*), it is evicted immediately.
  - **On Hit**: Instantly returns answer with `tokens = 0` and latency ~5ms.

### Step 7: FAQ Similarity Cache Lookup
- **Files**:
  - [app/infrastructure/faq/faq_similarity_cache.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/faq/faq_similarity_cache.py)
  - [data/faqs.json](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/data/faqs.json)
- **Role**:
  - Computes cosine similarity of the query vector against curated company FAQs.
  - If similarity exceeds `FAQ_SIMILARITY_THRESHOLD` (e.g. 0.85), returns curated HR answer immediately without calling the LLM.

### Step 8: Multi-Turn Conversation Resolution
- **File**: [app/use_cases/chat/conversation_query_resolver.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/conversation_query_resolver.py)
- **Role**:
  - Resolves pronouns and elliptical questions (e.g., User: *"How many days?"* -> Resolved: *"How many days of bereavement leave are allowed for full-time employees?"*).

### Step 9: Vector Retrieval & Metadata Filtering
- **Files**:
  - [app/use_cases/chat/retrieval_service.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/retrieval_service.py)
  - [app/infrastructure/vector/chroma_client.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/vector/chroma_client.py)
- **Role**:
  - Embeds query and queries ChromaDB (`.chroma/` collection).
  - Appends MongoDB / Chroma metadata filters:
    - User project IDs
    - Explicit document IDs
    - Public / unassigned documents
  - Pulls top candidate chunks (`RAG_CANDIDATE_COUNT`).

### Step 10: Reranking & Retrieval Quality Gate
- **Files**:
  - [app/use_cases/chat/retrieval_quality.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/retrieval_quality.py)
  - [app/infrastructure/rerank/reranker.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/rerank/reranker.py)
- **Role**:
  - Reranker sorts candidates using deep cross-attention scores.
  - `RetrievalQualityGate.evaluate()` grades evidence:
    - Calculates distance spread, grounding score, and semantic density.
    - Classifies evidence as `HIGH`, `MEDIUM`, `LOW`, or `INSUFFICIENT`.
    - If `INSUFFICIENT`, halts the pipeline before calling LLM to save token cost and prevent hallucinations.

### Step 11: Context Building & Fallback LLM Generation
- **Files**:
  - [app/use_cases/chat/rag_context_builder.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/rag_context_builder.py)
  - [app/infrastructure/llm/fallback_llm_provider.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/llm/fallback_llm_provider.py)
  - [app/infrastructure/llm/groq_client.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/llm/groq_client.py)
  - [app/infrastructure/llm/openrouter_client.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/llm/openrouter_client.py)
  - [app/infrastructure/llm/provider_health.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/llm/provider_health.py)
- **Role**:
  - `RAGContextBuilder` packs top chunks into bounded prompt with strict grounding instructions.
  - `FallbackLLMProvider` tries **GroqClient** (`llama-3.3-70b-versatile`).
  - If Groq experiences rate limits or server timeouts (monitored by circuit breaker in `provider_health.py`), it automatically fails over to **OpenRouterClient** (`google/gemini-2.5-flash`).

### Step 12: Provenance Attribution & Citations
- **File**: [app/use_cases/chat/provenance_service.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/provenance_service.py)
- **Role**:
  - Extracts source document name, section title, page numbers, and snippet text.
  - Attaches unique citations to the response payload.

### Step 13: Writeback & Conversation Logging
- **Files**:
  - [app/infrastructure/cache/langcache_adapter.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/cache/langcache_adapter.py#L225)
  - [app/infrastructure/logging/conversation_logger.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/logging/conversation_logger.py)
  - [app/infrastructure/observability/langsmith_integration.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/observability/langsmith_integration.py)
- **Role**:
  - **Write Quality Gate**: If the generated response is negative (*"I cannot find that in the documents"*), caching is bypassed to avoid locking in negative answers.
  - Positive answers are persisted to Redis LangCache and RAM cache with RBAC tags and doc timestamps.
  - Audit trail recorded in `conversation_logs/` JSONL files.
  - Token counts sent to LangSmith for tracking cost and latency.

---

## 3. Component & File Reference Matrix

| Processing Stage | Primary Component Class | Implementation File | Key Outputs |
| :--- | :--- | :--- | :--- |
| **Presentation** | Streamlit Web App | [streamlit_app/app.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/streamlit_app/app.py) | User question JSON payload |
| **REST API Route** | FastAPI Chat Router | [app/api/routes/chat.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/api/routes/chat.py) | `ChatRequest`, `ChatResponse` |
| **Security & RBAC** | `AuthorizationEngine` | [app/domain/services/authorization_engine.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/domain/services/authorization_engine.py) | `AuthorizationScope` (roles, project permissions) |
| **Orchestration** | `QueryOrchestrator` | [app/use_cases/chat/query_orchestrator.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/query_orchestrator.py) | Pipeline coordination & state machine |
| **Normalization** | `QueryNormalizer` | [app/use_cases/chat/query_normalizer.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/query_normalizer.py) | Clean query string, normalized `cache_key` |
| **POS & Synonyms** | `SynonymClusteringService` | [app/use_cases/chat/synonym_clustering.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/synonym_clustering.py) | Extracted noun lemmas, vector synonym clusters |
| **Semantic Cache** | `LangCacheAdapter` / `QualityAwareCache` | [app/infrastructure/cache/langcache_adapter.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/cache/langcache_adapter.py) | Sub-10ms cache hit response |
| **FAQ Cache** | `FAQSimilarityCache` | [app/infrastructure/faq/faq_similarity_cache.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/faq/faq_similarity_cache.py) | Curated company HR FAQ answer |
| **Query Expansion** | `ConversationQueryResolver` | [app/use_cases/chat/conversation_query_resolver.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/conversation_query_resolver.py) | Pronoun-resolved standalone retrieval query |
| **Vector Store** | `ChromaVectorStore` | [app/infrastructure/vector/chroma_client.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/vector/chroma_client.py) | Distance-ranked document chunks |
| **Retrieval Engine** | `RetrievalService` | [app/use_cases/chat/retrieval_service.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/retrieval_service.py) | Filtered evidence candidates |
| **Quality Gate** | `RetrievalQualityGate` | [app/use_cases/chat/retrieval_quality.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/retrieval_quality.py) | Evidence quality score & confidence rating |
| **Context Packing** | `RAGContextBuilder` | [app/use_cases/chat/rag_context_builder.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/rag_context_builder.py) | System + Context message payload |
| **LLM Resilience** | `FallbackLLMProvider` & `ProviderHealthTracker` | [app/infrastructure/llm/fallback_llm_provider.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/llm/fallback_llm_provider.py) | Failover management (Groq -> OpenRouter) |
| **Citations** | `ProvenanceService` | [app/use_cases/chat/provenance_service.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/use_cases/chat/provenance_service.py) | Citations list (source, section, text) |
| **Observability** | `PipelineTracer` & `ConversationLogger` | [app/infrastructure/observability/pipeline_tracer.py](file:///c:/Users/ABHINAVNBARGI/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/My%20Coding%20Space/Company-Bot/Company_Bot/app/infrastructure/observability/pipeline_tracer.py) | Trace metrics & audit logs |
