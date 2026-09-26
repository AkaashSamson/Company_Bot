import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.infrastructure.channels.registry import register_channel_adapter, clear_channel_registry
from app.infrastructure.channels.teams.adapter import TeamsChannelAdapter


@pytest.fixture(autouse=True)
def setup_teams():
    clear_channel_registry()
    adapter = TeamsChannelAdapter(skip_auth=True)
    register_channel_adapter(adapter)
    yield
    clear_channel_registry()


def test_channel_not_found():
    client = TestClient(app)
    response = client.post("/api/channels/unknown_channel/messages", json={"text": "hello"})
    assert response.status_code == 404
    assert "not supported" in response.json()["detail"]


def test_teams_message_dispatch(monkeypatch):
    from app.api.routes import channels

    class MockOrchestrator:
        def answer(self, question, **kwargs):
            return {
                "answer": f"Echo: {question}",
                "citations": [{"source": "test.txt", "section": "1", "text": "Citation quote"}],
            }

    monkeypatch.setattr(channels, "_get_orchestrator", lambda: MockOrchestrator())

    client = TestClient(app)
    payload = {
        "type": "message",
        "text": "<at>Bot</at> What is the vacation policy?",
        "from": {"id": "user123", "userPrincipalName": "jane@company.com"},
        "conversation": {"id": "thread456"},
    }
    response = client.post("/api/channels/teams/messages", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "Echo: What is the vacation policy?" in data["text"]
    assert data["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
