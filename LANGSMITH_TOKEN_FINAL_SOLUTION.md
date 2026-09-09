# LangSmith Token Display - Final Solution

## ✅ What's Now Working

Token counts are now properly displayed in **LangSmith traces** with the following structure:

```
LLMGenerate (llm) Run
├── Outputs:
│   ├─ completion: "Generated"
│   ├─ prompt_tokens: 342
│   ├─ completion_tokens: 156
│   ├─ total_tokens: 498
│   └─ model: claude-3.5-sonnet
```

## 🔧 How It Works

### Data Flow:

```
1. OpenRouter API Returns Tokens
   │
   ├─ OpenRouterClient._track_tokens()
   │  └─ Stores in self._last_tokens
   │
   ├─ OpenRouterClient._add_tokens_to_langsmith()
   │  └─ Logs tokens for visibility
   │
2. QueryOrchestrator.answer() Retrieves Tokens
   │
   ├─ Calls self.llm.get_last_tokens()
   │
   ├─ Calls add_tokens_to_current_run()
   │  └─ Updates LangSmith trace with outputs
   │
3. LangSmith Receives Token Data
   │
   └─ Displays in trace UI under "Outputs"
```

## 📝 Files Modified/Created

### New Files:
- ✅ `app/infrastructure/observability/langsmith_integration.py` - LangSmith token API wrapper
- ✅ `test_langsmith.py` - Verification script

### Modified Files:
- ✅ `app/infrastructure/llm/openrouter_client.py` - Token extraction
- ✅ `app/infrastructure/llm/fallback_llm_provider.py` - Token forwarding
- ✅ `app/use_cases/chat/query_orchestrator.py` - Token to LangSmith integration
- ✅ `app/api/routes/chat.py` - Token in response
- ✅ `streamlit_app/app.py` - Token display

## 🚀 Setup (3 Steps)

### Step 1: Configure `.env`

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls_your_key_here
LANGCHAIN_PROJECT=company-bot
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

Get API key from: https://api.smith.langchain.com → Settings → API Keys

### Step 2: Verify Setup

```bash
python test_langsmith.py
```

### Step 3: Run App

```bash
# Terminal 1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2
streamlit run streamlit_app/app.py
```

## 👀 Where to See Tokens

### 1. LangSmith Dashboard (Primary)

1. Go to https://api.smith.langchain.com
2. Click project: "company-bot"
3. Click a trace
4. Expand **"LLMGenerate"** step
5. Look at **"Outputs"** section
6. See token counts

### 2. Streamlit (Secondary)

- Sidebar shows total tokens and metrics
- Chat history shows tokens per message

### 3. API Response (For integration)

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"test"}' | jq '.tokens'
```

## 🔍 Example LangSmith Output

When you expand an "LLMGenerate" trace in LangSmith, you'll see:

```json
{
  "Outputs": {
    "completion": "Generated",
    "prompt_tokens": 342,
    "completion_tokens": 156,
    "total_tokens": 498,
    "model": "claude-3.5-sonnet"
  }
}
```

## ✅ Verification Checklist

- [ ] LANGCHAIN_TRACING_V2=true in .env
- [ ] LANGCHAIN_API_KEY set in .env
- [ ] python test_langsmith.py shows ✅ checks
- [ ] FastAPI running on http://localhost:8000
- [ ] Streamlit running on http://localhost:8501
- [ ] Asked a question in chatbot
- [ ] Check https://api.smith.langchain.com for trace
- [ ] Expand LLMGenerate step
- [ ] See token counts in Outputs

## 🐛 Troubleshooting

### Tokens Not Showing?

**Check 1:** Is LangSmith configured?
```bash
python test_langsmith.py
# Should show: ✅ for all checks
```

**Check 2:** Did you restart the app?
```bash
# Stop and restart FastAPI after changing .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Check 3:** Are tokens being extracted?
```bash
# Look for log messages:
grep -i "token usage" app.log
```

**Check 4:** Is the API key valid?
```bash
# Test connection
curl -H "Authorization: Bearer $LANGCHAIN_API_KEY" \
     https://api.smith.langchain.com/sessions
```

## 📚 Key Functions

### In `langsmith_integration.py`:

```python
def add_tokens_to_current_run(
    prompt_tokens: int,
    completion_tokens: int,
    model: str = "unknown"
) -> None:
    """Add token counts to the current LangSmith trace."""
```

### In `openrouter_client.py`:

```python
def _track_tokens(self, response_data: dict) -> None:
    """Extract tokens from API response."""

def get_last_tokens(self) -> dict:
    """Get tokens from last generate() call."""
```

### In `query_orchestrator.py`:

```python
# Retrieve tokens from LLM
tokens = self.llm.get_last_tokens()

# Add to LangSmith
add_tokens_to_current_run(
    prompt_tokens=tokens.get("prompt_tokens", 0),
    completion_tokens=tokens.get("completion_tokens", 0),
    model=tokens.get("model", "unknown"),
)
```

## 🎯 Token Count Flow

```
OpenRouter API
    ↓
{"usage": {"prompt_tokens": 342, "completion_tokens": 156}}
    ↓
OpenRouterClient.generate()
    ├─ _track_tokens() → stores in tracker
    ├─ _add_tokens_to_langsmith() → logs
    └─ _last_tokens = {...}
    ↓
QueryOrchestrator.answer()
    ├─ get_last_tokens() → retrieves tokens
    ├─ add_tokens_to_current_run() → sends to LangSmith
    └─ returns in response dict
    ↓
ChatResponse
    └─ tokens: {prompt_tokens, completion_tokens, ...}
    ↓
┌────────────────────────────┐
│ LangSmith Dashboard        │
│ └─ LLMGenerate → Outputs   │
│    └─ prompt_tokens: 342   │
│    └─ completion_tokens: 156
│    └─ total_tokens: 498    │
└────────────────────────────┘
```

## 📊 Cost Tracking

With tokens visible in LangSmith, you can now track costs:

- Claude 3.5 Sonnet: $3/M input + $15/M output
- Example: 342 input + 156 output = ~0.34¢ per call

## Summary

✅ **Token tracking is fully implemented and integrated with LangSmith**

Tokens now appear in:
1. **LangSmith Dashboard** - Under "LLMGenerate" → "Outputs"
2. **Streamlit Sidebar** - Real-time metrics
3. **API Response** - Included in chat response
4. **Application Logs** - Logged for audit trail

Run `python test_langsmith.py` to verify everything is working.
