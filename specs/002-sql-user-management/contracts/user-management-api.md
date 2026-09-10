# User Management API Contract

Base path: `/api`

All endpoints require an authenticated principal supplied by the existing authentication integration. The caller's UID is taken from trusted auth context, not from a mutable request body field.

## Users

### `POST /users`

Admin only. Creates a user.

Request:

```json
{"uid":"u-123","name":"Asha Rao","email":"asha@example.com","role":"Solution Architect","department_id":"dept-eng"}
```

Responses:
- `201`: created User representation
- `400`: invalid email, empty role/name, or malformed identifier
- `404`: department does not exist
- `409`: UID or email already exists
- `403`: caller is not Admin

### `GET /users/{uid}`

Admin, or Manager when the target belongs to the Manager's department. Other users may read only their own record.

Responses: `200`, `403`, `404`.

### `PATCH /users/{uid}`

Admin can update all mutable fields. Manager can update permitted fields only within the Manager's department. Role is a string, not an enum.

Responses: `200`, `400`, `403`, `404`, `409`.

### `DELETE /users/{uid}`

Admin may deactivate or delete according to retention policy. Manager may deactivate only an in-scope user if policy permits. Membership changes are transactional.

Responses: `204`, `403`, `404`.

## Departments and projects

### `POST /departments`

Admin only. Creates a department. Duplicate names return `409`.

### `POST /projects`

Admin only. Creates a project linked to an active department.

### `GET /projects`

Returns only projects authorized for the caller. Admin receives all active projects; other users receive active memberships.

### `POST /projects/{project_id}/members/{uid}`

Admin, or Manager when both target user and project are in the Manager's department. Idempotent success returns `204`.

### `DELETE /projects/{project_id}/members/{uid}`

Same scope rules as assignment. Revokes membership without deleting project data. Returns `204` when already revoked.

## Chat authorization

### `POST /chat`

Existing chat request gains trusted auth context and an optional project scope. The route resolves authorized project IDs before constructing the `QueryOrchestrator` retrieval call.

An unauthorized explicit project request returns:

```json
{"detail":"Access denied"}
```

with status `403`. No restricted vector query or LLM generation is performed. A request with no authorized projects returns an empty evidence result according to the existing chat response contract.

## Audit behavior

Every successful or denied management operation creates one AuditEvent. Audit persistence failures must be observable and must not expose secrets; transaction semantics for the business operation are defined in the implementation plan.
