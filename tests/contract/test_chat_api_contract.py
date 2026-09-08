from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_endpoint_requires_authentication():
    """Chat is now a protected resource; anonymous callers get 401."""
    payload = {
        "question": "What is the annual leave policy?",
        "session_id": "session-123",
        "conversation_history": [
            {"role": "user", "content": "What is the annual leave policy?"},
            {"role": "assistant", "content": "It is described in the HR policy."},
        ],
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_upload_endpoint_requires_authentication():
    response = client.post(
        "/api/documents/upload",
        files={"file": ("policy.txt", b"content")},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"