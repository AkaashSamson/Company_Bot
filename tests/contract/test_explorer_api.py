from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_principal, get_organization_explorer_service
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
from app.use_cases.organization.organization_explorer import OrganizationExplorerService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def _explorer_fixture():
    permissions = [Permission(None, "DOCUMENT_VIEW"), Permission(None, "PROJECT_VIEW"), Permission(None, "DOCUMENT_QUERY")]
    now = datetime(2025, 3, 1, tzinfo=timezone.utc)
    uow = InMemoryUnitOfWork(
        users=[
            User("a1", "Ana Admin", "ana@example.com", "Admin", "d1", employee_id="EMP-000"),
            User("u1", "Asha Rao", "asha@example.com", "Developer", "d1", employee_id="EMP-001"),
            User("m1", "Maya Boss", "maya@example.com", "Manager", "d1", employee_id="EMP-002"),
            User("bob", "Bob Hidden", "bob@example.com", "Developer", "d2", employee_id="EMP-003"),
        ],
        departments=[Department("d1", "Engineering"), Department("d2", "Other")],
        projects=[
            Project("p1", "Nexora Banking", "d1", manager_uid="m1", description="Core banking upgrade", status="active"),
            Project("p2", "Secret Project", "d2", status="active"),
        ],
        memberships=[
            UserProject("u1", "p1", membership_role="Member", status="active", assigned_at=now),
            UserProject("m1", "p1", membership_role="Lead", status="active", assigned_at=now),
            UserProject("bob", "p2", membership_role="Member", status="active", assigned_at=now),
        ],
        department_members=[
            DepartmentMember("u1", "d1", billable_status="billable", status="active"),
            DepartmentMember("m1", "d1", billable_status="non-billable", status="active"),
        ],
        documents=[
            Document("doc-a", "Architecture Design", "p1", status="active", file_type="pdf", version="1.0",
                     description="Design of the Nexora banking platform", uploaded_by="m1", uploaded_at=now),
            Document("doc-secret", "Financial Planning", "p2", status="active", file_type="xlsx", version="1.0"),
            Document("doc-grant", "API Documentation", "p2", status="active", file_type="md", version="2.0",
                     uploaded_by="a1", uploaded_at=now),
            Document("doc-unassigned", "Org Wide Manual", None, status="active", file_type="pdf", version="1.0"),
        ],
        document_grants=[DocumentGrant("doc-grant", "user", user_id="u1", granted_by_uid="a1", granted_at=now, status="active")],
        roles=[Role(None, "Developer", scope="global", status="active")],
        permissions=permissions,
    )
    developer = uow.roles.get_by_name("Developer")
    uow.roles.set_permissions(developer.role_id, [permission.permission_id for permission in permissions])
    return uow


def _request_as(unit_of_work, uid):
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal(uid)
    app.dependency_overrides[get_organization_explorer_service] = lambda: OrganizationExplorerService(lambda: unit_of_work)
    return TestClient(app)


def test_developer_only_sees_authorized_slices():
    unit_of_work = _explorer_fixture()
    client = _request_as(unit_of_work, "u1")

    try:
        body = client.get("/api/explorer/organization").json()
        assert [dept["department_id"] for dept in body["departments"]] == ["d1"]
        assert [project["project_id"] for project in body["departments"][0]["projects"]] == ["p1"]

        project = body["departments"][0]["projects"][0]
        assert project["manager"] == {"uid": "m1", "name": "Maya Boss"}
        assert project["members_visible"] is False
        assert project["members"] == []
        assert [document["document_id"] for document in project["documents"]] == ["doc-a"]

        unassigned = [document["document_id"] for document in body["unassigned_documents"]]
        assert unassigned == ["doc-unassigned"]
        assert body["unassigned_documents"][0]["access"] == "org_wide"

        people = body["people"]
        assert [person["uid"] for person in people] == ["a1", "u1", "bob", "m1"]
        person_by_uid = {person["uid"]: person for person in people}
        assert person_by_uid["u1"]["department_id"] == "d1"
        assert person_by_uid["u1"]["department_name"] == "Engineering"
        assert person_by_uid["bob"]["department_name"] == "Other"
        assert person_by_uid["u1"]["employee_id"] == "EMP-001"

        additional = [document["document_id"] for document in body["additional_documents"]]
        assert additional == ["doc-grant"]
        assert body["additional_documents"][0]["access"] == "document_grant"
        assert {document["document_id"] for document in body["additional_documents"]} == {"doc-grant"}

        raw = str(body)
        assert "Secret Project" not in raw
        assert "doc-secret" not in raw
    finally:
        app.dependency_overrides.clear()


def test_manager_sees_member_roster_and_unassigned_documents():
    unit_of_work = _explorer_fixture()
    client = _request_as(unit_of_work, "m1")

    try:
        body = client.get("/api/explorer/organization").json()
        project = body["departments"][0]["projects"][0]
        assert project["members_visible"] is True
        member_names = [member["name"] for member in project["members"]]
        assert "Asha Rao" in member_names
        assert project["documents"][0]["document_id"] == "doc-a"

        unassigned = [document["document_id"] for document in body["unassigned_documents"]]
        assert unassigned == ["doc-unassigned"]

        raw = str(body)
        assert "Secret Project" not in raw
        assert "doc-secret" not in raw
    finally:
        app.dependency_overrides.clear()


def test_admin_sees_entire_hierarchy():
    unit_of_work = _explorer_fixture()
    client = _request_as(unit_of_work, "a1")

    try:
        body = client.get("/api/explorer/organization").json()
        assert {dept["department_id"] for dept in body["departments"]} == {"d1", "d2"}
        projects = {
            project["project_id"]
            for department in body["departments"]
            for project in department["projects"]
        }
        assert projects == {"p1", "p2"}

        d2 = next(dept for dept in body["departments"] if dept["department_id"] == "d2")
        secret = next(project for project in d2["projects"] if project["project_id"] == "p2")
        assert secret["members_visible"] is True
        assert {document["document_id"] for document in secret["documents"]} == {"doc-secret", "doc-grant"}

        unassigned = [document["document_id"] for document in body["unassigned_documents"]]
        assert "doc-unassigned" in unassigned
    finally:
        app.dependency_overrides.clear()