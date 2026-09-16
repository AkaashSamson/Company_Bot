# Displaying Tokens in LangSmith - Complete Guide

## Quick Setup (5 minutes)

### Step 1: Enable LangSmith in `.env`

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls_your_api_key_here
LANGCHAIN_PROJECT=company-bot
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

### Step 2: Get LangSmith API Key

1. Go to [api.smith.langchain.com](https://api.smith.langchain.com)
2. Sign up or log in
3. Click **Settings** (gear icon)
4. Click **API Keys**
5. Click **Create New API Key**
6. Copy the key starting with `ls_`

### Step 3: Restart Your App

```bash
# Terminal 1: Start FastAPI
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2: Start Streamlit
streamlit run streamlit_app/app.py
```

### Step 4: Ask a Question

1. Open Streamlit app at http://localhost:8501
2. Ask a question: "What is the leave policy?"
3. Wait for response

### Step 5: Check LangSmith

1. Go to [api.smith.langchain.com](https://api.smith.langchain.com)
2. Click your project: "company-bot"
3. You should see your conversation as a trace
4. Click on the trace to expand it
5. **Expand "LLMGenerate" step**
6. **Look for token counts in outputs:**
   ```
   prompt_tokens: 342
   completion_tokens: 156
   total_tokens: 498
   model: claude-3.5-sonnet
   ```

## Verify Setup

Run the test script:

```bash
python test_langsmith.py
```

Expected output:
```
LangSmith Integration Test
=====================================================================
1. Checking LangSmith Configuration:
   LANGCHAIN_TRACING_V2: True
   LANGCHAIN_API_KEY: ***your_key_last_10_chars
   LANGCHAIN_PROJECT: company-bot

2. Checking if langsmith is installed:
   ✅ langsmith version: 0.1.x

3. Testing LangSmith trace:
   ✅ Created test run: abc123...
   ✅ Updated run with token data
   
   Visit: https://api.smith.langchain.com/
   Project: company-bot

4. Testing @traceable decorator:
   ✅ Decorator syntax is correct
```

## Where Tokens Appear in LangSmith

### Trace View

```
📊 Conversation Trace
├── 🔗 QueryOrchestrator.answer (chain)
│   ├── 🔍 RAGRetrieval (retriever)
│   │   └── Retrieved: 3 documents
│   ├── 🤖 LLMGenerate (llm)  ← CLICK HERE
│   │   ├── Model: claude-3.5-sonnet
│   │   ├── Inputs: {...}
│   │   ├── Outputs:  ← TOKEN COUNTS HERE
│   │   │   ├─ prompt_tokens: 342
│   │   │   ├─ completion_tokens: 156
│   │   │   ├─ total_tokens: 498
│   │   │   └─ model: claude-3.5-sonnet
│   │   └── Duration: 2.1s
│   └── FAQSimilarityCache.search (retriever)
```

## How to Read Token Information

| Field | Meaning | Example |
|-------|---------|---------|
| `prompt_tokens` | Tokens in your question + context | 342 |
| `completion_tokens` | Tokens in the LLM response | 156 |
| `total_tokens` | Sum of prompt + completion | 498 |
| `model` | Which model was used | claude-3.5-sonnet |

## Estimate Costs

OpenRouter pricing (September 2026):
- Claude 3.5 Sonnet: $3/M input, $15/M output
- Llama 3.1: $0.07/M input, $0.10/M output

**Cost calculation:**
```
342 input × $3/1M + 156 output × $15/1M
= $0.001026 + $0.00234
= $0.003366 per call (~0.34¢)
```

## Troubleshooting

### Tokens Not Showing in LangSmith?

#### Check 1: Is LangSmith enabled?

```bash
# Run test script
python test_langsmith.py

# Check output for:
# LANGCHAIN_TRACING_V2: True
# langsmith version: 0.x.x
```

#### Check 2: Is API key valid?

```bash
# Test API connection
curl -H "Authorization: Bearer $LANGCHAIN_API_KEY" \
     https://api.smith.langchain.com/sessions

# Should return: {"sessions": [...]}
# If error: Check API key is correct and not expired
```

#### Check 3: Are tokens being extracted?

```bash
# Check application logs for:
grep -i "Token usage" app.log

# Should show:
# "Token usage: prompt=342, completion=156, total=498, model=claude-3.5-sonnet"
```

#### Check 4: Check API response format

```bash
# Make a chat request
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "test"}' | jq '.tokens'

# Should show:
{
  "prompt_tokens": 342,
  "completion_tokens": 156,
  "total_tokens": 498,
  "cache_hit": false
}
```

### Still Not Working?

1. **Restart FastAPI** - Changes to .env require restart
2. **Check .env file** - Make sure file has correct formatting
3. **Verify API key** - Copy fresh from LangSmith UI
4. **Check network** - Ensure you can reach api.smith.langchain.com
5. **View application logs** - Look for error messages

## File Changes

Files updated to support LangSmith token tracking:

1. **`openrouter_client.py`**
   - Extracts tokens from API response
   - Stores in `_last_tokens`
   - Adds to LangSmith metadata

2. **`query_orchestrator.py`**
   - Retrieves tokens from LLM provider
   - Calls `add_tokens_to_current_run()` to update LangSmith
   - Includes tokens in response

3. **`langsmith_integration.py`** (NEW)
   - `add_tokens_to_current_run()` - Updates active LangSmith trace
   - `add_token_metadata()` - Adds token metadata
   - `add_tokens_via_extra()` - Creates metadata dict

4. **`test_langsmith.py`** (NEW)
   - Tests LangSmith configuration
   - Verifies API connectivity
   - Creates test traces

## Example: Viewing Tokens in LangSmith UI

### Step-by-step:

1. **Navigate to project**
   ```
   https://api.smith.langchain.com/ → company-bot
   ```

2. **Find your trace**
   ```
   Look for recent traces (sorted by newest first)
   ```

3. **Click trace to expand**
   ```
   Click on any trace to see full details
   ```

4. **Find LLMGenerate step**
   ```
   Expand the "LLMGenerate" operation
   ```

5. **View outputs**
   ```
   Look at "Outputs" section
   You should see:
   {
     "completion": "Generated",
     "prompt_tokens": 342,
     "completion_tokens": 156,
     "total_tokens": 498,
     "model": "claude-3.5-sonnet"
   }
   ```

## Token Visibility Locations

Tokens now visible in **3 places**:

### 1. LangSmith Dashboard ✅
- Navigate to: https://api.smith.langchain.com
- Project: company-bot
- Look for "LLMGenerate" step → Outputs

### 2. Streamlit Sidebar ✅
- Sidebar metrics show:
  - Total Tokens
  - API Calls
  - Avg per Call
  - Cache Hit Rate

### 3. API Response ✅
- `/api/chat` endpoint returns:
  ```json
  {
    "tokens": {
      "prompt_tokens": 342,
      "completion_tokens": 156,
      "total_tokens": 498,
      "cache_hit": false
    }
  }
  ```

## Advanced: Custom Token Tracking

If you want more detailed token tracking:

```python
from app.infrastructure.observability.langsmith_integration import add_tokens_to_current_run

# Manually add tokens to LangSmith
add_tokens_to_current_run(
    prompt_tokens=342,
    completion_tokens=156,
    model="claude-3.5-sonnet"
)
```

## Support

For issues:

1. Run `python test_langsmith.py` - Verify setup
2. Check `.env` file - Verify credentials
3. Check FastAPI logs - Look for errors
4. Check LangSmith dashboard - See if trace created
5. Review this guide - Check setup steps

For LangSmith documentation: https://docs.smith.langchain.com
