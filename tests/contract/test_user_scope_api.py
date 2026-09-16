from fastapi.testclient import TestClient

from app.api.dependencies import get_current_principal, get_user_management_service
from app.domain.entities.organization_models import Department, User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app
from app.use_cases.organization.user_management import UserManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_manager_cannot_update_user_outside_department():
    uow = InMemoryUnitOfWork(
        users=[
            User("m1", "Manager", "m@example.com", "Manager", "d1"),
            User("u2", "User", "u@example.com", "Developer", "d2"),
        ],
        departments=[Department("d1", "Engineering"), Department("d2", "QA")],
    )
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("m1")
    app.dependency_overrides[get_user_management_service] = lambda: UserManagementService(lambda: uow)
    try:
        response = TestClient(app).patch("/api/users/u2", json={"name": "Changed"})
        assert response.status_code == 403
        assert uow.users.get_by_uid("u2").name == "User"
    finally:
        app.dependency_overrides.clear()
