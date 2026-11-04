import os

import requests


class AdminAPI:
    """Thin HTTP client over the KnowLayer admin APIs.

    No business authorization logic lives here — every decision is enforced
    by the FastAPI backend. When an operation is not permitted for the signed-in
    user the backend answers with 403 and this client surfaces the detail.
    """

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.getenv("STREAMLIT_API_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.token = token

    # ------------------------------------------------------------------ auth

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

    @staticmethod
    def _get(url, **kwargs):
        response = requests.get(url, timeout=20, **kwargs)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _post(url, json=None, **kwargs):
        response = requests.post(url, json=json or {}, timeout=60, **kwargs)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _patch(url, json=None, **kwargs):
        response = requests.patch(url, json=json or {}, timeout=20, **kwargs)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _put(url, json=None, **kwargs):
        response = requests.put(url, json=json or {}, timeout=20, **kwargs)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _delete(url, **kwargs):
        response = requests.delete(url, timeout=20, **kwargs)
        response.raise_for_status()

    # ---------------------------------------------------------------- users

    def list_users(self):
        return self._get(f"{self.base_url}/api/users", headers=self._headers())

    def get_user(self, uid):
        return self._get(f"{self.base_url}/api/users/{uid}", headers=self._headers())

    def create_user(self, payload):
        return self._post(f"{self.base_url}/api/users", payload, headers=self._headers())

    def update_user(self, uid, payload):
        return self._patch(f"{self.base_url}/api/users/{uid}", payload, headers=self._headers())

    def deactivate_user(self, uid):
        self._delete(f"{self.base_url}/api/users/{uid}", headers=self._headers())

    def list_user_memberships(self, uid):
        return self._get(f"{self.base_url}/api/users/{uid}/memberships", headers=self._headers())

    def list_user_project_memberships(self, uid):
        return self._get(f"{self.base_url}/api/users/{uid}/project-memberships", headers=self._headers())

    def list_user_roles(self, uid):
        return self._get(f"{self.base_url}/api/users/{uid}/roles", headers=self._headers())

    def list_user_permissions(self, uid):
        return self._get(f"{self.base_url}/api/users/{uid}/permissions", headers=self._headers())

    # ---------------------------------------------------------- departments

    def list_departments(self):
        return self._get(f"{self.base_url}/api/departments", headers=self._headers())

    def get_department(self, department_id):
        return self._get(f"{self.base_url}/api/departments/{department_id}", headers=self._headers())

    def create_department(self, payload):
        return self._post(f"{self.base_url}/api/departments", payload, headers=self._headers())

    def update_department(self, department_id, payload):
        return self._patch(f"{self.base_url}/api/departments/{department_id}", payload, headers=self._headers())

    def list_department_members(self, department_id):
        return self._get(f"{self.base_url}/api/departments/{department_id}/members", headers=self._headers())

    def assign_department_member(self, department_id, payload):
        return self._post(
            f"{self.base_url}/api/departments/{department_id}/members",
            payload,
            headers=self._headers(),
        )

    def update_department_member(self, department_id, user_id, payload):
        return self._patch(
            f"{self.base_url}/api/departments/{department_id}/members/{user_id}",
            payload,
            headers=self._headers(),
        )

    def remove_department_member(self, department_id, user_id):
        self._delete(
            f"{self.base_url}/api/departments/{department_id}/members/{user_id}",
            headers=self._headers(),
        )

    # ---------------------------------------------------------------- roles

    def list_roles(self):
        return self._get(f"{self.base_url}/api/roles", headers=self._headers())

    def get_role(self, role_id):
        return self._get(f"{self.base_url}/api/roles/{role_id}", headers=self._headers())

    def create_role(self, payload):
        return self._post(f"{self.base_url}/api/roles", payload, headers=self._headers())

    def update_role(self, role_id, payload):
        return self._patch(f"{self.base_url}/api/roles/{role_id}", payload, headers=self._headers())

    def delete_role(self, role_id):
        self._delete(f"{self.base_url}/api/roles/{role_id}", headers=self._headers())

    def list_role_permissions(self, role_id):
        return self._get(f"{self.base_url}/api/roles/{role_id}/permissions", headers=self._headers())

    def set_role_permissions(self, role_id, payload):
        return self._put(
            f"{self.base_url}/api/roles/{role_id}/permissions",
            payload,
            headers=self._headers(),
        )

    # ------------------------------------------------------------ permissions

    def list_permissions(self):
        return self._get(f"{self.base_url}/api/permissions", headers=self._headers())

    # -------------------------------------------------------------- projects

    def list_projects(self):
        return self._get(f"{self.base_url}/api/projects", headers=self._headers())

    def get_project(self, project_id):
        return self._get(f"{self.base_url}/api/projects/{project_id}", headers=self._headers())

    def create_project(self, payload):
        return self._post(f"{self.base_url}/api/projects", payload, headers=self._headers())

    def update_project(self, project_id, payload):
        return self._patch(f"{self.base_url}/api/projects/{project_id}", payload, headers=self._headers())

    def list_project_members(self, project_id):
        return self._get(f"{self.base_url}/api/projects/{project_id}/members", headers=self._headers())

    def assign_project_member(self, project_id, uid, payload=None):
        return self._post(
            f"{self.base_url}/api/projects/{project_id}/members/{uid}",
            payload or {},
            headers=self._headers(),
        )

    def revoke_project_member(self, project_id, uid):
        self._delete(
            f"{self.base_url}/api/projects/{project_id}/members/{uid}",
            headers=self._headers(),
        )

    def leave_project(self, project_id):
        self._post(
            f"{self.base_url}/api/projects/{project_id}/members/me/leave",
            headers=self._headers(),
        )

    def list_project_access_grants(self, project_id):
        return self._get(f"{self.base_url}/api/projects/{project_id}/access", headers=self._headers())

    def grant_project_access(self, project_id, payload):
        return self._post(
            f"{self.base_url}/api/projects/{project_id}/access",
            payload,
            headers=self._headers(),
        )

    def revoke_project_access(self, grant_id):
        self._delete(f"{self.base_url}/api/project-access/{grant_id}", headers=self._headers())

    # ------------------------------------------------------------ documents

    def list_documents(self):
        return self._get(f"{self.base_url}/api/documents", headers=self._headers())

    def create_document(self, payload):
        return self._post(f"{self.base_url}/api/documents", payload, headers=self._headers())

    def delete_document(self, document_id):
        self._delete(f"{self.base_url}/api/documents/{document_id}", headers=self._headers())

    def list_project_documents(self, project_id):
        return self._get(f"{self.base_url}/api/projects/{project_id}/documents", headers=self._headers())

    def list_document_access_grants(self, document_id):
        return self._get(f"{self.base_url}/api/documents/{document_id}/access", headers=self._headers())

    def grant_document_access(self, document_id, payload):
        return self._post(
            f"{self.base_url}/api/documents/{document_id}/access",
            payload,
            headers=self._headers(),
        )

    def revoke_document_access(self, grant_id):
        self._delete(f"{self.base_url}/api/document-access/{grant_id}", headers=self._headers())