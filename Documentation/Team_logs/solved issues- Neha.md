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
