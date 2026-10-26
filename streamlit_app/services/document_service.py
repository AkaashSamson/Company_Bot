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

    def _get(self, path: str, params: dict | None = None, timeout: float = 30):
        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        response = requests.get(url, params=params, headers=self._headers(), timeout=timeout)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, json_data: dict | None = None, timeout: float | None = None):
        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        post_timeout = timeout if timeout is not None else 300
        response = requests.post(url, json=json_data, headers=self._headers(), timeout=post_timeout)
        response.raise_for_status()
        return response.json()

    def _delete(self, path: str, params: dict | None = None, timeout: float = 30):
        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        response = requests.delete(url, params=params, headers=self._headers(), timeout=timeout)
        response.raise_for_status()
        return True

    def list_documents(self):
        return self._get("/api/documents")

    def get_document(self, document_id: str):
        return self._get(f"/api/documents/{document_id}", timeout=15)

    def create_document(self, payload, timeout: float | None = None):
        upload_timeout = timeout
        if upload_timeout is None:
            raw_timeout = os.getenv("DOCUMENT_UPLOAD_TIMEOUT")
            if raw_timeout is not None and raw_timeout.strip():
                try:
                    upload_timeout = float(raw_timeout.strip())
                except ValueError:
                    upload_timeout = None
        return self._post("/api/documents", json_data=payload, timeout=upload_timeout)

    def get_status(self, document_id: str):
        return self._get(f"/api/documents/{document_id}/status")

    def get_chunks(self, document_id: str):
        return self._get(f"/api/documents/{document_id}/chunks")

    def search_chunks(self, payload: dict):
        return self._post("/api/documents/chunks/search", json_data=payload)

    def delete_document(self, document_id: str, permanent: bool = False):
        return self._delete(f"/api/documents/{document_id}", params={"permanent": permanent})
