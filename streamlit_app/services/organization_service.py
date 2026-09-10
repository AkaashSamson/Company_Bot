import requests


class OrganizationService:
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")

    def list_users(self):
        response = requests.get(f"{self.base_url}/api/users", timeout=15)
        response.raise_for_status()
        return response.json()

    def create_user(self, payload):
        response = requests.post(f"{self.base_url}/api/users", json=payload, timeout=15)
        response.raise_for_status()
        return response.json()

    def update_user(self, uid, payload):
        response = requests.patch(f"{self.base_url}/api/users/{uid}", json=payload, timeout=15)
        response.raise_for_status()
        return response.json()

    def deactivate_user(self, uid):
        response = requests.delete(f"{self.base_url}/api/users/{uid}", timeout=15)
        response.raise_for_status()

    def list_departments(self):
        response = requests.get(f"{self.base_url}/api/departments", timeout=15)
        response.raise_for_status()
        return response.json()

    def create_department(self, payload):
        response = requests.post(f"{self.base_url}/api/departments", json=payload, timeout=15)
        response.raise_for_status()
        return response.json()

    def list_projects(self):
        response = requests.get(f"{self.base_url}/api/projects", timeout=15)
        response.raise_for_status()
        return response.json()

    def create_project(self, payload):
        response = requests.post(f"{self.base_url}/api/projects", json=payload, timeout=15)
        response.raise_for_status()
        return response.json()

    def assign_member(self, project_id, uid):
        response = requests.post(
            f"{self.base_url}/api/projects/{project_id}/members/{uid}",
            timeout=15,
        )
        response.raise_for_status()

    def revoke_member(self, project_id, uid):
        response = requests.delete(
            f"{self.base_url}/api/projects/{project_id}/members/{uid}",
            timeout=15,
        )
        response.raise_for_status()
