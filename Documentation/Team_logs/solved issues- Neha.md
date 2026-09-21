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
- We updated the FastAPI Pydantic schema (`ChatMessage` in `app/api/schemas/chat.py`) to include an `Optional[str]` for `timestamp`. This prevents FastAPI from silently dropping the timestamp from the incoming API request.
- In the frontend (`streamlit_app/app.py`), we imported `datetime` and `timezone`.
- We updated the `st.session_state.messages.append()` calls so that the user's message is stamped with `datetime.now(timezone.utc).isoformat()` the exact millisecond they hit "Send".
- We applied the same logic to the assistant's response so it is stamped the exact moment it arrives.
- The backend logging engine (`conversation_logger.py`) was already programmed to read incoming timestamps, so this data simply passes through the entire stack unmodified, perfectly preserving the actual chat timeline in the JSON log file.

## 2. Quadratic Duplication of Conversation Logs

**Status:** Solved
**Date:** 2026-09-20

**How this issue was solved:**
- We updated `app/use_cases/chat/query_orchestrator.py` to stop sending the full conversation history to the logger on every turn. Instead, it now packages only the newest question and answer pair.
- We added an in-memory dictionary `self._active_sessions = {}` to `app/infrastructure/logging/conversation_logger.py` to track which JSON files belong to which active sessions.
- We implemented an "append mode" in `log_conversation`: if the session is already active, the logger opens the existing JSON file, parses it, appends the newly received messages, and atomically overwrites the file. This completely eliminates quadratic duplication and fragmented log files without requiring a database migration.

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
