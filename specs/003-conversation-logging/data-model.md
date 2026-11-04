# Data Model: Developer Conversation Logging

## ConversationLog

One JSON document representing one completed conversation.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `employee_id` | string | yes | Returned by the employee-ID provider; represents the employee associated with the authenticated user. |
| `session_id` | string | yes | Existing application session identifier; no separate conversation identifier is introduced. |
| `messages` | array | yes | Ordered message records for the completed conversation. |
| `recording_status` | string | yes | `completed` for a successfully recorded conversation. |

A log also contains the message-level timestamps required to reconstruct ordering and timing.

## ConversationMessage

| Field | Type | Required | Rules |
|---|---|---:|---|
| `role` | string | yes | The existing chat role, such as `user` or `assistant`. |
| `content` | string | yes | Redacted message content; secrets and tokens must not remain in cleartext. |
| `timestamp` | string | yes | UTC timestamp for the message. |

## File Identity

- Directory: configured conversation-log directory, defaulting to `conversation_logs/`.
- Filename: `<employee_id>_<timestamp>.json`.
- Timestamp: UTC in `YYYYMMDD_HHMMSS` format.
- If the same employee completes another conversation within the same timestamp interval, the implementation must preserve unique files without introducing a separate conversation ID.

## EmployeeIdProvider

A replaceable lookup boundary that returns the employee ID associated with the authenticated user.

### Initial provider

The initial implementation uses a temporary mock provider returning test IDs such as `MSS001`, `MSS002`, and `MSS003`. These IDs are provider data and must not be hard-coded in the logging service.

### Future provider

A database-backed employee identity provider will replace the mock provider without changing the conversation logger contract.

## Retention State

Retention is derived from filesystem metadata and configuration rather than stored as a separate entity:

- `CONVERSATION_LOG_RETENTION_DAYS`, default `30`.
- Files older than the retention cutoff are expired.
- Non-expired files remain untouched.
- Cleanup continues after individual deletion failures.
