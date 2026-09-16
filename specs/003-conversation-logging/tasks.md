---
description: "Task list for developer conversation logging and retention"
---

# Tasks: Developer Conversation Logging and Retention

**Input**: Design documents from `specs/003-conversation-logging/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `quickstart.md`

**Tests**: Included because the feature specification requires independent validation and regression coverage.

**Organization**: Tasks are grouped by user story and ordered by dependency.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel when dependencies are complete
- **[Story]**: User story mapping for story-phase tasks
- Every task includes the exact file path it changes or validates

## Path Conventions

- Application source: `app/`
- Tests: `tests/`
- Documentation: `README.md`, `specs/003-conversation-logging/quickstart.md`
- Local operational logs: `conversation_logs/`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish configuration and repository conventions shared by all stories.

- [x] T001 Add `CONVERSATION_LOG_DIR` with default `conversation_logs` and `CONVERSATION_LOG_RETENTION_DAYS` with default `30` to `app/core/settings.py`
- [x] T002 [P] Exclude the configured conversation-log directory from version control in `.gitignore`

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the provider and data boundaries required by all conversation-log behavior.

**Checkpoint**: Provider contract, temporary identity source, and log payload boundary are ready before story implementation.

- [x] T003 Define the replaceable employee-ID provider contract in `app/domain/services/employee_id_provider.py`
- [x] T004 [P] Implement the temporary mock employee-ID provider returning test IDs such as `MSS001`, `MSS002`, and `MSS003` in `app/infrastructure/logging/mock_employee_id_provider.py`
- [x] T005 Define the conversation-log and ordered-message payload models with `employee_id`, existing `session_id`, timestamps, and recording status in `app/domain/entities/conversation_log.py`
- [x] T006 Add safe parsing and developer-visible warnings for missing or invalid retention configuration in `app/core/settings.py`

## Phase 3: User Story 1 - Capture conversations for development analysis (Priority: P1) 🎯 MVP

**Goal**: Record each completed employee conversation as one redacted JSON file without changing chatbot answers or retrieval behavior.

**Independent Test**: Complete a chat request and verify one employee-scoped JSON file contains the required identity, session, ordered messages, timestamps, and completed recording status without cleartext secrets.

### Tests for User Story 1

- [x] T007 [P] [US1] Test temporary employee-ID lookup and provider substitution in `tests/unit/test_employee_id_provider.py`
- [x] T008 [P] [US1] Test JSON schema, filename format, UTC timestamps, ordered messages, existing `session_id`, completed status, redaction, same-time collision handling, and write-failure isolation in `tests/unit/test_conversation_logger.py`
- [x] T009 [P] [US1] Test that orchestration logs only after successful answer and citation creation and preserves answer/retrieval behavior when logging fails in `tests/unit/test_query_orchestrator_logging.py`

### Implementation for User Story 1

- [x] T010 [US1] Implement redaction, employee-scoped filename construction, ordered-message serialization, and atomic JSON persistence in `app/infrastructure/logging/conversation_logger.py`
- [x] T011 [US1] Integrate the logger after successful answer and citation generation, pass the existing `session_id` and authenticated-user context required by the provider, and preserve the existing API response behavior in `app/use_cases/chat/query_orchestrator.py` and `app/api/routes/chat.py`

**Checkpoint**: User Story 1 is independently testable; completed conversations produce one redacted employee-scoped JSON log and logging failures do not interrupt chat.

## Phase 4: User Story 2 - Remove expired conversation logs automatically (Priority: P1)

**Goal**: Remove expired JSON logs while preserving non-expired logs and continuing after individual deletion failures.

**Independent Test**: Run cleanup against expired, non-expired, malformed, and unrelated files and verify only eligible logs are removed while cleanup continues after a deletion error.

### Tests for User Story 2

- [x] T012 [P] [US2] Test expired-log deletion, non-expired preservation, malformed/unrelated-file handling, repeat-safe cleanup, and continuation after an individual deletion failure in `tests/unit/test_conversation_log_cleanup.py`

### Implementation for User Story 2

- [x] T013 [US2] Implement repeat-safe cleanup using the configured retention cutoff and per-file failure handling in `app/infrastructure/logging/conversation_log_cleanup.py`
- [x] T014 [US2] Invoke cleanup at application startup or through an explicit maintenance entry point without adding a user-facing endpoint in `app/main.py`
- [x] T015 [US2] Add cleanup failure observability and verify startup cleanup failures do not prevent FastAPI startup in `app/main.py` and `app/infrastructure/logging/conversation_log_cleanup.py`

**Checkpoint**: User Stories 1 and 2 work independently; logs can be captured and expired logs can be cleaned safely.

## Phase 5: User Story 3 - Configure retention without code changes (Priority: P2)

**Goal**: Allow developers to change the retention boundary through configuration while retaining a documented 30-day default.

**Independent Test**: Change the configured retention value and verify cleanup applies the new boundary without source-code changes.

### Tests for User Story 3

- [x] T016 [P] [US3] Test the 30-day default, valid configured retention, missing configuration, invalid values, safe fallback, and warning behavior in `tests/unit/test_settings.py` and `tests/unit/test_conversation_log_cleanup.py`

### Implementation for User Story 3

- [x] T017 [US3] Document `CONVERSATION_LOG_DIR`, `CONVERSATION_LOG_RETENTION_DAYS`, the 30-day default, mock employee identity, cleanup operation, and developer-only access in `README.md` and `specs/003-conversation-logging/quickstart.md`
- [x] T018 [US3] Ensure cleanup reads the validated retention setting without introducing a database implementation in `app/infrastructure/logging/conversation_log_cleanup.py`

**Checkpoint**: User Story 3 is independently testable; operations can change retention through one configuration value.

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validate the feature without changing existing chat, retrieval, memory, provider, API, or UI behavior.

- [ ] T019 [P] Run existing chat API contract and end-to-end regression tests and update only affected assertions in `tests/contract/test_chat_api_contract.py` and `tests/integration/test_chat_e2e.py`
- [ ] T020 [P] Run existing retrieval, conversation-resolution, session-memory, LLM-provider, and document-ingestion tests in `tests/unit/`
- [ ] T021 Verify logs are excluded from version control and execute the scenarios in `specs/003-conversation-logging/quickstart.md`
- [ ] T022 Review the completed implementation against `specs/003-conversation-logging/spec.md`, `specs/003-conversation-logging/data-model.md`, and `specs/003-conversation-logging/plan.md` for scope, security, failure isolation, and no retrieval/answer behavior changes

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; establishes settings and log-directory conventions.
- **Foundational (Phase 2)**: Depends on Setup and blocks all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational; MVP capture flow.
- **User Story 2 (Phase 4)**: Depends on the shared settings and logger file conventions; cleanup can proceed after the foundational phase and logger contract are defined.
- **User Story 3 (Phase 5)**: Depends on settings and cleanup; documents the operational configuration.
- **Polish (Phase 6)**: Depends on the implemented stories and validates regressions.

### User Story Dependencies

- **US1 (P1)**: Depends on Phase 2; delivers the MVP conversation-capture flow.
- **US2 (P1)**: Depends on Phase 1 and the log file format from US1; independently validates cleanup behavior.
- **US3 (P2)**: Depends on Phase 1 and US2 cleanup behavior; independently validates configuration-driven retention.

### Within Each User Story

- Write tests before implementation and confirm they fail for the missing behavior.
- Implement provider/data boundaries before logger services.
- Implement logger and cleanup services before application integration.
- Validate each story at its checkpoint before moving to the next priority.

### Parallel Opportunities

- T002, T004, and T007-T009 can be parallelized when their prerequisite interfaces are available.
- T013 and T016 can be developed in parallel after the shared settings contract is defined.
- T019-T020 can run in parallel after orchestration and startup integration are complete.

## Parallel Example: User Story 1

```text
Task: T007 provider unit tests in tests/unit/test_employee_id_provider.py
Task: T008 conversation logger tests in tests/unit/test_conversation_logger.py
Task: T009 orchestration logging tests in tests/unit/test_query_orchestrator_logging.py
```

These tests can be prepared in parallel before the logger implementation is completed.

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Setup and Foundational phases.
2. Implement the temporary employee-ID provider and conversation logger.
3. Integrate logging after successful answer/citation generation.
4. Run the User Story 1 tests and confirm chat behavior is unchanged.
5. Stop for review before adding cleanup automation.

### Incremental Delivery

1. Deliver US1 for employee-scoped JSON capture.
2. Deliver US2 for safe automatic cleanup.
3. Deliver US3 for configurable retention and operational documentation.
4. Run Phase 6 regression and quickstart validation.

### Parallel Team Strategy

1. Complete settings and provider contracts together.
2. Assign logger implementation/tests and cleanup implementation/tests to separate contributors after the shared contracts are stable.
3. Integrate orchestration and startup wiring after both services are validated.
4. Run API, integration, and quickstart validation as the final cross-cutting pass.

## Notes

- Every task uses the required checkbox, sequential ID, optional `[P]` marker, story label in story phases, and exact file path.
- No database implementation or database dependency is included.
- The temporary mock employee-ID provider is a replaceable boundary for future database-backed identity lookup.
- The existing `session_id` remains the only conversation identifier.
- No retrieval, memory, LLM provider, API schema, or Streamlit behavior is intentionally changed.
