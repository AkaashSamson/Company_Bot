import requests


class ChatService:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def ask(self, question: str, session_id: str = "default-session", history=None, headers=None):
        payload = {
            "question": question,
            "session_id": session_id,
            "conversation_history": history or [],
        }
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            headers=headers or {},
            timeout=60,
        )
        if response.status_code == 401:
            raise RuntimeError("Not authenticated")
        response.raise_for_status()
        return response.json()
