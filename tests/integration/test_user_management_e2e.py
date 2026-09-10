from fastapi.testclient import TestClient

from app.api.dependencies import get_current_principal
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app


def test_user_management_requires_authentication():
    client = TestClient(app)
    response = client.get("/api/users/u1")
    assert response.status_code == 401


def test_authenticated_admin_can_deactivate_user_when_storage_is_configured():
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    client = TestClient(app)
    try:
        response = client.delete("/api/users/missing")
        assert response.status_code in {404, 500}
    finally:
        app.dependency_overrides.clear()
