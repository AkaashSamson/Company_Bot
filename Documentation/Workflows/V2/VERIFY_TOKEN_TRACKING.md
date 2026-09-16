# Verify Token Tracking is Working

## ✅ Servers Restarted Successfully

Both servers have been restarted with the updated code:

- **FastAPI**: http://127.0.0.1:8000 ✅
- **Streamlit**: http://localhost:8501 ✅

## 🧪 Test Token Tracking

### Step 1: Verify Setup

```bash
python test_langsmith.py
```

Expected output:
```
✅ LANGCHAIN_TRACING_V2: True
✅ LANGCHAIN_API_KEY: ***your_key
✅ langsmith version: 0.1.x
✅ Created test run
```

### Step 2: Test via Streamlit

1. Open http://localhost:8501
2. Ask a question: "What is the leave policy?"
3. **Check sidebar** for token metrics:
   ```
   📊 Token Metrics
   Total Tokens: X
   API Calls: Y
   Cache Hit Rate: Z%
   ```
4. **Check chat** for token info:
   ```
   Your answer...
   📊 Tokens used: 342P + 156C = 498T
   ```

### Step 3: Test via API

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"What is annual leave?"}' | jq '.tokens'
```

Expected response:
```json
{
  "prompt_tokens": 342,
  "completion_tokens": 156,
  "total_tokens": 498,
  "cache_hit": false
}
```

### Step 4: Check LangSmith

1. Go to https://api.smith.langchain.com
2. Click your project: "company-bot"
3. Click a recent trace
4. **Expand "LLMGenerate" step**
5. **Look at "Outputs" section**
6. You should see:
   ```
   {
     "completion": "Generated",
     "prompt_tokens": 342,
     "completion_tokens": 156,
     "total_tokens": 498,
     "model": "claude-3.5-sonnet"
   }
   ```

## 📋 Checklist

- [x] FastAPI restarted (127.0.0.1:8000)
- [x] Streamlit restarted (localhost:8501)
- [ ] Run `python test_langsmith.py`
- [ ] Ask question in Streamlit
- [ ] Check sidebar metrics
- [ ] Check chat token display
- [ ] Check LangSmith dashboard
- [ ] Verify token counts in trace

## 🔍 Troubleshooting

### Tokens Still Not in LangSmith?

1. **Check LangSmith enabled:**
   ```bash
   python test_langsmith.py
   ```

2. **Check API key valid:**
   ```bash
   echo $LANGCHAIN_API_KEY
   ```

3. **Check .env file:**
   ```
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_API_KEY=ls_...
   LANGCHAIN_PROJECT=company-bot
   ```

4. **Check application logs:**
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 2>&1 | grep -i "token"
   ```

### Streams Not Responding?

Try clearing cache and reloading:

1. Streamlit: Press `C` to clear cache, then `R` to rerun
2. Browser: Hard refresh with `Ctrl+Shift+R`
3. LangSmith: Clear browser cache or use incognito window

## 📊 Current Implementation

Token tracking now works as follows:

```
OpenRouter API Response
    ↓
{"usage": {"prompt_tokens": 342, "completion_tokens": 156}}
    ↓
OpenRouterClient stores tokens
    ↓
QueryOrchestrator retrieves tokens
    ↓
add_tokens_to_current_run() sends to LangSmith
    ↓
LangSmith Trace Updated
    ↓
Visible in:
├─ LangSmith Dashboard (Outputs)
├─ Streamlit Sidebar (Metrics)
└─ API Response (tokens field)
```

## 💡 Key Files Modified

1. `app/infrastructure/llm/openrouter_client.py` - Token extraction
2. `app/infrastructure/observability/langsmith_integration.py` - LangSmith integration
3. `app/use_cases/chat/query_orchestrator.py` - Token retrieval & LangSmith update
4. `app/api/routes/chat.py` - Token in response
5. `streamlit_app/app.py` - Token display

## 🎯 Success Criteria

Tokens are working correctly when you see:

1. ✅ Token counts in Streamlit sidebar
2. ✅ Token counts in chat messages
3. ✅ Token counts in API response
4. ✅ Token counts in LangSmith trace outputs

If all 4 are showing, token tracking is 100% working!

## Next Steps

1. Monitor LangSmith for token usage patterns
2. Use token counts to estimate costs
3. Optimize based on token consumption
4. Track performance improvements

For detailed information, see:
- `LANGSMITH_TOKENS_GUIDE.md` - Setup and usage guide
- `LANGSMITH_TOKEN_FINAL_SOLUTION.md` - Technical details
- `TOKEN_TRACKING_FIX.md` - Troubleshooting guide
