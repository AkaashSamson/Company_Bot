from datetime import datetime, timezone

import pytest

from app.domain.entities.organization_models import (
    Department,
    DepartmentMember,
    Document,
    DocumentGrant,
    Permission,
    Project,
    ProjectGrant,
    Role,
    User,
    UserProject,
)
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.organization_errors import ForbiddenError
from app.use_cases.organization.profile import ProfileService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def _developer_unit_of_work():
    permissions = [
        Permission(None, "DOCUMENT_VIEW"),
        Permission(None, "PROJECT_VIEW"),
        Permission(None, "PROJECT_LEAVE"),
        Permission(None, "DOCUMENT_QUERY"),
    ]
    now = datetime(2025, 2, 1, tzinfo=timezone.utc)
    uow = InMemoryUnitOfWork(
        users=[
            User("u1", "Asha Rao", "asha@example.com", "Developer", "d1", employee_id="EMP-001"),
            User("m1", "Maya Boss", "maya@example.com", "Manager", "d1", employee_id="EMP-000"),
        ],
        departments=[Department("d1", "Engineering"), Department("d2", "Other")],
        projects=[
            Project("p1", "Nexora Banking", "d1", manager_uid="m1", start_date=now, status="active"),
            Project("p2", "Granted Project", "d2", status="active"),
            Project("p3", "Archived Project", "d1", status="archived"),
            Project("p4", "Secret Project", "d2", status="active"),
        ],
        memberships=[UserProject("u1", "p1", membership_role="Member", status="active", assigned_at=now)],
        department_members=[DepartmentMember("u1", "d1", billable_status="non-billable", status="active")],
        documents=[
            Document("doc-a", "Architecture Design", "p1", status="active", file_type="pdf", version="1.0"),
            Document("doc-g", "Granted Doc", "p2", status="active", file_type="md", version="2.0"),
            Document("doc-secret", "Secret Doc", "p4", status="active"),
            Document("doc-archived", "Old Doc", "p1", status="archived"),
        ],
        project_grants=[ProjectGrant("p2", "user", user_id="u1", status="active")],
        document_grants=[DocumentGrant("doc-g", "user", user_id="u1", status="active")],
        roles=[Role(None, "Developer", scope="global", status="active")],
        permissions=permissions,
    )
    developer = uow.roles.get_by_name("Developer")
    uow.roles.set_permissions(developer.role_id, [permission.permission_id for permission in permissions])
    return uow


def _profile(principal_uid="u1"):
    uow = _developer_unit_of_work()
    return ProfileService(lambda: uow).get_profile(AuthenticatedPrincipal(principal_uid))


def test_personal_information_and_billable_status():
    body = _profile()
    assert body["user"] == {
        "uid": "u1",
        "name": "Asha Rao",
        "email": "asha@example.com",
        "employee_id": "EMP-001",
        "role": "Developer",
        "status": "active",
    }
    assert body["department"] == {"department_id": "d1", "department_name": "Engineering"}
    assert body["billable_status"] == "non-billable"


def test_billable_status_none_when_membership_inactive():
    uow = _developer_unit_of_work()
    member = uow.department_members.get("u1", "d1")
    member.status = "inactive"
    body = ProfileService(lambda: uow).get_profile(AuthenticatedPrincipal("u1"))
    assert body["billable_status"] is None


def test_projects_only_include_accessible_and_active_projects():
    body = _profile()
    project_ids = [project["project_id"] for project in body["projects"]]
    assert "p1" in project_ids
    assert "p2" in project_ids
    assert "p3" not in project_ids
    assert "p4" not in project_ids

    by_id = {project["project_id"]: project for project in body["projects"]}
    assert by_id["p1"]["is_member"] is True
    assert by_id["p1"]["membership"]["membership_role"] == "Member"
    assert by_id["p1"]["manager"] == {"uid": "m1", "name": "Maya Boss"}
    assert by_id["p2"]["is_member"] is False
    assert by_id["p2"]["membership"] is None
    assert by_id["p2"]["access_source"] == "grant"
    assert by_id["p1"]["access_source"] == "department"


def test_documents_only_include_readable_ones_with_source_labels():
    body = _profile()
    document_ids = {document["document_id"] for document in body["documents"]}
    assert "doc-a" in document_ids
    assert "doc-g" in document_ids
    assert "doc-secret" not in document_ids
    assert "doc-archived" not in document_ids

    by_id = {document["document_id"]: document for document in body["documents"]}
    assert by_id["doc-a"]["access_source"] == "project_access"
    assert by_id["doc-a"]["project_name"] == "Nexora Banking"
    assert by_id["doc-g"]["access_source"] == "document_grant"
    assert by_id["doc-g"]["project_name"] == "Granted Project"


def test_roles_and_effective_permissions():
    body = _profile()
    assert [role["name"] for role in body["roles"]] == ["Developer"]
    assert {"DOCUMENT_VIEW", "DOCUMENT_QUERY", "PROJECT_VIEW", "PROJECT_LEAVE"}.issubset(body["permissions"])


def test_inactive_actor_is_rejected():
    uow = _developer_unit_of_work()
    uow.users.get_by_uid("u1").status = "inactive"
    with pytest.raises(ForbiddenError):
        ProfileService(lambda: uow).get_profile(AuthenticatedPrincipal("u1"))