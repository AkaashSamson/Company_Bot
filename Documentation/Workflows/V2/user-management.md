# User Management Workflow

The Streamlit Users page uses `OrganizationService` for user and department HTTP calls. It never opens the database.

1. The page sends requests to `/api/users` or `/api/departments` using `STREAMLIT_API_BASE_URL`.
2. FastAPI dependencies resolve the trusted authenticated principal and construct `UserManagementService` with the configured Unit of Work.
3. The service loads the actor and target records through repository ports, checks active status and Admin/Manager scope, then validates department and uniqueness rules.
4. The SQLAlchemy Unit of Work maps domain entities to relational records and commits one transaction.
5. FastAPI returns the response or a consistent `401`, `403`, `404`, or `409` error for the page to display.

The persistence factory selects SQLite by default and retains the same repository and Unit of Work contract for PostgreSQL configuration.
