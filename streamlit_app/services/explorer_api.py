import os

import requests


class ExplorerAPI:
    """Thin HTTP client for the Organization Explorer.

    Every visibility decision (which departments, projects, members and
    documents the signed-in user may see) is made by the FastAPI backend.
    This client only renders what the backend returns.
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

    def organization(self):
        response = requests.get(
            f"{self.base_url}/api/explorer/organization",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()