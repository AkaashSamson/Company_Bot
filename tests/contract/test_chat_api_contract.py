from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_endpoint_returns_chat_response():
    payload = {
        "question": "What is the annual leave policy?",
        "session_id": "session-123",
        "conversation_history": [
            {"role": "user", "content": "What is the annual leave policy?"},
            {"role": "assistant", "content": "It is described in the HR policy."},
        ],
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "session-123"
    assert "answer" in body
    assert len(body["citations"]) >= 1
