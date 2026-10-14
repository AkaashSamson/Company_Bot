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

    def ask(self, question: str, question_timestamp: str | None = None, session_id: str = "default-session", history=None, project_id=None, defer_citations: bool = False):
        payload = {
            "question": question,
            "question_timestamp": question_timestamp,
            "session_id": session_id,
            "project_id": project_id,
            "conversation_history": history or [],
            "defer_citations": defer_citations,
        }
        response = requests.post(f"{self.base_url}/api/chat", json=payload, headers=self._headers(), timeout=90)
        response.raise_for_status()
        return response.json()

    def clear_cache(self):
        response = requests.post(f"{self.base_url}/api/chat/cache/clear", headers=self._headers(), timeout=10)
        response.raise_for_status()
        return response.json()

    def get_provider_health(self):
        """Fetch LLM provider health status and circuit breaker metrics."""
        try:
            response = requests.get(f"{self.base_url}/api/chat/providers/health", headers=self._headers(), timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return {}

    def reset_providers(self):
        """Reset all provider circuit breakers."""
        try:
            response = requests.post(f"{self.base_url}/api/chat/providers/reset", headers=self._headers(), timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return {}
