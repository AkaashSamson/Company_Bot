"""Streamlit session helpers for the logged-in user."""

import streamlit as st

from streamlit_app.services.auth_service import AuthError, AuthService


def get_current_user():
    """Return the logged-in user dict from session state, or None."""
    return st.session_state.get("user")


def identity_headers():
    """Headers carrying the current user's identity for backend calls."""
    user = get_current_user()
    if not user:
        return {}
    return {
        "X-User-Id": user["employee_id"],
        "X-User-Role": user.get("role_code", ""),
    }


def is_logged_in() -> bool:
    return get_current_user() is not None


def render_login():
    """Render the login form and return the user dict when logged in."""
    if get_current_user() is not None:
        return get_current_user()

    st.title("KnowLayer HR Policy Assistant")
    st.subheader("Login")
    col1, col2 = st.columns(2)
    with col1:
        email = st.text_input("Email", placeholder="firstname.lastname@mclarensv.com")
    with col2:
        password = st.text_input("Password", type="password", placeholder="MSS001")
    if st.button("Login", type="primary"):
        if not email or not password:
            st.error("Enter both email and password.")
            return None
        try:
            user = AuthService().login(email.strip(), password)
        except AuthError as exc:
            st.error(str(exc))
            return None
        st.session_state.user = user
        st.rerun()
    return None


def logout():
    st.session_state.pop("user", None)
    st.session_state.pop("messages", None)
    st.rerun()