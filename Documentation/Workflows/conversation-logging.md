# Developer Conversation Logging Workflow

Technical documentation and architecture specification for the Developer Conversation Logging and Retention capability in Company_Bot.

---

## 1. Purpose
The developer conversation logging feature captures completed chatbot exchanges to local JSON files for offline developer inspection, regression debugging, and operations analysis.

This system is strictly a diagnostics tool:
- It is **not** an authoritative business or audit record.
- It is **not** an end-user conversation history or profile store.
- It does **not** expose search or query endpoints to end users or the Streamlit UI.

---

## 2. High-Level Flow

Conversation capture occurs asynchronously at the very end of the chat turn lifecycle, strictly after the response and citations have been completely assembled:

```text
User
  → Chat API (/api/chat)
  → Query Orchestrator
  → Query resolution / Retrieval / LLM generation / Provenance citations
  → Completed response assembled
  → Conversation Logger (_safe_log_conversation)
      → EmployeeIdProvider (resolves employee_id)
      → Pattern-based redaction (credentials, tokens, secrets)
      → JSON serialization (ConversationLog model)
      → Atomic file write (temp file + os.replace)
      → conversation_logs/<employee_id>_<timestamp>.json
```

**Key principle:** Logging happens after the answer and citations are successfully assembled. Any failure during logging is trapped and logged; it never impedes returning the answer to the user.

---

## 3. Conversation Identity
The existing `session_id` is the sole conversation identifier.
- No separate `conversation_id` is introduced.
- The `session_id` provided by the client (or the fallback default) is passed directly from `ChatRequest` through `QueryOrchestrator` into the `ConversationLog` record.

---

## 4. Employee Identity
Employee identity resolution is decoupled via the `EmployeeIdProvider` abstract service:
- **Abstract Interface:** `EmployeeIdProvider` defines `get_employee_id(user_context: Optional[dict]) -> str`.
- **Temporary Mock Implementation:** `MockEmployeeIdProvider` encapsulates a cycling set of local test identifiers (`MSS001`, `MSS002`, `MSS003`).
- **Untrusted Context Guard:** Arbitrary user-supplied employee IDs in `user_context` are not trusted; unrecognized IDs are discarded in favor of valid mock IDs.
- **Future Integration:** A future database or authentication-backed identity provider can be plugged directly into the `EmployeeIdProvider` boundary without changing any code in `ConversationLogger`.

---

## 5. Configuration
Configuration is loaded via environment variables in `app/core/settings.py`:

```text
CONVERSATION_LOG_DIR=conversation_logs
CONVERSATION_LOG_RETENTION_DAYS=30
```

### Validation & Fallback Rules
- `CONVERSATION_LOG_RETENTION_DAYS` must parse to a positive integer (`> 0`).
- If the variable is missing, empty, zero, negative, or a non-integer string, the settings layer emits a warning and safely falls back to the default of `30` days.

---

## 6. Log File Naming
Each conversation turn is written to a dedicated JSON file using the naming pattern:

```text
<employee_id>_<UTC timestamp>.json
```

- **Timestamp format:** `YYYYMMDDTHHMMSSZ` (UTC ISO 8601 compact format).
- **Collision Handling:** If multiple completed conversations occur for the same employee within the same second, an incrementing numerical suffix is automatically appended before the file extension (e.g., `<employee_id>_<UTC timestamp>_1.json`, `<employee_id>_<UTC timestamp>_2.json`).

---

## 7. JSON Structure
The schema is validated using Pydantic models in `app/domain/entities/conversation_log.py`. A representative log file:

```json
{
  "employee_id": "MSS001",
  "session_id": "sess-prod-9874",
  "messages": [
    {
      "role": "user",
      "content": "What is the standard annual leave entitlement?",
      "timestamp": "2026-09-10T16:45:00.123456Z"
    },
    {
      "role": "assistant",
      "content": "Employees are entitled to 25 days of paid annual leave per calendar year.",
      "timestamp": "2026-09-10T16:45:02.987654Z"
    }
  ],
  "recording_status": "completed"
}
```

---

## 8. Redaction
Before any log data is written to disk, sensitive tokens and secrets are scrubbed using regular expression matchers in `ConversationLogger`:
- **Bearer Tokens:** `Bearer <token>` patterns.
- **API Keys:** Formats such as `sk-...`, `gsk_...`, and generic key assignments.
- **Passwords:** Key-value pairs referencing passwords or credentials.
- **Configured Secrets:** Any active environment secrets (such as `OPENROUTER_API_KEY` and `GROQ_API_KEY`) are scrubbed if present in message content.

Redaction is performed only on serialized log copies; in-memory message history and user responses are never altered.

---

## 9. Atomic Persistence
To avoid corrupted or partially written JSON files during crashes or concurrent operations, file persistence uses atomic writing:
1. Log content is serialized and written to a temporary file in the target directory using `tempfile.NamedTemporaryFile(delete=False)`.
2. The file stream is flushed to disk.
3. The temporary file is renamed to the final destination path via `os.replace(temp_path, final_path)`.
4. If an error occurs prior to renaming, the temporary file is safely unlinked.

---

## 10. Failure Isolation
Conversation logging is strictly best-effort and non-blocking:
- In `QueryOrchestrator._safe_log_conversation()`, the entire logging invocation is wrapped in a defensive `try...except` block.
- In `ConversationLogger.log_conversation()`, disk, permission, or serialization errors are caught and logged.
- Under no circumstance can a logging failure alter, delay, or prevent the generation and delivery of the user's chatbot response.

---

## 11. Retention and Cleanup
The `ConversationLogCleanup` service maintains the conversation directory within the configured retention boundary:
- **Evaluation Criteria:** File modification time (`st_mtime`) is compared against `now - timedelta(days=retention_days)`.
- **Expired File Deletion:** Files with `st_mtime` older than the threshold are deleted.
- **Preservation:** Non-expired logs are preserved untouched.
- **Unrelated File Safety:** Non-JSON files, hidden files, temporary files, and subdirectories are ignored.
- **Missing Directory Safety:** If the log directory does not exist, cleanup exits gracefully without error.
- **Per-File Error Isolation:** If deletion of an individual file fails (e.g., file lock or permissions), the error is logged and cleanup continues for all remaining candidate files.
- **Repeat-Safe:** The cleanup process is idempotent and safe to run repeatedly.

---

## 12. Startup Integration
Retention cleanup runs automatically during FastAPI application startup:
- Implemented within the FastAPI `lifespan` context manager in `app/main.py`.
- Any exception occurring during startup cleanup is caught and logged; startup cleanup failure **never** halts or crashes application startup.

---

## 13. Git Protection
Local conversation logs are private developer artifacts and are excluded from Git:
- `.gitignore` includes `conversation_logs/`.
- Verified via `git check-ignore conversation_logs/test.json`.

---

## 14. Architecture Components

The feature is organized within the modular monolith architecture across the following components:

- `app/core/settings.py`: Environment configuration and retention parsing with fallback.
- `app/domain/entities/conversation_log.py`: `ConversationMessage` and `ConversationLog` data models.
- `app/domain/services/employee_id_provider.py`: `EmployeeIdProvider` abstract interface.
- `app/infrastructure/logging/mock_employee_id_provider.py`: Temporary mock provider with encapsulated test IDs.
- `app/infrastructure/logging/conversation_logger.py`: Log serialization, redaction, and atomic write service.
- `app/infrastructure/logging/conversation_log_cleanup.py`: File-mtime cleanup service with error continuation.
- `app/use_cases/chat/query_orchestrator.py`: Chat orchestration with non-blocking post-response logging hook.
- `app/api/routes/chat.py`: API endpoint routing passing `session_id` into query orchestrator.
- `app/main.py`: FastAPI application entry point with lifespan startup cleanup hook.

---

## 15. Future Employee Identity Integration

The current architecture provides a clean extension boundary for authentication and enterprise database integration:

```text
Authenticated User / DB Identity
  → EmployeeIdProvider (production implementation)
      → ConversationLogger
```

- **Current state:** `MockEmployeeIdProvider` serves local developer workflows.
- **Future path:** When authentication and user databases are implemented, a new class implementing `EmployeeIdProvider` can be registered without modifying `ConversationLogger` or `QueryOrchestrator`.
- **Note:** No database or authentication integration currently exists in this codebase.

---

## 16. Testing
The implementation is validated by automated test suites:
- **API & Contract Regression:** 1 passed (`tests/contract/test_chat_api_contract.py`).
- **End-to-End Integration:** 2 passed (`tests/integration/test_chat_e2e.py`).
- **Core Unit Domains:** 28 passed (`retrieval_selection`, `conversation_query_resolver`, `session_memory`, `llm_provider`, `document_ingestion`).
- **Feature Unit Tests:** 35 passed (`test_conversation_logger.py`, `test_conversation_log_cleanup.py`, `test_employee_id_provider.py`, `test_query_orchestrator_logging.py`, `test_settings.py`).
- **Full Suite:** **66 passed**, 0 failures (1 non-blocking Starlette deprecation warning).

---

## 17. Scope Boundaries
To safeguard existing functionality, this feature does **not** alter:
- RAG retrieval strategy or candidate selection.
- Out-of-domain grounding or distance threshold filtering.
- Conversational query rewriting or session memory bounding.
- LLM provider client interactions or fallback behavior.
- Streamlit UI rendering or citation display.
- Chatbot API response schema, status codes, or contract behavior.
