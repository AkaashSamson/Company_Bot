import json

import streamlit as st

try:
    from streamlit_cookies_controller import CookieController
except ImportError:
    class CookieController:
        """In-memory session fallback when streamlit_cookies_controller is not installed."""
        def __init__(self, key: str | None = None) -> None:
            self.key = key

        def get(self, name: str) -> dict | str | None:
            return st.session_state.get(f"_cookie_{name}")

        def set(self, name: str, val: dict | str) -> None:
            st.session_state[f"_cookie_{name}"] = val

        def remove(self, name: str) -> None:
            st.session_state.pop(f"_cookie_{name}", None)

AUTH_COOKIE = "knowlayer_auth"
_COOKIE_KEY = "knowlayer_cookies"


def bootstrap_cookies() -> CookieController:
    cookies = CookieController(key=_COOKIE_KEY)
    if "cookies_synced" not in st.session_state:
        st.session_state.cookies_synced = True
        st.stop()
    return cookies


import os
import requests


def validate_token(token: str) -> bool:
    """Check if token is valid and belongs to an active user on the FastAPI backend."""
    if not token:
        return False
    base_url = os.getenv("STREAMLIT_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    try:
        r = requests.get(
            f"{base_url}/api/users/me/profile",
            headers={"Authorization": f"Bearer {token}"},
            timeout=3,
        )
        if r.status_code in (401, 403):
            return False
    except Exception:
        # If the backend is temporarily unreachable, do not clear the user session
        pass
    return True


def restore_auth(cookies: CookieController) -> dict | None:
    if st.session_state.get("logged_out"):
        return None
    if "auth" not in st.session_state:
        st.session_state.auth = None
    if st.session_state.auth is None:
        cookie_auth = cookies.get(AUTH_COOKIE)
        if isinstance(cookie_auth, str):
            try:
                cookie_auth = json.loads(cookie_auth)
            except (json.JSONDecodeError, TypeError):
                try:
                    cookies.remove(AUTH_COOKIE)
                except KeyError:
                    pass
                cookie_auth = None
        if isinstance(cookie_auth, dict) and cookie_auth.get("access_token"):
            token = cookie_auth.get("access_token")
            if not validate_token(token):
                try:
                    cookies.remove(AUTH_COOKIE)
                except Exception:
                    pass
                st.session_state.auth = None
                return None
            st.session_state.auth = cookie_auth
            st.rerun()
    return st.session_state.auth


def persist_auth(cookies: CookieController) -> None:
    auth = st.session_state.get("auth")
    if auth is not None and cookies.get(AUTH_COOKIE) is None:
        cookies.set(AUTH_COOKIE, auth)


def require_auth() -> dict | None:
    cookies = bootstrap_cookies()
    auth = restore_auth(cookies)
    if auth is not None:
        token = auth.get("access_token")
        if token and not validate_token(token):
            try:
                cookies.remove(AUTH_COOKIE)
            except Exception:
                pass
            st.session_state.auth = None
            auth = None
    if auth is None:
        st.warning("You must log in to view this page.")
        st.page_link("app.py", label="Go to log in")
        st.stop()
    persist_auth(cookies)
    from streamlit_app.sidebar import render_sidebar
    render_sidebar()
    return auth