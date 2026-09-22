# Solved Issues - Neha

This document tracks the issues that have been successfully resolved in the codebase.

## 1. Conversation Log Cleanup Triggered Only at App Startup

**Status:** Solved
**Date:** 2026-09-20

**How this issue was solved:**
- We imported Python's native `asyncio` library into `app/main.py`.
- We defined a new background task function (`periodic_log_cleanup_task`) that operates in an infinite `while True:` loop.
- Inside the loop, the task awaits a sleep timer dictated by the `LOG_CLEANUP_INTERVAL_SECONDS` environment variable (defaulting to 86400 seconds, or 24 hours).
- After waking up, it safely executes the file deletion logic on a background thread using `asyncio.to_thread` to prevent the heavy file operations from freezing the main FastAPI server.
- The task was integrated into FastAPI's `lifespan` event. It starts immediately after the initial synchronous startup cleanup and is gracefully cancelled when the server shuts down.
- An environment variable `LOG_CLEANUP_INTERVAL_SECONDS` was added to `app/core/settings.py` and `.env.example` to allow configurable cleanup intervals without changing the codebase.

## 4. Shared Session ID Collision

**Status:** Solved
**Date:** 2026-09-20

**How this issue was solved:**
- We imported Python's `uuid` library into `streamlit_app/app.py`.
- We added logic to check if a `session_id` exists in the Streamlit `session_state` upon app initialization. If it doesn't exist, we dynamically generate a new one using `str(uuid.uuid4())`.
- We updated the `service.ask` method call to pass `st.session_state.session_id` to the backend, completely eliminating the hardcoded `"streamlit-session"` string.
- We modified the "Log out" button's click handler to call a custom `handle_logout` function. This function resets the authentication token, generates a brand new UUID for the session, and clears the local chat history (`messages = []`). This guarantees session isolation even if multiple users log in on the same browser sequentially.

## 3. Identical Message Timestamps

**Status:** Solved
**Date:** 2026-09-20

**How this issue was solved:**
- We updated the FastAPI Pydantic schema (`ChatMessage` and `ChatRequest` in `app/api/schemas/chat.py`) to include a `question_timestamp`. This prevents FastAPI from dropping the timestamp from the incoming API request.
- In the frontend (`streamlit_app/app.py`), we updated the user's message so it is stamped with `datetime.now(timezone.utc).isoformat()` the exact millisecond they hit "Send". This timestamp is forwarded through `chat_service.py` to the backend.
- The backend `QueryOrchestrator` uses this exact UI timestamp for the user's message in the log, rather than generating its own `now_iso` timestamp, perfectly preserving the actual chat timeline.

## 2. Quadratic Duplication of Conversation Logs

**Status:** Solved
**Date:** 2026-09-20

**How this issue was solved:**
- We updated `app/use_cases/chat/query_orchestrator.py` to stop sending the full conversation history to the logger on every turn. Instead, it now packages only the newest question and answer pair.
- We refactored `app/infrastructure/logging/conversation_logger.py` to remove the in-memory `_active_sessions` dictionary entirely, which was causing duplicate log fragmentation during server restarts or in multi-worker environments.
- We changed the filename schema to explicitly include the `session_id` (`{employee_id}_{session_id}.json`) instead of a timestamp.
- The logger is now completely stateless and relies purely on `os.path.exists()`. If the file exists on disk, it opens it, parses it, appends the newly received messages, and atomically overwrites the file. This completely eliminates quadratic duplication and fragmented log files in production environments without requiring a database migration.

## 5. Silent Fallback to Fake Employee IDs

**Status:** Solved
**Date:** 2026-09-21

**How this issue was solved:**
- We imported `DatabaseEmployeeIdProvider` at the top of `app/infrastructure/logging/conversation_logger.py`.
- We updated the `__init__` method of the `ConversationLogger` to explicitly initialize the `DatabaseEmployeeIdProvider()` by default if no provider is passed in.
- Per your explicit request, we completely removed the `MockEmployeeIdProvider` from the logger and the codebase entirely, ensuring that fake IDs like `"MSS001"` can never be silently injected. Unauthenticated users now correctly receive the `"anonymous"` ID from the database provider, keeping our analytics data perfectly clean.

---

### 6. Issue 6: Hardcoded Chunk Metadata (Section Field)

**What the issue was:**
The application's document ingestion pipeline was statically hardcoding the `section` metadata field to `"Policy"` for every single chunk, resulting in useless metadata and UI citations that all looked the same (e.g., `📄 Handbook — Policy`).

**How this issue was solved:**
- We entirely removed the hardcoded `section` metadata from the document chunking process in `app/use_cases/ingestion/document_processing.py`. 
- We updated the `streamlit_app/app.py` citation formatting function to stop rendering the `— {section}` string.
- All integration and unit tests that expected `"section": "Policy"` were updated to reflect this removal.
- This approach avoids unnecessary LLM processing for section extraction while streamlining the metadata payload and keeping the UI citations clean.

---

### 8. Issue 8: Hardcoded and Context-Blind Query Retrieval

**What the issue was:**
The `RetrievalService` utilized an extremely brittle regex-based method called `_query_parts()` that attempted to inject hardcoded synonyms (e.g., adding "annual leave entitlement" whenever the user typed "leaves"). Because of this artificial modification, the database performed exactly as instructed but entirely failed to resolve pronouns like "it" from earlier in the chat (i.e., it was context-blind). 

**How this issue was solved:**
- We entirely deleted the `_query_parts()` function and the hardcoded regex logic from `app/use_cases/chat/retrieval_service.py`.
- We updated the retrieval loop to just pass the single, finalized `query_text` directly to ChromaDB.
- We rely completely on the pre-existing `ConversationQueryResolver` within `QueryOrchestrator`, which uses an LLM to rewrite dependent follow-ups (e.g., "Does it apply to contractors?") into fully resolved, standalone search queries based on the last 2-3 chat turns.
- We updated and cleaned the test suite in `tests/unit/test_retrieval_selection.py` to match this streamlined search logic.
