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


def test_teams_guest_user_gets_unassigned_scope(monkeypatch):
    from app.api.routes import channels

    captured_kwargs = {}

    class MockOrchestrator:
        def answer(self, question, **kwargs):
            captured_kwargs.update(kwargs)
            return {"answer": "Guest response", "citations": []}

    class MockAuthzService:
        def authorization_scope(self, principal, selected_project_id=None):
            # Simulate AuthorizationEngine returning empty scope for unregistered principal
            from app.domain.services.authorization_engine import AuthorizationScope
            return AuthorizationScope(is_admin=False, project_ids=[], document_ids=None, include_unassigned=False)

    monkeypatch.setattr(channels, "_get_orchestrator", lambda: MockOrchestrator())
    monkeypatch.setattr("app.api.dependencies.get_authorization_service", lambda: MockAuthzService())

    client = TestClient(app)
    # Playground payload: sender has no email and id is "User"
    payload = {
        "type": "message",
        "text": "What is the policy for leave?",
        "from": {"id": "User", "name": "User"},
        "conversation": {"id": "playground_thread"},
    }
    response = client.post("/api/channels/teams/messages", json=payload)
    assert response.status_code == 200
    assert "Guest response" in response.json()["text"]

    # Verify authorization_scope passed to orchestrator preserves include_unassigned=True
    scope = captured_kwargs.get("authorization_scope")
    assert scope is not None
    assert scope.include_unassigned is True
    assert scope.is_admin is False
