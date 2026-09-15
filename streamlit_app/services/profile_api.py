import os

import requests


class ProfileAPI:
    """Thin HTTP client over the knowler profile endpoints.

    Only the current user's own profile is ever requested; every access
    decision (visible projects, readable documents, effective permissions,
    entitlement to leave a project) is enforced by the FastAPI backend.
    """

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.getenv("STREAMLIT_API_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.token = token

    def _headers(self):
        headers = {}
        token = self.token or self._session_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _session_token():
        try:
            import streamlit as st

            auth = st.session_state.get("auth")
            if isinstance(auth, dict):
                return auth.get("access_token") or auth.get("token")
        except Exception:
            return None
        return None

    def profile(self):
        response = requests.get(
            f"{self.base_url}/api/users/me/profile",
            headers=self._headers(),
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def leave_project(self, project_id):
        response = requests.post(
            f"{self.base_url}/api/projects/{project_id}/members/me/leave",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()