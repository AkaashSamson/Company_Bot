# Quickstart: SQL Organization Access

## Prerequisites

- Python 3.11+
- Project dependencies installed from `requirements.txt`
- SQLite database file at `./instance/sqlite.db` for organization/access data
- Existing chat environment variables configured as described in `README.md`
- Authenticated principal integration configured for the API/UI test path

## Setup

1. Configure the database URL through the persistence adapter factory; use SQLite first.
2. Run the feature migration command documented by the implementation once migrations are added.
3. Seed one Admin, two Departments, one Manager per department, two regular users, and two Projects.
4. Assign User A to Project A and User B to Project B; leave one user with no memberships.
5. Ensure the configured persistence adapter creates indexes for department ownership and user-project membership.

## Validation scenarios

### Flexible roles

Create a user with role `Solution Architect`, then read it back. The operation must succeed without adding a predefined role or changing the role model. See [data-model.md](./data-model.md).

### Department-scoped management

Authenticate Manager A. Updating User A or assigning User A to Project A succeeds. Updating User B or assigning a user to Project B returns `403`.

### Project documents

Create a document without assigning a project, then assign it to Project A. Confirm Project A can contain multiple documents and that the unassigned document is excluded from project-scoped answers.

### Many-to-many membership

Assign one user to both projects. Read the user's projects and each project's users; both relationships must be present. Repeating the assignment must not create a duplicate.

### Retrieval isolation

Authenticate User A with access to Projects A and B and ask a question without selecting a project. The retrieval adapter must receive only Projects A and B as allowed filters.

Select Project A and repeat the question. The retrieval adapter must receive only Project A. Selecting Project C without membership must return access denied before the vector store is called. A user with no membership receives no restricted evidence.

### Admin troubleshooting

Authenticate Admin and read or modify records across both departments. Admin can access every active project without being individually assigned to each project.

### Transaction behavior

Force a database failure during a membership update. No partial membership may remain, and the API returns an operational error.

### Streamlit management pages

- Open the Users page and create a user with a new role value; confirm it appears after refresh.
- Open the Projects page and assign a user to a project; confirm the membership appears from both views.
- Open the Documents page and list, upload, and remove a supported document; confirm the page uses FastAPI responses and never accesses storage directly.
- Confirm all three pages use the same FastAPI base URL as chat.
