import json

import streamlit as st

from streamlit_cookies_controller import CookieController

AUTH_COOKIE = "knowlayer_auth"
_COOKIE_KEY = "knowlayer_cookies"


def bootstrap_cookies() -> CookieController:
    cookies = CookieController(key=_COOKIE_KEY)
    if "cookies_synced" not in st.session_state:
        st.session_state.cookies_synced = True
        st.stop()
    return cookies


def restore_auth(cookies: CookieController) -> dict | None:
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
    if auth is None:
        st.warning("You must log in to view this page.")
        st.page_link("app.py", label="Go to log in")
        st.stop()
    persist_auth(cookies)
    return auth