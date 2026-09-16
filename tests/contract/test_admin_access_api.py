from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_current_principal,
    get_project_management_service,
    get_user_management_service,
)
from app.domain.entities.organization_models import Department, Project, User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app
from app.use_cases.organization.project_management import ProjectManagementService
from app.use_cases.organization.user_management import UserManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_admin_can_list_projects_across_departments():
    uow = InMemoryUnitOfWork(
        users=[User("a1", "Admin", "a@example.com", "Admin", "d1")],
        departments=[Department("d1", "Engineering"), Department("d2", "QA")],
        projects=[Project("p1", "Project A", "d1"), Project("p2", "Project B", "d2")],
    )
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("a1")
    app.dependency_overrides[get_project_management_service] = lambda: ProjectManagementService(lambda: uow)
    try:
        response = TestClient(app).get("/api/projects")
        assert response.status_code == 200
        assert {item["project_id"] for item in response.json()} == {"p1", "p2"}
    finally:
        app.dependency_overrides.clear()
