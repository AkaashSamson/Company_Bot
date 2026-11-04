# LLM Configuration for ChromaDB-Based Generation

This document explains how the Company Bot is configured to generate responses using ChromaDB-retrieved documents.

## Architecture Overview

```
User Question
    ↓
FAQ Similarity Cache (Fast path)
    ↓ (miss)
RAG Retrieval (ChromaDB)
    ↓
Context Builder (Formats chunks)
    ↓
LLM Generation (With Context)
    ↓
Response + Citations
```

## Key Components

### 1. **RAG Context Builder** (`app/use_cases/chat/rag_context_builder.py`)

Responsible for formatting ChromaDB-retrieved chunks into optimized LLM prompts.

**Features:**
- **System Prompt Construction**: Guides the LLM to answer only from provided context
- **User Prompt Building**: Formats retrieved chunks with metadata and relevance scores
- **Citation Extraction**: Prepares evidence for user reference
- **Context Size Management**: Respects max context character limits

**Usage:**
```python
from app.use_cases.chat.rag_context_builder import RAGContextBuilder

builder = RAGContextBuilder(
    max_context_chars=12000,
    include_metadata=True,
    include_timestamp=False,
)

# Build complete messages for LLM
messages = builder.build_messages(
    question="What is the leave policy?",
    context_chunks=[...],  # From ChromaDB
    include_system_prompt=True,
)
```

### 2. **Query Orchestrator** (`app/use_cases/chat/query_orchestrator.py`)

Orchestrates the full RAG + LLM pipeline:

1. **FAQ Cache Check**: Fast path for curated Q&A
2. **Query Resolution**: Expands ambiguous questions using LLM
3. **ChromaDB Retrieval**: Gets relevant document chunks
4. **Context Building**: Formats chunks into prompts
5. **LLM Generation**: Generates answer based on context
6. **Citation Building**: Prepares references for user

### 3. **Retrieval Service** (`app/use_cases/chat/retrieval_service.py`)

Manages ChromaDB queries with filtering and deduplication:

- **Query Expansion**: Splits complex questions into sub-queries
- **Distance Filtering**: Removes low-relevance results
- **Deduplication**: Removes redundant chunks
- **Character Limiting**: Bounds total context size

## Configuration Parameters

All parameters are configurable via environment variables in `.env`:

```env
# ChromaDB Settings
COLLECTION_NAME=hr_policy_docs
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# RAG Retrieval Tuning
RAG_DISTANCE_THRESHOLD=0.50        # Max distance (0=perfect, 1=worst)
RAG_DISTANCE_RELAXATION=0.15       # Allow some wiggle room for top result
RAG_MIN_DISTANCE_GAP=0.10          # Minimum gap between top 2 results
RAG_CANDIDATE_COUNT=5              # Chunks to retrieve initially
RAG_MAX_EVIDENCE=3                 # Max chunks in final context
RAG_MAX_CONTEXT_CHARS=12000        # Max characters for LLM context

# LLM Settings
LLM_MODEL=openrouter/anthropic/claude-3.5-sonnet
OPENROUTER_API_KEY=your-key-here
GROQ_API_KEY=your-fallback-key

# FAQ Cache (Pre-RAG)
FAQ_SIMILARITY_CACHE_ENABLED=true
FAQ_SIMILARITY_THRESHOLD=0.92      # Must match question with 92% similarity
FAQ_JSON_PATH=data/faqs.json       # Curated Q&A file

# LLM Response Cache
LLM_CACHE_SIZE=128                 # In-memory LRU cache entries
```

## How It Works: Step by Step

### Step 1: FAQ Similarity Check
```
User: "What is the leave policy?"
  ↓
FAQSimilarityCache searches embedded FAQs
  ↓
If similarity >= threshold → Return cached answer (fast path)
Otherwise → Continue to step 2
```

**Speed**: <10ms (in-memory embedding search)

### Step 2: ChromaDB Retrieval
```
Question: "What is the leave policy?"
  ↓
RetrievalService._query_parts() expands to:
  - "What is the leave policy?"
  - "leave policy"
  - "annual leave entitlement"
  ↓
For each part, query ChromaDB:
  store.query(part, top_k=5)
  ↓
Collect all candidates with metadata
```

**Speed**: ~500ms-1s (includes embedding + DB query)

### Step 3: Context Building
```
Selected chunks from ChromaDB:
[
  {
    "text": "Employees receive 18 days of Annual Leave per year...",
    "metadata": {"section": "Leave Policy", "source": "HR Handbook"},
    "distance": 0.35
  },
  ...
]
  ↓
RAGContextBuilder.build_messages() formats into:
{
  "role": "system",
  "content": "You are an HR assistant. Answer ONLY from provided context..."
}
{
  "role": "user",
  "content": "[Leave Policy]\n18 days of Annual Leave...\n\nQuestion: What is the leave policy?"
}
```

### Step 4: LLM Generation
```
Messages with ChromaDB context
  ↓
LLM (OpenRouter/Claude)
  ↓
Response: "Employees receive 18 days of Annual Leave per calendar year..."
  ↓
Strip reasoning (if thinking model)
  ↓
Return with citations
```

**Speed**: ~1-3s (API call to OpenRouter)

## Prompt Engineering

The system prompt guides the LLM to:

1. **Use ONLY provided context** — No external knowledge
2. **Be concise** — 2-4 sentences max
3. **Handle missing info** — Say "I could not find..." if needed
4. **Indicate citations** — End with "Would you like to see the references?"

**System Prompt:**
```
You are a helpful HR assistant. Your role is to provide accurate answers
based exclusively on the HR policy documents provided to you.

Guidelines:
- Answer ONLY using the provided document context
- Be concise (2-4 sentences)
- If information is not in the context, say "I could not find..."
- Cite relevant sections when applicable
- Do not add external knowledge or assumptions
- End with: "Would you like to see the references for this?"
```

## Performance Tuning

### To Get Faster Responses:

1. **Reduce `RAG_CANDIDATE_COUNT`** (default: 5 → try 3)
   - Retrieves fewer chunks initially
   - Faster but may miss relevant documents

2. **Lower `RAG_MAX_EVIDENCE`** (default: 3 → try 2)
   - Fewer chunks in context
   - LLM processes faster, may lose nuance

3. **Increase `RAG_DISTANCE_THRESHOLD`** (default: 0.50 → try 0.40)
   - Only uses very close matches
   - May reject useful documents

4. **Reduce `LLM_MODEL` complexity**
   - Use faster models (Llama 3.1 vs Claude 3.5)
   - Trade accuracy for speed

### To Get More Accurate Responses:

1. **Lower `RAG_DISTANCE_THRESHOLD`** (allows more matches)
2. **Increase `RAG_MAX_EVIDENCE`** (more context for LLM)
3. **Improve embedding model** (use larger MiniLM or better)
4. **Use more powerful LLM** (Claude 3.5 > Llama 3.1)

## Caching Strategy

Three layers of caching for performance:

### Layer 1: FAQ Similarity Cache (Fastest)
- **When**: Before retrieval
- **Hit rate**: ~10-15% (depends on FAQ coverage)
- **Speed**: <10ms
- **Config**: `FAQ_SIMILARITY_CACHE_ENABLED`, `FAQ_SIMILARITY_THRESHOLD`

### Layer 2: LLM Response Cache (Fast)
- **When**: Exact prompt match detected
- **Hit rate**: ~20-30% (exact duplicates)
- **Speed**: <1ms
- **Config**: `LLM_CACHE_SIZE`

### Layer 3: Retrieval Cache (Medium)
- **When**: Same query retrieved multiple times
- **Hit rate**: ~5-10% (time-dependent)
- **Speed**: ~100ms
- **Config**: Consider Redis for distributed caching

## Testing & Debugging

### Check Context Builder Output:
```python
from app.use_cases.chat.rag_context_builder import RAGContextBuilder

builder = RAGContextBuilder()
messages = builder.build_messages(
    question="Example question?",
    context_chunks=[...],
)
print(messages)
```

### Verify ChromaDB Retrieval:
```python
from app.use_cases.chat.retrieval_service import RetrievalService

service = RetrievalService()
results = service.retrieve("Example question?", top_k=5)
for r in results:
    print(f"Distance: {r['distance']}, Text: {r['text'][:100]}")
```

### Monitor LangSmith (if enabled):
```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your-langsmith-api-key
LANGCHAIN_PROJECT=company-bot
```

Visit [api.smith.langchain.com](https://api.smith.langchain.com) to view traces.

## Common Issues

**Q: LLM is using external knowledge instead of context**
- Decrease `LLM_MODEL` complexity or use a more obedient model
- Make system prompt more explicit
- Reduce `RAG_MAX_EVIDENCE` to force focus on context

**Q: Relevant documents aren't being retrieved**
- Lower `RAG_DISTANCE_THRESHOLD`
- Increase `RAG_CANDIDATE_COUNT`
- Check ChromaDB collection has documents (run ingestion)

**Q: Responses are too slow**
- Use smaller LLM (Llama vs Claude)
- Reduce `RAG_MAX_EVIDENCE`
- Enable FAQ cache
- Consider adding retrieval caching

**Q: Citations are inaccurate**
- Check chunk metadata is stored correctly in ChromaDB
- Verify `ProvenanceService.build_citations()` correctly maps chunks
- Debug with `RAGContextBuilder.format_evidence_for_citations()`

## Next Steps

1. **Monitor response quality** — Test with diverse questions
2. **Tune distance thresholds** — Start with default, adjust based on results
3. **Add retrieval caching** — Consider Redis for production
4. **Implement feedback loop** — Log which sources users find helpful
5. **A/B test LLM models** — Compare quality vs speed tradeoffs
