# Implementation Plan: Developer Conversation Logging and Retention

**Branch**: `003-conversation-logging` | **Date**: 2026-09-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-conversation-logging/spec.md`

## Summary

Add best-effort employee-scoped conversation logging to the existing modular monolith. After a chat answer and citations are successfully produced, assemble the completed conversation using the existing `session_id`, resolve an employee ID through a replaceable provider abstraction, redact sensitive values, and atomically write one JSON file under a configurable log directory. Add a defensive cleanup service with a configurable retention period and a 30-day default. Logging and cleanup failures must be observable but must not affect retrieval or answer behavior.

The initial employee-ID implementation is a temporary mock provider. No database implementation, new API, user-facing log search, or retrieval change is included.

## Technical Context

**Language/Version**: Python 3.11 (existing project runtime)

**Primary Dependencies**: Existing Python standard library, FastAPI, Pydantic, pytest; no new database dependency

**Storage**: Local filesystem JSON files in a configurable conversation-log directory; existing Chroma and input storage remain unchanged

**Testing**: pytest unit tests and existing chat regression/contract tests

**Target Platform**: Windows development environment and the existing Python application process

**Project Type**: Modular-monolith web service with Streamlit client

**Performance Goals**: Normal local logging should add no more than 500 ms to completion; cleanup must be safe to repeat

**Constraints**: One JSON file per completed conversation; existing `session_id` only; 30-day default retention; best-effort logging; developer/operations-only access; logs excluded from version control; no retrieval or answer changes

**Scale/Scope**: Initial local developer/operations logging for completed conversations; no external identity or database integration

## Constitution Check

*GATE: Must pass before Phase 0 research and after Phase 1 design.*

- **Architectural boundaries**: PASS. The logger and filesystem adapter remain infrastructure concerns. Employee identity is accessed through a small provider abstraction rather than embedded in the logging service.
- **Ground truth and provenance**: PASS. Logging records the existing answer and citations but does not become an answer source and does not alter retrieval or synthesis.
- **Security and access gates**: PASS WITH MVP LIMITATION. Database-backed authentication and authorization are deferred by the current spec. The feature redacts secrets, restricts logs to developer/operations access, uses a temporary mock identity provider, and excludes logs from version control.
- **Spec-driven development**: PASS. This plan is derived from the approved `003-conversation-logging/spec.md`; implementation tasks will be generated separately.
- **Quality and complexity guardrails**: PASS. The design uses local files, standard-library JSON/time/path operations, a small provider interface, and focused unit tests. No database, service split, or new framework is introduced.

## Project Structure

### Documentation (this feature)

```text
specs/003-conversation-logging/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/requirements.md
└── contracts/                 # Not created: no new external API contract
```

### Source Code (repository root)

```text
app/
├── api/
│   └── routes/chat.py                         # Existing route; no API shape change
├── core/
│   └── settings.py                            # Add log directory/retention settings
├── domain/
│   └── services/
│       └── employee_id_provider.py             # Provider contract
├── infrastructure/
│   └── logging/
│       ├── conversation_logger.py              # Redaction and JSON file writing
│       ├── conversation_log_cleanup.py         # Retention cleanup
│       └── mock_employee_id_provider.py        # Temporary test provider
└── use_cases/
    └── chat/
        └── query_orchestrator.py               # Invoke logger after completed answer

tests/
└── unit/
    ├── test_conversation_logger.py
    ├── test_conversation_log_cleanup.py
    ├── test_employee_id_provider.py
    └── test_query_orchestrator_logging.py

.gitignore                                          # Exclude conversation log directory
```

**Structure Decision**: Keep the feature in the existing modular monolith. The domain layer defines the employee-ID lookup contract, infrastructure owns mock identity, file serialization, redaction, and cleanup, and the orchestrator performs the smallest integration point after answer/citation creation. The API, Streamlit UI, ingestion, retrieval, memory, and LLM provider contracts remain unchanged.

## Design

### Completion and message assembly

- Extend the orchestrator's post-generation path to pass the completed conversation to the logger.
- Preserve the existing `session_id` as the only conversation identifier.
- Preserve message order and attach UTC timestamps to each message.
- Record `recording_status: "completed"` only after the JSON payload is ready for persistence.
- Do not log incomplete requests as completed conversations.

### Employee identity

- Define an `EmployeeIdProvider` abstraction with a method that returns the employee ID associated with the authenticated-user context.
- Implement a temporary mock provider returning test IDs such as `MSS001`, `MSS002`, and `MSS003`.
- Keep mock IDs in the provider, never in `ConversationLogger`.
- Leave a replacement boundary for a later database-backed provider; do not add database integration in this feature.

### File writing

- Read `CONVERSATION_LOG_DIR`, defaulting to `conversation_logs`.
- Build `<employee_id>_<timestamp>.json` using UTC `YYYYMMDD_HHMMSS`.
- Handle same-second collisions without adding a separate conversation identifier.
- Serialize the required fields as readable JSON.
- Redact secrets and tokens before serialization.
- Use a temporary file followed by atomic replacement to avoid partial completed logs.
- Catch and log persistence errors; return normally so chat behavior is unchanged.

### Cleanup

- Read `CONVERSATION_LOG_RETENTION_DAYS`, defaulting to `30`.
- Identify expired JSON logs using filesystem modification time.
- Preserve non-expired and unrelated files.
- Catch deletion errors per file, report them, and continue processing the remaining files.
- Make cleanup safe to run repeatedly.
- Provide an explicit service/entry point for startup or scheduled invocation without adding a new user-facing endpoint.

### Integration boundary

- Keep retrieval, relevance selection, query resolution, memory, provider clients, API schemas, and Streamlit unchanged.
- Invoke logging only after successful answer generation and citation assembly.
- Do not make logging a prerequisite for returning the answer.

## Testing Plan

- **Employee provider**: mock provider returns allowed test IDs; logger depends on the abstraction rather than literal IDs.
- **File format**: one file per completed conversation; filename pattern; required JSON fields; ordered messages; UTC timestamps; completed status.
- **Session identity**: existing `session_id` is persisted and no separate conversation ID is generated.
- **Redaction**: token/secret-shaped values are absent or replaced in serialized output.
- **Retention**: default 30 days, configurable boundary, expired deletion, non-expired preservation, repeat-safe cleanup.
- **Failure isolation**: write failure and individual delete failure are logged/observable but do not interrupt the chat path; cleanup continues.
- **Orchestrator integration**: logger receives the final question history, answer, and citations only after successful generation; answer and retrieval result are unchanged when logging is disabled or fails.
- **Regression**: existing API contract, integration, retrieval, memory, conversation-resolution, and provider tests remain unchanged and continue to run.

## Phase 0: Research Summary

Research decisions are recorded in [research.md](research.md): local JSON storage, provider abstraction for employee identity, existing session ID, configurable 30-day retention, best-effort logging, atomic writes, and boundary redaction.

## Phase 1: Design Summary

- [data-model.md](data-model.md) defines `ConversationLog`, `ConversationMessage`, `EmployeeIdProvider`, and file/retention rules.
- [quickstart.md](quickstart.md) defines runnable validation scenarios and test targets.
- No contracts directory is needed because this feature does not add or change an external API.

## Complexity Tracking

No constitution violations require justification. The design adds one small domain provider contract, local infrastructure services, configuration values, and a post-answer orchestration hook without introducing a database or new deployment boundary.
