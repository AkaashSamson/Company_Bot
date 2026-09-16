# Research: Developer Conversation Logging and Retention

## Decision 1: Use local JSON files as the initial log store

**Decision**: Write one JSON file per completed conversation under a configurable local conversation-log directory.

**Rationale**: The feature is for developer and operations analysis, the specification explicitly requires file-based storage, and the existing application already uses local filesystem storage for input documents and Chroma persistence. This avoids adding a database implementation while keeping the storage replaceable.

**Alternatives considered**:
- MongoDB or another database: rejected for this feature because database/user-identity integration is explicitly not implemented.
- One append-only file: rejected because the specification requires one file per completed conversation and employee-scoped filenames.

## Decision 2: Use a replaceable employee-ID provider

**Decision**: Define a small employee-ID provider abstraction and implement a temporary mock provider returning test IDs such as `MSS001`, `MSS002`, and `MSS003`. The logging service consumes the abstraction and does not contain the IDs.

**Rationale**: The authenticated identity integration is not available yet. Keeping lookup behind an abstraction allows a database-backed provider to replace the mock without changing logging behavior.

**Alternatives considered**:
- Hard-code IDs in the logging service: rejected because it would couple logging to test data.
- Add database integration now: rejected by the feature scope.

## Decision 3: Use the existing session ID as the conversation identifier

**Decision**: Store the existing `session_id` in each log and do not introduce a separate conversation ID.

**Rationale**: This is an explicit requirement and preserves the current API/session contract.

## Decision 4: Use configurable retention with a 30-day default

**Decision**: Add one application setting for retention days, defaulting to 30, and one setting for the log directory. Cleanup compares file modification time with the retention cutoff.

**Rationale**: A single environment-backed setting makes the retention boundary easy to operate without code changes. File modification time is available without adding fields outside the required log format.

**Alternatives considered**:
- Filename-only age calculation: rejected because the employee/timestamp filename is an identity format, not the authoritative filesystem age source.
- Database TTL: rejected because no database is being introduced.

## Decision 5: Make logging best-effort after answer generation

**Decision**: Record the completed conversation after the answer and citations have been produced. Logging and cleanup errors are logged for developers and swallowed so the chat response is unchanged.

**Rationale**: The specification requires logging failures not to interrupt chat or change retrieval/answer behavior. Recording after answer generation also ensures only completed conversations are logged.

## Decision 6: Use atomic JSON writes and defensive cleanup

**Decision**: Write a temporary file in the log directory, then replace the final JSON path. Cleanup processes matching JSON files independently, preserves non-expired files, and continues after per-file deletion errors.

**Rationale**: Atomic replacement avoids leaving a partially written completed log. Per-file exception handling satisfies the requirement that one deletion failure must not stop cleanup.

## Decision 7: Redact before serialization

**Decision**: Apply a small deterministic redaction function to message content before writing JSON, covering configured secrets/tokens without changing the in-memory chat messages or LLM prompts.

**Rationale**: Redaction must protect persisted logs while preserving chatbot behavior. The redactor belongs at the logging boundary, not in retrieval or provider code.

## Resolved Planning Unknowns

- Proposed settings: `CONVERSATION_LOG_DIR` and `CONVERSATION_LOG_RETENTION_DAYS`.
- Default directory: `conversation_logs/` at the repository root.
- Default retention: `30` days.
- Recording status for a completed file: `completed`.
- Timestamp format in filenames: `YYYYMMDD_HHMMSS` using UTC; collision handling must preserve one-file-per-conversation by adding a deterministic uniqueness suffix only if needed, while retaining the required employee/timestamp prefix.
- No new public API endpoint or user-facing log search is required.
