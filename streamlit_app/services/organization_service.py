import os

import requests


class OrganizationService:
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

    def list_users(self):
        response = requests.get(f"{self.base_url}/api/users", headers=self._headers(), timeout=15)
        response.raise_for_status()
        return response.json()

    def create_user(self, payload):
        response = requests.post(f"{self.base_url}/api/users", json=payload, headers=self._headers(), timeout=15)
        response.raise_for_status()
        return response.json()

    def update_user(self, uid, payload):
        response = requests.patch(f"{self.base_url}/api/users/{uid}", json=payload, headers=self._headers(), timeout=15)
        response.raise_for_status()
        return response.json()

    def deactivate_user(self, uid):
        response = requests.delete(f"{self.base_url}/api/users/{uid}", headers=self._headers(), timeout=15)
        response.raise_for_status()

    def list_departments(self):
        response = requests.get(f"{self.base_url}/api/departments", headers=self._headers(), timeout=15)
        response.raise_for_status()
        return response.json()

    def create_department(self, payload):
        response = requests.post(f"{self.base_url}/api/departments", json=payload, headers=self._headers(), timeout=15)
        response.raise_for_status()
        return response.json()

    def list_projects(self):
        response = requests.get(f"{self.base_url}/api/projects", headers=self._headers(), timeout=15)
        response.raise_for_status()
        return response.json()

    def create_project(self, payload):
        response = requests.post(f"{self.base_url}/api/projects", json=payload, headers=self._headers(), timeout=15)
        response.raise_for_status()
        return response.json()

    def assign_member(self, project_id, uid):
        response = requests.post(
            f"{self.base_url}/api/projects/{project_id}/members/{uid}",
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()

    def revoke_member(self, project_id, uid):
        response = requests.delete(
            f"{self.base_url}/api/projects/{project_id}/members/{uid}",
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()

    def leave_project(self, project_id):
        response = requests.post(
            f"{self.base_url}/api/projects/{project_id}/members/me/leave",
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()
        return True
    def list_user_project_memberships(self, uid):
        response = requests.get(
            f"{self.base_url}/api/users/{uid}/project-memberships",
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
