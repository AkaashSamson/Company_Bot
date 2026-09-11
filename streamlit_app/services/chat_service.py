import os

import requests


class ChatService:
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

    def ask(self, question: str, session_id: str = "default-session", history=None, project_id=None):
        payload = {
            "question": question,
            "session_id": session_id,
            "project_id": project_id,
            "conversation_history": history or [],
        }
        response = requests.post(f"{self.base_url}/api/chat", json=payload, headers=self._headers(), timeout=60)
        response.raise_for_status()
        return response.json()