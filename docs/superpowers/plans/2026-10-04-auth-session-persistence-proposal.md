# Streamlit Native Authentication & Session Persistence Proposal

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide rock-solid, multi-day authentication session persistence across browser refreshes, tab closes, and device restarts using Streamlit's native `st.context.cookies` and direct first-party cookie writing, eliminating all external React iframes and component timeouts.

**Architecture:** Hybrid native cookie bridge. On startup, Streamlit reads incoming first-party cookies natively via `st.context.cookies["knowlayer_auth"]` without rendering any components. On successful login, a non-iframed client script writes `document.cookie` with 7-day expiration (`max-age=604800; SameSite=Lax`). On logout, the cookie is expired (`max-age=0`) and session state cleared. In-memory `st.session_state` serves as the live runtime cache between page re-runs.

**Tech Stack:** Streamlit 1.45 (`st.context.cookies`, `st.html`), Python 3.12, FastAPI backend (`/api/auth/login`, `/api/auth/refresh`).

**Spec:** `docs/superpowers/plans/2026-10-04-auth-session-persistence-proposal.md`

## Global Constraints

- Zero third-party React iframe packages (`streamlit_cookies_controller` remains permanently banned).
- Must work seamlessly across localhost, WSL2, local Wi-Fi, and Tailscale IP (`100.64.4.128`).
- Must survive hard browser reloads (F5) and browser restarts for up to 7 days.
- Must cleanly wipe tokens and reset view when user explicitly clicks "Log out".
- Must maintain 100% backward compatibility with multi-page navigation across `pages/*.py`.

---

## Technical Context & Root Cause Discoveries

### 1. Why `streamlit_cookies_controller` Failed
* **Mechanism:** Ran a miniature React application inside an isolated `<iframe src="/component/streamlit_cookies_controller...">`.
* **Failure Mode:** Communicated with Streamlit parent window via `window.parent.postMessage`. Over WSL2 virtual adapters, reverse proxies, and mobile browsers, iframe security policies and network latency caused Streamlit's 10-second component watchdog timer to expire.
* **The Crash:** When timed out, the component state in `st.session_state` became `None`. The library's `get(name)` method ran `if name not in self.__cookies:`. Because `self.__cookies` was `None`, Python crashed with `TypeError: argument of type 'NoneType' is not iterable`.

### 2. Client vs. Server State Clarification
* **`st.session_state`**: Lives in **Linux Server RAM** tied to a single active WebSocket. It is destroyed when the server restarts or when a tab stays disconnected for >2 minutes. It is never shared across browser tabs.
* **Browser Cookies**: Stored on the **Client Device Disk** (phone or laptop). Shared across all tabs of that domain, and persists across device restarts until `max-age` expires.

### 3. Streamlit 1.45 Native Cookie Architecture
* Streamlit 1.45 provides `st.context.cookies`, an instance of `StreamlitCookies(Mapping[str, str])`.
* It wraps Python's immutable `MappingProxyType` containing cookies parsed from the initial HTTP request headers.
* It is **read-only** by design because Streamlit communicates over WebSockets post-load and cannot send traditional HTTP `Set-Cookie` response headers.
* Streamlit also provides `st.html(..., unsafe_allow_javascript=True)`, which injects directly into the top-level page DOM **without any iframe**, allowing direct first-party `document.cookie` execution without cross-origin or postMessage failure.

---

## Review Focus

1. **First-time anonymous visitor:** `st.context.cookies` is empty. App must render login form immediately with zero delays or warnings.
2. **Active logged-in session on F5:** User hits F5. `st.context.cookies["knowlayer_auth"]` is read during initial HTTP handshake. User is logged in on millisecond 0 without showing the login form.
3. **Expired or corrupted token:** Stored cookie contains invalid JSON or expired JWT. Backend returns 401. App must automatically purge bad cookie and show login form.
4. **Explicit Logout:** User clicks "Log out". App must immediately set `max-age=0` on the browser cookie, clear `st.session_state`, and reload to login screen. Subsequent F5 must stay on login screen.
5. **Mobile browser / Private window with cookies disabled:** If client browser blocks cookies, app must gracefully fall back to `st.session_state` without throwing unhandled exceptions.

---

## Task Decomposition

### Task 1: Clean Session Auth Adapter with Native Cookie Reader

**Files:**
- Modify: `streamlit_app/session_auth.py`
- Test: `tests/unit/test_session_auth_native.py`

**Interfaces:**
- Produces:
  - `get_native_auth_cookie() -> Optional[dict]`
  - `render_set_auth_cookie_script(token_data: dict) -> None`
  - `render_clear_auth_cookie_script() -> None`
  - `restore_auth() -> Optional[dict]`
  - `require_auth() -> Optional[dict]`

- [ ] **Step 1: Write unit tests for session auth cookie parsing and fallback**

```python
# tests/unit/test_session_auth_native.py
import json
import pytest
from unittest.mock import MagicMock, patch

def test_get_native_auth_cookie_valid_json():
    from streamlit_app.session_auth import parse_auth_cookie
    valid_payload = {"access_token": "abc.123", "uid": "admin"}
    cookie_str = json.dumps(valid_payload)
    parsed = parse_auth_cookie(cookie_str)
    assert parsed == valid_payload

def test_get_native_auth_cookie_invalid_json():
    from streamlit_app.session_auth import parse_auth_cookie
    assert parse_auth_cookie("not-json") is None
    assert parse_auth_cookie(None) is None
```

- [ ] **Step 2: Run test to verify it passes/fails**
Run: `PYTHONPATH=. .venv/bin/pytest tests/unit/test_session_auth_native.py -v`

- [ ] **Step 3: Implement native cookie helpers in `streamlit_app/session_auth.py`**
Implement:
- `parse_auth_cookie(raw_cookie)`: Safe JSON deserializer.
- `restore_auth()`: Checks `st.session_state.auth`. If None, checks `st.context.cookies.get(AUTH_COOKIE)`.
- `render_set_auth_cookie_script(auth)`: Injects non-iframed `st.html(..., unsafe_allow_javascript=True)` setting `document.cookie` with 7-day max-age.
- `render_clear_auth_cookie_script()`: Injects script expiring the cookie (`max-age=0`).

- [ ] **Step 4: Run unit tests to verify pass**
Run: `PYTHONPATH=. .venv/bin/pytest tests/unit/test_session_auth_native.py -v`

---

### Task 2: Integrate Native Cookie Bridge into `streamlit_app/app.py`

**Files:**
- Modify: `streamlit_app/app.py`

- [ ] **Step 1: Update Login Flow**
On successful login:
1. Set `st.session_state.auth = auth`.
2. Call `render_set_auth_cookie_script(auth)`.
3. Rerun / reload so top-level app detects authenticated state.

- [ ] **Step 2: Update Logout Flow**
In `_logout()`:
1. Clear `st.session_state.auth = None`.
2. Clear `st.session_state.messages = []`.
3. Call `render_clear_auth_cookie_script()`.
4. Trigger `st.rerun()`.

- [ ] **Step 3: Verify End-to-End Persistence**
1. Open `http://localhost:8501`.
2. Log in with `admin` / `change-me-before-first-login`.
3. Confirm chat interface appears.
4. Hard reload tab (Ctrl+F5).
5. Confirm user remains logged in immediately without seeing login form.
6. Click "Log out".
7. Confirm login screen appears.
8. Hard reload tab (Ctrl+F5).
9. Confirm user remains on login screen.

---

### Task 3: Commit and Push to Branch

- [ ] **Step 1: Commit proposal document and clean auth implementation**
```bash
git add docs/superpowers/plans/2026-10-04-auth-session-persistence-proposal.md streamlit_app/session_auth.py streamlit_app/app.py tests/unit/test_session_auth_native.py
git commit -m "docs: add auth session persistence proposal and native cookie architecture"
```
