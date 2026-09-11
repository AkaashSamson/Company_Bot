from fastapi.testclient import TestClient

from app.api.dependencies import get_authorization_service, get_chat_principal
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app


class StubAuthorization:
    def authorized_project_ids(self, principal, selected_project_id=None):
        if selected_project_id == "p-denied":
            return []
        return ["p1", "p2"] if selected_project_id is None else [selected_project_id]

    def is_admin(self, principal):
        return False


def test_chat_rejects_explicit_unauthorized_project():
    app.dependency_overrides[get_chat_principal] = lambda: AuthenticatedPrincipal("u1")
    app.dependency_overrides[get_authorization_service] = lambda: StubAuthorization()
    try:
        response = TestClient(app).post(
            "/api/chat",
            json={"question": "What is the policy?", "project_id": "p-denied"},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
