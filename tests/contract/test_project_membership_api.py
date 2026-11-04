from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_current_principal,
    get_membership_management_service,
    get_project_management_service,
)
from app.domain.entities.organization_models import Department, User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app
from app.use_cases.organization.project_management import ProjectManagementService
from app.use_cases.organization.membership_management import MembershipManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_admin_can_create_project_and_assign_membership():
    uow = InMemoryUnitOfWork(
        users=[User("a1", "Admin", "a@example.com", "Admin", "d1"), User("u1", "User", "u@example.com", "Developer", "d1")],
        departments=[Department("d1", "Engineering")],
    )
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("a1")
    app.dependency_overrides[get_project_management_service] = lambda: ProjectManagementService(lambda: uow)
    app.dependency_overrides[get_membership_management_service] = lambda: MembershipManagementService(lambda: uow)
    try:
        client = TestClient(app)
        response = client.post("/api/projects", json={"project_id": "p1", "project_name": "Project A", "department_id": "d1"})
        assert response.status_code == 201
        response = client.post("/api/projects/p1/members/u1")
        assert response.status_code == 204
    finally:
        app.dependency_overrides.clear()
