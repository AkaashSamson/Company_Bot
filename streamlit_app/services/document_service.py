import os

import requests


class DocumentService:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or os.getenv("STREAMLIT_API_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")

    def list_documents(self):
        response = requests.get(f"{self.base_url}/api/documents", timeout=15)
        response.raise_for_status()
        return response.json()

    def create_document(self, payload):
        response = requests.post(f"{self.base_url}/api/documents", json=payload, timeout=15)
        response.raise_for_status()
        return response.json()

    def delete_document(self, document_id):
        response = requests.delete(f"{self.base_url}/api/documents/{document_id}", timeout=15)
        response.raise_for_status()
