import requests


class ChatService:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def ask(self, question: str, session_id: str = "default-session", history=None, project_id=None):
        payload = {
            "question": question,
            "session_id": session_id,
            "project_id": project_id,
            "conversation_history": history or [],
        }
        response = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
