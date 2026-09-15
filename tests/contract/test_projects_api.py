from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_current_principal,
    get_membership_management_service,
    get_project_management_service,
)
from app.domain.entities.organization_models import Department, Project, User, UserProject
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app
from app.use_cases.organization.project_management import ProjectManagementService
from app.use_cases.organization.membership_management import MembershipManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_create_project_returns_internal_and_human_readable_ids():
    uow = InMemoryUnitOfWork(
        users=[User("a1", "Admin", "a@example.com", "Admin", "d1")],
        departments=[Department("d1", "Engineering")],
    )
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("a1")
    app.dependency_overrides[get_project_management_service] = lambda: ProjectManagementService(lambda: uow)
    try:
        client = TestClient(app)
        response = client.post("/api/projects", json={"project_name": "Project A", "department_id": "d1"})
        assert response.status_code == 201
        body = response.json()
        assert body["project_id"] == "PROJ-001"
        assert body["internal_id"] == 1
    finally:
        app.dependency_overrides.clear()


def test_get_project_by_human_readable_id_and_internal_id():
    project = Project("p1", "Project A", "d1")
    uow = InMemoryUnitOfWork(
        users=[User("a1", "Admin", "a@example.com", "Admin", "d1")],
        departments=[Department("d1", "Engineering")],
        projects=[project],
    )
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("a1")
    app.dependency_overrides[get_project_management_service] = lambda: ProjectManagementService(lambda: uow)
    try:
        client = TestClient(app)
        by_code = client.get("/api/projects/p1")
        assert by_code.status_code == 200
        assert by_code.json()["internal_id"] == project.internal_id
        by_internal = client.get(f"/api/projects/{project.internal_id}")
        assert by_internal.status_code == 200
        assert by_internal.json()["project_id"] == "p1"
    finally:
        app.dependency_overrides.clear()


def test_update_project_and_clear_manager():
    manager = User("m1", "Manager", "m@example.com", "Manager", "d1")
    project = Project("p1", "Project A", "d1", manager_uid="m1")
    uow = InMemoryUnitOfWork(
        users=[manager],
        departments=[Department("d1", "Engineering")],
        projects=[project],
    )
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("m1")
    app.dependency_overrides[get_project_management_service] = lambda: ProjectManagementService(lambda: uow)
    try:
        client = TestClient(app)
        response = client.patch("/api/projects/p1", json={"description": "revised"})
        assert response.status_code == 200
        assert response.json()["description"] == "revised"
    finally:
        app.dependency_overrides.clear()


def test_assign_member_with_role_and_list_members():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    member = User("u1", "User", "u@example.com", "Developer", "d1")
    project = Project("p1", "Project A", "d1")
    uow = InMemoryUnitOfWork(
        users=[admin, member],
        departments=[Department("d1", "Engineering")],
        projects=[project],
    )
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("a1")
    app.dependency_overrides[get_project_management_service] = lambda: ProjectManagementService(lambda: uow)
    app.dependency_overrides[get_membership_management_service] = lambda: MembershipManagementService(lambda: uow)
    try:
        client = TestClient(app)
        assign = client.post("/api/projects/p1/members/u1", json={"membership_role": "Lead"})
        assert assign.status_code == 204
        members = client.get("/api/projects/p1/members")
        assert members.status_code == 200
        assert members.json()[0]["membership_role"] == "Lead"
        assert members.json()[0]["status"] == "active"
    finally:
        app.dependency_overrides.clear()


def test_leave_project():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    member = User("u1", "User", "u@example.com", "Developer", "d1")
    project = Project("p1", "Project A", "d1")
    membership = UserProject("u1", "p1")
    uow = InMemoryUnitOfWork(
        users=[admin, member],
        departments=[Department("d1", "Engineering")],
        projects=[project],
        memberships=[membership],
    )
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("u1")
    app.dependency_overrides[get_project_management_service] = lambda: ProjectManagementService(lambda: uow)
    app.dependency_overrides[get_membership_management_service] = lambda: MembershipManagementService(lambda: uow)
    try:
        client = TestClient(app)
        response = client.post("/api/projects/p1/members/me/leave")
        assert response.status_code == 204
        assert uow.memberships.get("u1", "p1").status == "left"
    finally:
        app.dependency_overrides.clear()