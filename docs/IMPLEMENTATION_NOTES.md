# Implementation Notes

Two pieces of work are documented here:

1. **Current implementation** - browser-cookie session persistence so the Streamlit UI stays logged in across page refreshes, plus the backend refresh-token contract that supports it.
2. **Previous implementation** - hiding the permission-checkbox editor for the system `Admin` role in the Roles & Permissions page.

---

## 1. Current implementation: session persistence across page refresh

### Problem being solved

Streamlit pages (`app.py` and every page under `streamlit_app/pages/`) run as an independent Python script on every page load or refresh. `st.session_state` is kept per WebSocket connection within a tab, but a full page refresh re-runs the script from zero with an empty `st.session_state`, and the state never survives the reload.

As a result, a user who logged in on the chat page and then navigated to another page (for example `/profile`) would see "Authentication required" errors after refreshing that page, because the frontend services read the token from `st.session_state.auth` (see `streamlit_app/services/profile_api.py` `_session_token()` and `streamlit_app/services/organization_service.py`).

### Chosen approach

Persist the auth payload (access + refresh tokens, user id, display name) in a **browser cookie** named `knowlayer_auth` and restore it into `st.session_state.auth` at the start of every page run.

- Library: `streamlit-cookies-controller>=0.0.4` (added to `requirements.txt`).
  - `streamlit-cookies-manager` was tried first but is incompatible with current Streamlit versions (it used the removed `st.cache` API); the maintained alternative was adopted instead.
- The cookie is JS-accessible (not `HttpOnly`). This is acceptable for this internal, localhost-only tool, but it means the token is readable by any script running on the same origin.

### What changed

New shared helper module `streamlit_app/session_auth.py`:

- `bootstrap_cookies()` - creates the `CookieController` and waits one rerun for the browser to sync its cookies (`st.stop()` while waiting). This gate is required because the component value is only available after the browser postback.
- `restore_auth(cookies)` - ensures `st.session_state.auth` exists; if it is empty, reads the `knowlayer_auth` cookie and restores the session, then `st.rerun()` so the page continues as an authenticated run. Handles both forms the library returns (a raw JSON string, or an already-parsed dict), and removes the cookie if it is not valid JSON or has no `access_token`.
- `persist_auth(cookies)` - after a successful login, writes the cookie if it is still missing. The write is skipped once the cookie exists so the component's postback rerun does not cause a re-render loop.
- `require_auth()` - convenience guard that pages call: bootstraps the cookie, restores the session, and if the user is still anonymous shows a warning with a link to the chat page and `st.stop()`.

`streamlit_app/app.py`:

- Refactored to use the shared helpers (`bootstrap_cookies`, `restore_auth`, `persist_auth`).
- The login form is unchanged: on submit it calls the auth service, stores the result in `st.session_state.auth` and `st.rerun()`. The cookie write happens on the following, normally-completing run via `persist_auth`.
  - Important detail: the cookie cannot be written inside the login-submit branch, because `st.rerun()` discards the current run's deltas before they reach the browser.
- Logout removes the `knowlayer_auth` cookie.

`streamlit_app/pages/*.py` (`profile.py`, `users.py`, `departments.py`, `projects.py`, `documents.py`, `explorer.py`, `roles.py`, `organization.py`):

- Each page now calls `require_auth()` immediately after its `st.set_page_config(...)`. This was the key fix: previously the cookie-restore logic lived only in `app.py`, so refreshing any other page dropped the session.

`app/` backend (refresh-token contract):

- `app/core/settings.py` - added `AUTH_REFRESH_TOKEN_EXPIRE_MINUTES` (10080 minutes = 7 days). Access tokens expire after 480 minutes (8 hours).
- `app/domain/services/authentication_service.py` - token creation now issues signed JWTs carrying `sub` (user id), `iat`, `exp`, `jti` (unique token id) and `token_type` (`access` or `refresh`). `refresh_access_token()` validates a refresh token and returns a rotated (user id, access token, refresh token) triple. `resolve_token()` (used by the auth dependency) rejects tokens whose `token_type` is not `access`.
- `app/domain/ports/authorization_service.py` - `AuthenticatedPrincipal` gained an optional `refresh_token` field (backwards compatible).
- `app/api/schemas/authentication.py` - added `RefreshRequest` / `RefreshResponse`, and a `refresh_token` field on `LoginResponse`.
- `app/api/routes/authentication.py` - added `POST /api/auth/refresh`.
- `streamlit_app/services/authentication_service.py` - added a `refresh()` helper for the future frontend swap.
- Tests added in `tests/unit/test_authentication_service.py` and `tests/contract/test_authentication_api.py` (14 auth tests, all green).

### Why the backend refresh-token work was included

The API is being kept stable so the Streamlit frontend can later be replaced without redesigning authentication. JWT `exp` now matches what the API declares in its OpenAPI contract, refresh tokens are visibly distinct from access tokens, and a refresh endpoint exists for long-lived sessions without forcing re-login.

### Known limitations

- Cookie expiry defaults to `now + 1 day` (`sameSite=strict`, `path=/`) with the library's default settings; a session is effectively remembered for at most 24 hours regardless of the expiry encoded in the JWT itself.
- A JSON-parse failure of the cookie silently drops the session (cookie removed); no error is surfaced.
- Because the cookie is JS-readable, this is not appropriate for a production, multi-tenant deployment.

---

## 2. Previous implementation: Admin role permission-checkbox display

### The change

In `streamlit_app/pages/roles.py`, the "Assign permissions to role" section previously rendered the full permission-checkbox grid (via `permission_checkboxes(...)`) and a "Save permissions" button for **every** role, including the system `Admin` role.

The current code special-cases `Admin` (compare with `git show HEAD:streamlit_app/pages/roles.py` for the previous version):

```python
if assign_role_label == "Admin":
    st.info(
        "The system Admin role cannot be modified. Admin access is granted "
        "by role identity, so permission assignment is disabled for this role."
    )
else:
    # ... existing checkbox list + Save permissions ...
```

### Why

- `Admin` is a bootstrap system role. A user is treated as an admin by role identity, not by the set of permission rows attached to the role.
- Allowing the checkbox grid for `Admin` created a real risk: an operator could uncheck permissions on the admin role and accidentally lock themselves (or everyone else) out of administrative capabilities, with no recovery path through the UI.
- Mixed signals: even if the backend ignored updates to the system role, the UI presented it as freely editable, which was misleading.

The special-case replaces the editable grid with an explanatory message, so the section communicates that `Admin` permissions are fixed and skips the (now pointless) fetch and save calls for that role.

### Out of scope

- The Create / Update / Delete role expanders still apply to all roles, including `Admin`. This implementation only changed the permission-assignment checkbox display. If `Admin` should also be excluded from create/update/delete, that is a follow-up decision.
- The backend was not changed for this item; it was a frontend-only guard.