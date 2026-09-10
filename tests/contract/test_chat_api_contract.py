from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_endpoint_returns_chat_response():
    payload = {
        "question": "What is the annual leave policy?",
        "session_id": "session-123",
        "conversation_history": [
            {"role": "user", "content": "What are the standard working hours?"},
            {"role": "assistant", "content": "Standard hours are 9am to 5pm Monday to Friday."},
        ],
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "session-123"
    assert "answer" in body
    assert len(body["citations"]) >= 1
