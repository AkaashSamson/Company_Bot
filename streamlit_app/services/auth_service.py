import requests


class AuthError(Exception):
    """Raised when an authentication API call fails."""


class AuthService:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def login(self, email: str, password: str) -> dict:
        payload = {"email": email, "password": password}
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json=payload,
                timeout=15,
            )
        except requests.exceptions.RequestException as exc:
            raise AuthError(
                "The backend is not running. Start FastAPI with: "
                "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
            ) from exc

        if response.status_code >= 400:
            detail = ""
            try:
                detail = response.json().get("detail", "")
            except ValueError:
                detail = response.text
            raise AuthError(detail or f"Login failed with status {response.status_code}")
        return response.json()

    def list_users(self, headers: dict) -> list[dict]:
        response = requests.get(
            f"{self.base_url}/api/users",
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def list_roles(self, headers: dict) -> list[dict]:
        response = requests.get(
            f"{self.base_url}/api/roles",
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()