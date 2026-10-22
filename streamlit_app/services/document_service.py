import os

import requests


class DocumentService:
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

    def list_documents(self):
        response = requests.get(f"{self.base_url}/api/documents", headers=self._headers(), timeout=15)
        response.raise_for_status()
        return response.json()

    def create_document(self, payload):
        response = requests.post(f"{self.base_url}/api/documents", json=payload, headers=self._headers(), timeout=300)
        response.raise_for_status()
        return response.json()

    def archive_document(self, document_id):
        response = requests.post(f"{self.base_url}/api/documents/{document_id}/archive", headers=self._headers(), timeout=15)
        response.raise_for_status()
        return response.json()

    def unarchive_document(self, document_id):
        response = requests.post(f"{self.base_url}/api/documents/{document_id}/unarchive", headers=self._headers(), timeout=30)
        response.raise_for_status()
        return response.json()

    def delete_document(self, document_id, permanent: bool = True, *args, **kwargs):
        params = {"permanent": "true"} if permanent else {"permanent": "false"}
        response = requests.delete(
            f"{self.base_url}/api/documents/{document_id}",
            params=params,
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()