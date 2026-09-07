import requests


class DocumentUploadError(Exception):
    """Raised when the document upload API returns an error."""


class DocumentService:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def upload(
        self,
        file_name: str,
        file_data: bytes,
        overwrite: bool = False,
        timeout: int = 300,
    ):
        url = f"{self.base_url}/api/documents/upload?overwrite={str(overwrite).lower()}"
        files = {"file": (file_name, file_data)}
        try:
            response = requests.post(url, files=files, timeout=timeout)
        except requests.exceptions.ConnectionError as exc:
            raise DocumentUploadError(
                "The backend is not running. Start FastAPI with: "
                "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise DocumentUploadError(f"The backend request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = ""
            try:
                detail = response.json().get("detail", "")
            except ValueError:
                detail = response.text
            raise DocumentUploadError(detail or f"Upload failed with status {response.status_code}")

        return response.json()
