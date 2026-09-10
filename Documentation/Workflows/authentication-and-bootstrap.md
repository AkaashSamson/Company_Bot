# Authentication and Bootstrap Workflow

The application starts with a pre-seeded Admin configured through `ADMIN_USERNAME` and `ADMIN_INITIAL_PASSWORD`. The initial password is stored only as a secure representation.

1. Database setup provisions the Admin idempotently and creates the Administration department when needed.
2. Admin logs in through `POST /api/auth/login`, receives a bearer token, and changes the configured default password through `POST /api/auth/change-password`.
3. Admin creates Managers with usernames and initial passwords. Managers log in and onboard employees inside their department scope.
4. Protected organization, document, and chat requests resolve the principal from the bearer token before authorization or retrieval.
5. Users can change their own passwords. Admin can set a user's password through the authenticated password-change flow.
6. Authentication events record event type, principal ID when available, and success status without recording passwords or tokens.

Set `AUTH_SECRET_KEY` to a private value before deployment. Never commit `ADMIN_INITIAL_PASSWORD` or production secrets.