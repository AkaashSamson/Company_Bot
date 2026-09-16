# Token Tracking in LangSmith - Quick Setup

## ✅ What's Implemented

Your bot now automatically tracks and displays token consumption in LangSmith:

- **✅ Token extraction** from OpenRouter API responses
- **✅ LangSmith metadata** with prompt_tokens, completion_tokens, total_tokens
- **✅ Session-based tracking** (group tokens by user)
- **✅ Model tracking** (see which models consume most tokens)
- **✅ Zero overhead** (gracefully degrades if LangSmith disabled)

## 🚀 Quick Start (3 Steps)

### Step 1: Get LangSmith API Key

1. Go to https://api.smith.langchain.com
2. Sign up or log in
3. Click Settings → API Keys
4. Create new key

### Step 2: Update `.env`

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls_your_key_here
LANGCHAIN_PROJECT=company-bot
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

### Step 3: Restart App

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 📊 View Token Usage

1. Go to https://api.smith.langchain.com
2. Click on "company-bot" project
3. Each conversation appears as a trace
4. Click any trace → expand "LLMGenerate" step
5. See metadata:
   - `prompt_tokens`: 342
   - `completion_tokens`: 156
   - `total_tokens`: 498
   - `model`: claude-3.5-sonnet

## 📈 What Gets Tracked

### Per API Call:
- Prompt tokens (your question + context)
- Completion tokens (LLM response)
- Total tokens (sum of both)
- Model name
- Session ID
- Timestamp

### Example Trace:
```
QueryOrchestrator.answer (chain)
├── RAGRetrieval (retriever)
│   └── Retrieved 3 documents
├── LLMGenerate (llm) ← TOKEN COUNTS HERE
│   ├── prompt_tokens: 342
│   ├── completion_tokens: 156
│   ├── total_tokens: 498
│   └── model: claude-3.5-sonnet
└── Duration: 2.1s
```

## 💰 Cost Calculation

OpenRouter pricing (September 2026):
- Claude 3.5 Sonnet: $3 per 1M input, $15 per 1M output
- Llama 3.1: $0.07 per 1M input, $0.10 per 1M output

**Example cost:**
```
342 input × $3/M + 156 output × $15/M
= $0.001026 + $0.00234
= $0.003366 per call (~0.34¢)
```

## 🎯 Key Features

| Feature | Status | Where |
|---------|--------|-------|
| Token extraction | ✅ | `openrouter_client.py` → `_track_tokens()` |
| LangSmith metadata | ✅ | `openrouter_client.py` → `_add_tokens_to_langsmith()` |
| Session tracking | ✅ | `query_orchestrator.py` → `_generate()` |
| API endpoint stats | ✅ | `/api/tokens/*` endpoints |
| Streamlit display | ✅ | `streamlit_app/app.py` → sidebar metrics |

## 🔧 Customization

### Reduce Token Usage:

```env
# Use FAQ cache (0 tokens for cached answers)
FAQ_SIMILARITY_CACHE_ENABLED=true
FAQ_SIMILARITY_THRESHOLD=0.92

# Fewer context chunks
RAG_MAX_EVIDENCE=2          # was 3

# Use cheaper model
LLM_MODEL=openrouter/meta-llama/llama-3.1-8b-instruct
```

### Monitor Specific Sessions:

Visit LangSmith and search:
```
session_id = "user-123"
```

### Export Token Data:

Use the REST API:
```bash
curl http://localhost:8000/api/tokens/stats
curl http://localhost:8000/api/tokens/by-model
curl http://localhost:8000/api/tokens/recent?limit=100
```

## 🐛 Troubleshooting

### Tokens Not Showing?

1. Check LangSmith enabled:
   ```bash
   echo $LANGCHAIN_TRACING_V2  # Should be: true
   ```

2. Check API key valid:
   ```bash
   curl -H "Authorization: Bearer $LANGCHAIN_API_KEY" \
        https://api.smith.langchain.com/sessions
   ```

3. Check logs for errors:
   ```
   grep -i langsmith app.log
   ```

### Always 0 Tokens?

- Verify OpenRouter API response includes `usage` field
- Check LLM API is working (test with `curl`)
- Verify `LANGCHAIN_TRACING_V2=true` in environment

## 📚 Files Modified/Created

| File | Change |
|------|--------|
| `app/infrastructure/llm/openrouter_client.py` | ✅ Token tracking + LangSmith metadata |
| `app/use_cases/chat/query_orchestrator.py` | ✅ Pass session_id to LLM |
| `app/infrastructure/observability/token_tracker.py` | ✅ Created (internal tracking) |
| `app/api/routes/tokens.py` | ✅ Created (REST API for metrics) |
| `app/main.py` | ✅ Register token metrics endpoints |
| `streamlit_app/app.py` | ✅ Display token sidebar metrics |
| `LANGSMITH_TOKEN_TRACKING.md` | ✅ Detailed guide |

## ✨ Result

Every LLM call now shows in LangSmith with:
- ✅ Token counts
- ✅ Cost estimation
- ✅ Session grouping
- ✅ Model comparison
- ✅ Performance metrics

Done! Go to https://api.smith.langchain.com to see your token usage 📊
