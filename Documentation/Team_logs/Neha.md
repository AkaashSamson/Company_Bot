# Neha - Team Development Log

## Feature: Developer Conversation Logging and Retention
- **Date:** 10 September 2026
- **Feature branch:** `feature/chat-logs`
- **Status:** Implemented and validated

---

## Objective
The Developer Conversation Logging and Retention feature stores completed chatbot conversations as local JSON files for developer and operations analysis. Logs are scoped by employee ID, protect sensitive information via pattern-based redaction, and enforce configurable retention. This capability is strictly for operational diagnostics and is not an authoritative business record, user-facing history store, or analytics platform.

---

## Requirements Implemented
- One JSON log file per completed conversation turn.
- Employee-scoped conversation logs.
- Existing `session_id` used as the sole conversation identifier.
- Chronologically ordered user and assistant messages with UTC timestamps.
- Sensitive-value redaction (credentials, tokens, keys) prior to persistence.
- Configurable log storage directory (`CONVERSATION_LOG_DIR`).
- Configurable retention window (`CONVERSATION_LOG_RETENTION_DAYS`).
- Safe default retention period of 30 days.
- Automatic retention cleanup during application startup.
- Robust failure isolation: logging and cleanup failures never interrupt chatbot responses or FastAPI startup.
- Version control exclusion for local conversation logs.
- Replaceable `EmployeeIdProvider` abstraction boundary.

---

## Key Engineering Decisions
1. **Reuse existing `session_id`**: No separate `conversation_id` was introduced. The application already manages `session_id`, and reusing it avoids redundant identifiers and schema complexity.
2. **`EmployeeIdProvider` abstraction**: An abstract base class decouples employee resolution from logging logic, defining a clean extension point for future production identity services.
3. **Encapsulated temporary mock IDs**: `MSS001`, `MSS002`, and `MSS003` are maintained strictly inside `MockEmployeeIdProvider` for local development. Untrusted arbitrary IDs from user contexts are rejected.
4. **Logger agnostic of mock IDs**: `ConversationLogger` depends only on `EmployeeIdProvider` and contains zero knowledge or hardcoded values of mock IDs.
5. **No database or authentication integration**: Persistence relies entirely on the local filesystem; database and auth integration were intentionally omitted to maintain scope boundaries.
6. **Best-effort non-blocking logging**: Logging is isolated via defensive exception handling. Filesystem, serialization, or permission errors are logged as warnings/errors and never alter or block the chatbot answer delivered to the user.

---

## Implementation
Major components implemented and integrated:
- **Settings (`app/core/settings.py`)**: Added `CONVERSATION_LOG_DIR` and `CONVERSATION_LOG_RETENTION_DAYS` with validation and fallback to 30 days.
- **Domain Entities (`app/domain/entities/conversation_log.py`)**: `ConversationMessage` and `ConversationLog` Pydantic models with `recording_status="completed"`.
- **Domain Service Contract (`app/domain/services/employee_id_provider.py`)**: Abstract base class defining `get_employee_id()`.
- **Infrastructure Provider (`app/infrastructure/logging/mock_employee_id_provider.py`)**: Cycling mock employee provider encapsulating test identities.
- **Logger Service (`app/infrastructure/logging/conversation_logger.py`)**: Handles redaction, collision avoidance, and atomic writes via temporary files.
- **Cleanup Service (`app/infrastructure/logging/conversation_log_cleanup.py`)**: Scans log files and deletes expired logs based on file modification time (`mtime`).
- **Use Case Integration (`app/use_cases/chat/query_orchestrator.py`)**: `_safe_log_conversation()` invoked after successful answer/citation assembly; preserves backward-compatible defaults.
- **Application Startup Cleanup (`app/main.py`)**: Hooked into FastAPI `lifespan` context manager with error isolation.

---

## Conversation Log Format
Each log record contains the following structure:
- `employee_id`: Identifier resolved via the provider.
- `session_id`: Existing session identifier.
- `messages`: List of message objects, each containing:
  - `role`: Role identifier (`user` or `assistant`).
  - `content`: Message text (with sensitive tokens redacted).
  - `timestamp`: ISO 8601 UTC timestamp.
- `recording_status`: `"completed"`.

### Filename & Collision Handling
- **Format:** `<employee_id>_<UTC timestamp>.json` (timestamp format: `YYYYMMDDTHHMMSSZ`).
- **Collision resolution:** If a file with the target name already exists within the same second, an incrementing numeric suffix is appended (e.g., `<employee_id>_<UTC timestamp>_1.json`).

---

## Security / Redaction
Before logs are written to disk, sensitive patterns in message content are redacted:
- Bearer tokens (`Bearer <token>`).
- API keys (including `sk-...`, `gsk_...`, and generic key patterns).
- Passwords and credentials matching key-value assignments.
- Configured secret values (such as `OPENROUTER_API_KEY` and `GROQ_API_KEY`).

Redaction occurs strictly during log serialization; in-memory message history and user responses are never altered.

---

## Retention / Cleanup
- **Safe default:** 30 days.
- **Configuration validation:** `CONVERSATION_LOG_RETENTION_DAYS` must be a positive integer. Non-integer, empty, zero, or negative inputs log a warning and safely fall back to 30 days.
- **Startup cleanup:** Executes automatically during FastAPI application startup via `lifespan`.
- **`mtime` expiry:** Expiration is calculated directly from file modification time (`st_mtime`) without parsing JSON bodies.
- **Preservation:** Non-expired logs, subdirectories, and non-log files are preserved.
- **Per-file isolation:** If deletion of an individual expired file fails, the error is caught, logged, and cleanup proceeds with remaining files.

---

## Issues Encountered and Resolved
1. **Duplicate user message in conversation history:**
   - *Issue:* In contract test fixtures, the current question was being appended to `conversation_history` before calling the endpoint, resulting in duplicate user turns recorded in the log.
   - *Resolution:* Corrected the test fixture to supply distinct prior history, and added a defensive guard in `QueryOrchestrator._safe_log_conversation()` to avoid re-appending the current user prompt if it matches the trailing message in `conversation_history`.
2. **Outdated `GROQ_MODEL` in documentation:**
   - *Issue:* `README.md` listed `llama-3.1-8b-instant` in the configuration section while `.env.example` and confirmed project configuration used `openai/gpt-oss-20b`.
   - *Resolution:* Updated `README.md` to reflect `openai/gpt-oss-20b`, ensuring documentation consistency.

---

## Validation
All test suites pass successfully:
- **API/E2E regression:** 3 passed (`tests/contract/test_chat_api_contract.py`, `tests/integration/test_chat_e2e.py`).
- **Core domain regression:** 28 passed (`tests/unit/` across retrieval selection, conversation resolver, session memory, LLM provider, and document ingestion).
- **Full test suite:** 66 passed (0 failures, 1 deprecation warning from Starlette `BlockingPortal`).

---

## Git Safety
- `conversation_logs/` is explicitly listed in `.gitignore`.
- Verified via `git check-ignore conversation_logs/test.json` that log files are excluded from version control and will not be accidentally staged.

---

## Current Status
- Tasks **T001–T022** are fully implemented and verified against `spec.md`, `plan.md`, and `tasks.md`.
- All requirements, constraints, and boundaries are satisfied.
- Changes are local, unstaged, and uncommitted; no commit or push has been performed.
