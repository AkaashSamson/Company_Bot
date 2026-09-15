from fastapi.testclient import TestClient

from app.api.dependencies import get_authorization_service, get_chat_principal
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationScope
from app.main import app


class AdminAuthorization:
    def is_admin(self, principal):
        return True

    def authorization_scope(self, principal, selected_project_id=None):
        return AuthorizationScope(is_admin=True, project_ids=None, document_ids=None, include_unassigned=True)


client = TestClient(app)


def test_chat_endpoint_returns_chat_response():
    app.dependency_overrides[get_chat_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_authorization_service] = lambda: AdminAuthorization()
    try:
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
    finally:
        app.dependency_overrides.clear()