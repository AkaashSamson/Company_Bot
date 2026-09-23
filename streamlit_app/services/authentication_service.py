import os

import requests


class AuthenticationService:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or os.getenv("STREAMLIT_API_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")

    def login(self, username: str, password: str):
        response = requests.post(
            f"{self.base_url}/api/auth/login",
            json={"username": username, "password": password},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def refresh(self, refresh_token: str):
        response = requests.post(
            f"{self.base_url}/api/auth/refresh",
            json={"refresh_token": refresh_token},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def change_password(self, token: str, current_password: str, new_password: str, uid: str | None = None):
        payload = {"current_password": current_password, "new_password": new_password}
        if uid:
            payload["uid"] = uid
        response = requests.post(
            f"{self.base_url}/api/auth/change-password",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        response.raise_for_status()