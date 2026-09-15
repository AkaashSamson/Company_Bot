from fastapi.testclient import TestClient

from app.api.dependencies import get_authorization_service, get_chat_principal
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationScope
from app.main import app


class StubAuthorization:
    def authorization_scope(self, principal, selected_project_id=None):
        if selected_project_id == "p-denied":
            return AuthorizationScope(is_admin=False, project_ids=[], document_ids=None, include_unassigned=False)
        return AuthorizationScope(is_admin=False, project_ids=["p1"], document_ids=None, include_unassigned=False)

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


def test_chat_allows_authorized_project_selection():
    app.dependency_overrides[get_chat_principal] = lambda: AuthenticatedPrincipal("u1")
    app.dependency_overrides[get_authorization_service] = lambda: StubAuthorization()
    try:
        response = TestClient(app).post(
            "/api/chat",
            json={"question": "What is the policy?", "project_id": "p1"},
        )
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()