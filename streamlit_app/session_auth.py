import json
import logging
from typing import Any, Optional

import streamlit as st

logger = logging.getLogger(__name__)

AUTH_COOKIE = "knowlayer_auth"
_COOKIE_KEY = "knowlayer_cookies"


class SafeCookieController:
    """In-memory session auth controller using st.session_state.
    
    Avoids mounting the third-party streamlit_cookies_controller iframe,
    which fails over network/proxies and causes infinite loading spinners.
    """
    def __init__(self, key: str = _COOKIE_KEY) -> None:
        self.key = key

    def get(self, name: str) -> Any:
        return st.session_state.get(f"_cookie_{name}")

    def set(self, name: str, val: Any) -> None:
        st.session_state[f"_cookie_{name}"] = val

    def remove(self, name: str) -> None:
        st.session_state.pop(f"_cookie_{name}", None)


def bootstrap_cookies() -> SafeCookieController:
    return SafeCookieController(key=_COOKIE_KEY)


def restore_auth(cookies: SafeCookieController) -> dict | None:
    if st.session_state.get("logged_out"):
        return None
    if "auth" not in st.session_state:
        st.session_state.auth = None
    if st.session_state.auth is None:
        cookie_auth = None
        try:
            cookie_auth = cookies.get(AUTH_COOKIE)
        except Exception as e:
            logger.warning("Error fetching auth cookie: %s", e)

        if isinstance(cookie_auth, str):
            try:
                cookie_auth = json.loads(cookie_auth)
            except (json.JSONDecodeError, TypeError):
                try:
                    cookies.remove(AUTH_COOKIE)
                except Exception:
                    pass
                cookie_auth = None
        if isinstance(cookie_auth, dict) and cookie_auth.get("access_token"):
            st.session_state.auth = cookie_auth
            st.rerun()
    return st.session_state.auth


def persist_auth(cookies: SafeCookieController) -> None:
    auth = st.session_state.get("auth")
    if auth is not None:
        try:
            if cookies.get(AUTH_COOKIE) is None:
                cookies.set(AUTH_COOKIE, auth)
        except Exception as e:
            logger.debug("Failed persisting auth cookie: %s", e)


def require_auth() -> dict | None:
    cookies = bootstrap_cookies()
    auth = restore_auth(cookies)
    if auth is None:
        st.warning("You must log in to view this page.")
        st.page_link("app.py", label="Go to log in")
        st.stop()
    persist_auth(cookies)
    return auth