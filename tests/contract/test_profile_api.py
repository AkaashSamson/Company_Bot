from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_principal, get_profile_service
from app.domain.entities.organization_models import (
    Department,
    DepartmentMember,
    Document,
    DocumentGrant,
    Permission,
    Project,
    Role,
    User,
    UserProject,
)
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app
from app.use_cases.organization.profile import ProfileService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def _seed_developer_fixture():
    permissions = [
        Permission(None, "DOCUMENT_VIEW"),
        Permission(None, "PROJECT_VIEW"),
        Permission(None, "PROJECT_LEAVE"),
        Permission(None, "DOCUMENT_QUERY"),
    ]
    now = datetime(2025, 1, 10, tzinfo=timezone.utc)
    uow = InMemoryUnitOfWork(
        users=[User("u1", "Asha Rao", "asha@example.com", "Developer", "d1", employee_id="EMP-001")],
        departments=[Department("d1", "Engineering"), Department("d2", "Other")],
        projects=[
            Project("p1", "Nexora Banking", "d1", manager_uid="m1", start_date=now, status="active"),
            Project("p2", "Secret Project", "d2", status="active"),
        ],
        memberships=[UserProject("u1", "p1", membership_role="Member", status="active", assigned_at=now)],
        department_members=[DepartmentMember("u1", "d1", billable_status="billable", status="active")],
        documents=[
            Document("doc-a", "Architecture Design", "p1", status="active", file_type="pdf", version="1.0"),
            Document("doc-grant", "API Documentation", "p2", status="active"),
            Document("doc-secret", "Financial Planning", "p2", status="active"),
        ],
        document_grants=[DocumentGrant("doc-grant", "user", user_id="u1", status="active")],
        roles=[Role(None, "Developer", scope="global", status="active")],
        permissions=permissions,
    )
    developer = uow.roles.get_by_name("Developer")
    uow.roles.set_permissions(developer.role_id, [permission.permission_id for permission in permissions])
    return uow


def test_developer_can_fetch_own_profile():
    unit_of_work = _seed_developer_fixture()
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("u1")
    app.dependency_overrides[get_profile_service] = lambda: ProfileService(lambda: unit_of_work)
    client = TestClient(app)

    try:
        response = client.get("/api/users/me/profile")
        assert response.status_code == 200
        body = response.json()

        assert body["user"]["name"] == "Asha Rao"
        assert body["user"]["employee_id"] == "EMP-001"
        assert body["user"]["role"] == "Developer"
        assert body["department"] == {"department_id": "d1", "department_name": "Engineering"}
        assert body["billable_status"] == "billable"

        assert [project["project_id"] for project in body["projects"]] == ["p1"]
        project = body["projects"][0]
        assert project["is_member"] is True
        assert project["membership"]["membership_role"] == "Member"
        assert project["membership"]["status"] == "active"
        assert project["manager"] == {"uid": "m1", "name": None}

        document_ids = {document["document_id"] for document in body["documents"]}
        assert document_ids == {"doc-a", "doc-grant"}
        assert "doc-secret" not in document_ids

        sources = {document["document_id"]: document["access_source"] for document in body["documents"]}
        assert sources["doc-a"] == "project_access"
        assert sources["doc-grant"] == "document_grant"

        assert {"DOCUMENT_VIEW", "DOCUMENT_QUERY", "PROJECT_VIEW", "PROJECT_LEAVE"}.issubset(body["permissions"])
        assert [role["name"] for role in body["roles"]] == ["Developer"]
    finally:
        app.dependency_overrides.clear()


def test_profile_never_leaks_inaccessible_document_metadata():
    unit_of_work = _seed_developer_fixture()
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("u1")
    app.dependency_overrides[get_profile_service] = lambda: ProfileService(lambda: unit_of_work)
    client = TestClient(app)

    try:
        body = client.get("/api/users/me/profile").json()
        raw = str(body)
        assert "doc-secret" not in raw
        assert "Financial Planning" not in raw

        for document in body["documents"]:
            assert "content" not in document
            assert "description" not in document
            assert "storage_location" not in document
            assert "original_filename" not in document
    finally:
        app.dependency_overrides.clear()


def test_ordinary_user_does_not_need_role_view_permission():
    permissions = [Permission(None, "DOCUMENT_QUERY")]
    unit_of_work = InMemoryUnitOfWork(
        users=[User("quin", "Quinn Li", "quinn@example.com", "Tester", "d1", employee_id="EMP-002")],
        departments=[Department("d1", "Engineering")],
        roles=[Role(None, "Tester", scope="global", status="active")],
        permissions=permissions,
    )
    tester = unit_of_work.roles.get_by_name("Tester")
    unit_of_work.roles.set_permissions(tester.role_id, [permissions[0].permission_id])

    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("quin")
    app.dependency_overrides[get_profile_service] = lambda: ProfileService(lambda: unit_of_work)
    client = TestClient(app)

    try:
        response = client.get("/api/users/me/profile")
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["uid"] == "quin"
        assert "DOCUMENT_QUERY" in body["permissions"]
        assert "ROLE_VIEW" not in body["permissions"]
    finally:
        app.dependency_overrides.clear()