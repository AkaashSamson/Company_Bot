# Quickstart: SQL Organization Access

## Prerequisites

- Python 3.11+
- Project dependencies installed from `requirements.txt`
SQLite database file at `./instance/sqlite.db` for organization/access data
- Existing chat environment variables configured as described in `README.md`
- Authenticated principal integration configured for the API/UI test path

## Setup

1. Configure the SQL connection URL in the application environment.
2. Run the feature migration command documented by the implementation once migrations are added.
3. Seed one Admin, two Departments, one Manager per department, two regular users, and two Projects.
4. Assign User A to Project A and User B to Project B; leave one user with no memberships.
5. Ensure indexed foreign keys exist for `User.department_id`, `Project.department_id`, and `UserProject(uid, project_id)`.

## Validation scenarios

### Flexible roles

Create a user with role `Solution Architect`, then read it back. The operation must succeed without adding a role row or schema migration. See [data-model.md](./data-model.md).

### Department-scoped management

Authenticate Manager A. Updating User A or assigning User A to Project A succeeds. Updating User B or assigning a user to Project B returns `403` and creates a denied audit event.

### Many-to-many membership

Assign one user to both projects. Read the user's projects and each project's users; both relationships must be present. Repeating the assignment must not create a duplicate.

### Retrieval isolation

Authenticate User A and ask a Project A question. The retrieval adapter must receive only Project A as an allowed filter. Requesting Project B must return access denied before the vector store is called. A user with no membership receives no restricted evidence.

### Admin troubleshooting

Authenticate Admin and read or modify records across both departments. Admin can access every active project without explicit UserProject rows, and the operation is audited.

### Transaction and audit behavior

Force a database failure during a membership update. No partial membership may remain. Verify successful, denied, and failed management operations contain actor, action, target, timestamp, and outcome without secrets.

## Test commands

Run the focused unit and contract suites:

```powershell
pytest tests/unit/test_user_authorization.py tests/unit/test_project_membership.py tests/contract/test_user_management_api.py
```

Run the full suite after the focused tests pass:

```powershell
pytest
```

The API shapes and expected status codes are defined in [contracts/user-management-api.md](./contracts/user-management-api.md).
