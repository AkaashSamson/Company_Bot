# Quickstart: Conversation Logging

## Prerequisites

- Python 3.11 environment configured for Company_Bot.
- Existing chat/RAG dependencies installed.
- No database service is required for the initial implementation.

## Configuration

Set the following environment values in `.env` when defaults are not suitable:

```env
CONVERSATION_LOG_DIR=conversation_logs
CONVERSATION_LOG_RETENTION_DAYS=30
```

The initial employee identity source is the temporary mock employee-ID provider. It returns test IDs such as `MSS001`, `MSS002`, and `MSS003`; database-backed identity lookup is deferred.

## Validation Scenarios

### Record one completed conversation

1. Start the existing FastAPI and Streamlit services.
2. Submit one chat conversation using an authenticated-user test context.
3. Locate the configured conversation-log directory.
4. Verify exactly one JSON file exists with a name matching `<employee_id>_<timestamp>.json`.
5. Verify the JSON contains `employee_id`, the existing `session_id`, ordered `messages`, message timestamps, and `recording_status: "completed"`.
6. Verify the answer and retrieval behavior are unchanged.

### Verify redaction

1. Submit messages containing test credentials or token-shaped values.
2. Open the generated JSON log.
3. Verify secrets and tokens are redacted or omitted.
4. Verify the in-memory chatbot request and answer behavior are unaffected.

### Verify retention cleanup

1. Configure `CONVERSATION_LOG_RETENTION_DAYS=30`.
2. Create one log older than 30 days and one log newer than 30 days.
3. Run the cleanup operation.
4. Verify only the expired log is removed.
5. Simulate one deletion failure and verify cleanup continues for remaining files.

### Verify failure isolation

1. Make the log directory unavailable or force a write failure.
2. Complete a chat request.
3. Verify the user still receives the normal chatbot answer and retrieval result.
4. Verify the logging failure is observable to developers or operations.

## Automated Test Targets

Add unit coverage for:

- mock employee-ID provider and provider replacement boundary;
- filename construction and timestamp uniqueness;
- JSON schema and ordered message timestamps;
- secret/token redaction;
- 30-day default and configurable retention;
- expired versus non-expired cleanup;
- cleanup continuation after individual deletion failures;
- logging failures not interrupting chat;
- no separate conversation identifier beyond `session_id`.

Logs are developer/operations data only. There is no end-user log search or analytics flow.
