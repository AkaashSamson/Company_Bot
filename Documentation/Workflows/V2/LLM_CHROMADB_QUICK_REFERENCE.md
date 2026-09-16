# LLM + ChromaDB Quick Reference

## How It Works (30 seconds)

1. **User asks a question**
2. **FAQ cache checks** if exact match exists (fast path)
3. **ChromaDB retrieves** relevant document chunks
4. **LLM generates** answer using ONLY those chunks
5. **Citations** provided from source documents

## Key Files

| File | Purpose |
|------|---------|
| `app/use_cases/chat/rag_context_builder.py` | Formats ChromaDB chunks → LLM prompts |
| `app/use_cases/chat/query_orchestrator.py` | Orchestrates entire RAG pipeline |
| `app/use_cases/chat/retrieval_service.py` | ChromaDB querying & filtering |
| `app/infrastructure/llm/openrouter_client.py` | LLM API client (OpenRouter) |

## Environment Configuration

```env
# ChromaDB & Embeddings
COLLECTION_NAME=hr_policy_docs
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Retrieval Tuning (0.0 = perfect, 1.0 = worst)
RAG_DISTANCE_THRESHOLD=0.50         # Keep only this close or closer
RAG_DISTANCE_RELAXATION=0.15        # Wiggle room for top result
RAG_MIN_DISTANCE_GAP=0.10           # Must be distinct from 2nd place
RAG_CANDIDATE_COUNT=5               # Initial pool size
RAG_MAX_EVIDENCE=3                  # Final context chunks
RAG_MAX_CONTEXT_CHARS=12000         # Max prompt size

# LLM
LLM_MODEL=openrouter/anthropic/claude-3.5-sonnet
OPENROUTER_API_KEY=sk-or-...
GROQ_API_KEY=gsk-...                # Fallback

# FAQ Cache
FAQ_SIMILARITY_CACHE_ENABLED=true
FAQ_SIMILARITY_THRESHOLD=0.92       # Must match 92% to use cached answer
FAQ_JSON_PATH=data/faqs.json

# Response Caching
LLM_CACHE_SIZE=128                  # In-memory LRU entries
```

## Code Usage

### Basic RAG Flow
```python
from app.use_cases.chat.query_orchestrator import QueryOrchestrator

orchestrator = QueryOrchestrator()
result = orchestrator.answer(
    question="What is the leave policy?",
    conversation_history=[...],
    session_id="user-123"
)

print(result["answer"])        # LLM response
print(result["citations"])     # Source documents
print(result["cache_hit"])     # Was it from FAQ cache?
```

### Direct Context Building
```python
from app.use_cases.chat.rag_context_builder import RAGContextBuilder
from app.use_cases.chat.retrieval_service import RetrievalService

retrieval = RetrievalService()
docs = retrieval.retrieve("leave policy", top_k=3)

builder = RAGContextBuilder()
messages = builder.build_messages(
    question="What is the leave policy?",
    context_chunks=docs,
    include_system_prompt=True,
)

# messages now ready for LLM
```

## Tuning Guide

### Too Slow?
```env
RAG_CANDIDATE_COUNT=3          # Was 5 → Retrieve fewer
RAG_MAX_EVIDENCE=2             # Was 3 → Less context
LLM_MODEL=...llama-3.1...      # Faster model
```

### Inaccurate Answers?
```env
RAG_DISTANCE_THRESHOLD=0.60    # Was 0.50 → More lenient
RAG_MAX_EVIDENCE=4             # Was 3 → More context
LLM_MODEL=...claude-3.5...     # Better model
```

### Not Finding Documents?
```env
RAG_DISTANCE_THRESHOLD=0.40    # Was 0.50 → More lenient
RAG_CANDIDATE_COUNT=10         # Was 5 → Retrieve more
FAQ_SIMILARITY_THRESHOLD=0.85  # Was 0.92 → More lenient FAQ match
```

## Response Format

```python
{
    "answer": "Employees receive 18 days of Annual Leave per year... Would you like to see the references for this?",
    "citations": [],           # Empty until user asks
    "cache_hit": False,        # True = from FAQ/LRU cache
    "matched_faq": "...",      # Optional: which FAQ matched
    "similarity": 0.95         # Optional: match score
}
```

## Performance Targets

| Operation | Target Speed |
|-----------|--------------|
| FAQ cache hit | <10ms |
| ChromaDB retrieval | 300-800ms |
| LLM generation | 1-3s |
| **Total (cold)** | **1.5-4s** |
| **Total (FAQ hit)** | **<20ms** |

## Common Issues & Fixes

| Problem | Fix |
|---------|-----|
| LLM uses external knowledge | Lower `RAG_MAX_EVIDENCE`, make system prompt stricter |
| Docs not retrieved | Lower `RAG_DISTANCE_THRESHOLD` from 0.50 to 0.40 |
| Very slow responses | Reduce `RAG_CANDIDATE_COUNT` from 5 to 3 |
| FAQ cache never hits | Lower `FAQ_SIMILARITY_THRESHOLD` from 0.92 to 0.85 |
| Hallucinations | Use `claude-3.5` instead of `llama-3.1` |

## Observability

### Enable LangSmith Tracing
```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls_...
LANGCHAIN_PROJECT=company-bot
```

Visit: https://api.smith.langchain.com to view traces

### Log ChromaDB Queries
```python
import logging
logging.getLogger("app.use_cases.chat.retrieval_service").setLevel(logging.DEBUG)
```

## FAQ

**Q: Why 3 cache layers?**
A: Different tradeoffs — FAQ (fast), LLM (exact), Retrieval (time-based)

**Q: Can I disable ChromaDB and use FAQ only?**
A: Yes, but set `FAQ_SIMILARITY_THRESHOLD=0.0` to always match (not recommended)

**Q: How do I test locally without OpenRouter API?**
A: Mock the `OpenRouterClient.generate()` method or use `GroqClient` with free tier

**Q: What happens if ChromaDB has no results?**
A: Returns "I could not find that information in the available documents."

**Q: Can I use a different LLM?**
A: Yes, implement `LLMProvider` interface and inject into `QueryOrchestrator`
