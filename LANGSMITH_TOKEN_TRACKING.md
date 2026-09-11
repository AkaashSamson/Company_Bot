# LangSmith Token Tracking

Your Company Bot now automatically tracks and displays token usage in LangSmith.

## Setup

### 1. Enable LangSmith Tracing

Set these environment variables in `.env`:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls_your-api-key-here
LANGCHAIN_PROJECT=company-bot
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

### 2. Get LangSmith API Key

1. Go to [api.smith.langchain.com](https://api.smith.langchain.com)
2. Sign up or log in
3. Click "Settings" (gear icon)
4. Under "API Keys", create a new key
5. Copy and paste into `.env`

### 3. Restart Your App

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Viewing Token Usage in LangSmith

### In the Web UI

1. Go to [api.smith.langchain.com](https://api.smith.langchain.com)
2. Navigate to your project ("company-bot")
3. Each conversation will appear as a trace
4. Click on any trace to see details:

```
┌─ QueryOrchestrator.answer (chain) ─────────────┐
│  ├─ RAGRetrieval (retriever)                   │
│  │  └─ Tokens: 0 (no LLM call)                 │
│  ├─ LLMGenerate (llm)                          │
│  │  ├─ Prompt Tokens: 342                      │
│  │  ├─ Completion Tokens: 156                  │
│  │  └─ Total Tokens: 498                       │
│  └─ Duration: 2.3s                             │
└────────────────────────────────────────────────┘
```

### Token Metadata in LangSmith

Each LLM call shows:
- **prompt_tokens** - Tokens in your question + context
- **completion_tokens** - Tokens in the LLM response
- **total_tokens** - Sum of both
- **model** - Which model was used (e.g., "claude-3.5-sonnet")

## What Gets Tracked

### ✅ Tracked Automatically

- Each LLM API call to OpenRouter
- Token counts from the API response
- Session ID (for grouping by user)
- Model name
- Cache hits/misses
- Latency

### Example Trace Structure

```
🔗 QueryOrchestrator.answer
├── 📤 Inputs: {"question": "What is leave policy?", "session_id": "user-123"}
├── 🔍 FAQSimilarityCache.search (retriever)
│   └── ❌ Cache Miss
├── 🔍 RAGRetrieval (retriever)
│   ├── 📤 Query: "leave policy"
│   └── 📨 Retrieved: 3 documents
├── 🤖 LLMGenerate (llm)
│   ├── 📤 Inputs: {"model": "claude-3.5-sonnet"}
│   ├── 📊 Metadata:
│   │   ├─ prompt_tokens: 342
│   │   ├─ completion_tokens: 156
│   │   ├─ total_tokens: 498
│   │   └─ model: "claude-3.5-sonnet"
│   └── ⏱️  Duration: 2.1s
└── 📨 Output: "Employees receive 18 days..."
```

## Analyzing Token Usage

### In LangSmith UI:

1. **Filter by project**: "company-bot"
2. **Sort by**: Duration, Tokens, or Date
3. **Search**: Use query language to find specific sessions or models
4. **Compare**: Click multiple traces to compare token counts

### Example Queries:

```
# Find all traces for a specific user
session_id = "user-123"

# Find expensive operations (>500 tokens)
tags:"llm" AND total_tokens > 500

# Find failures
feedback.rating < 0.5
```

## Calculating Costs

OpenRouter pricing (as of September 2026):

| Model | Input | Output |
|-------|-------|--------|
| Claude 3.5 Sonnet | $3 / M | $15 / M |
| Llama 3.1 | $0.07 / M | $0.10 / M |

**Formula:**
```
Cost = (prompt_tokens × input_rate + completion_tokens × output_rate) / 1,000,000
```

**Example:**
```
342 prompts × $3/M + 156 completions × $15/M
= (342 × 0.000003) + (156 × 0.000015)
= $0.001026 + $0.00234
= $0.003366 per call (~0.33¢)
```

## Performance Tips

### To Reduce Tokens:

1. **Use FAQ cache** - Answers below 50 tokens
   ```env
   FAQ_SIMILARITY_THRESHOLD=0.92
   FAQ_SIMILARITY_CACHE_ENABLED=true
   ```

2. **Reduce context** - Fewer chunks = fewer tokens
   ```env
   RAG_MAX_EVIDENCE=2  # was 3
   ```

3. **Use faster models** - Often have smaller token counts
   ```env
   LLM_MODEL=openrouter/meta-llama/llama-3.1-8b-instruct
   ```

### To See Savings:

Before & After in LangSmith:
- FAQ hits: 0 tokens (cached)
- With optimization: 200 avg tokens
- Without optimization: 500 avg tokens
- Savings: 60% reduction in costs

## Debugging

### Tokens Not Showing?

1. Check LangSmith is enabled:
   ```bash
   echo $LANGCHAIN_TRACING_V2  # Should output: true
   ```

2. Check API key is valid:
   ```bash
   curl -H "Authorization: Bearer $LANGCHAIN_API_KEY" \
        https://api.smith.langchain.com/sessions
   ```

3. Check logs:
   ```bash
   grep "LangSmith" your-app.log
   ```

### Tokens Always 0?

- Check OpenRouter response includes `usage` field
- Verify LLM API is working (test with curl)
- Check for errors in application logs

## Environment Variables Quick Reference

```env
# Enable LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls_xxxx
LANGCHAIN_PROJECT=company-bot
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com

# LLM Settings (affects token counts)
LLM_MODEL=openrouter/anthropic/claude-3.5-sonnet
RAG_MAX_EVIDENCE=3              # Number of context chunks
RAG_MAX_CONTEXT_CHARS=12000    # Max context size

# FAQ Cache (saves tokens)
FAQ_SIMILARITY_CACHE_ENABLED=true
FAQ_SIMILARITY_THRESHOLD=0.92
```

## Support

For questions about LangSmith, visit:
- [LangSmith Docs](https://docs.smith.langchain.com)
- [LangSmith Dashboard](https://api.smith.langchain.com)
