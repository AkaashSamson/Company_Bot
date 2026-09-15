from datetime import datetime, timezone

import pytest

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
from app.domain.services.organization_errors import ForbiddenError
from app.use_cases.organization.organization_explorer import OrganizationExplorerService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def _explorer_unit_of_work():
    permissions = [Permission(None, "DOCUMENT_VIEW"), Permission(None, "PROJECT_VIEW")]
    now = datetime(2025, 3, 1, tzinfo=timezone.utc)
    long_description = "x" * 600
    uow = InMemoryUnitOfWork(
        users=[
            User("u1", "Asha Rao", "asha@example.com", "Developer", "d1", employee_id="EMP-001", first_name="Asha"),
            User("m1", "Maya Boss", "maya@example.com", "Manager", "d1", employee_id="EMP-002"),
            User("org", "Org Staff", "org@example.com", "Developer", "d2", employee_id="EMP-003"),
        ],
        departments=[Department("d1", "Engineering"), Department("d2", "Other")],
        projects=[
            Project("p1", "Nexora Banking", "d1", manager_uid="m1", description="Banking platform", status="active"),
            Project("p2", "Hidden Project", "d2", status="active"),
            Project("p3", "Archived", "d1", status="archived"),
        ],
        memberships=[
            UserProject("u1", "p1", membership_role="Member", status="active", assigned_at=now),
        ],
        department_members=[
            DepartmentMember("u1", "d1", billable_status="billable", status="active"),
            DepartmentMember("m1", "d1", membership_role="Head", status="active"),
        ],
        documents=[
            Document("doc-a", "Architecture Design", "p1", status="active", file_type="pdf", version="1.0",
                     description=long_description, uploaded_by="m1", uploaded_at=now),
            Document("doc-secret", "Secret Planning", "p2", status="active", file_type="xlsx", version="1.0"),
            Document("doc-granted", "Granted Spec", "p2", status="active", file_type="md", version="2.0"),
            Document("doc-unassigned", "Manager Manual", None, status="active", file_type="pdf", version="1.0"),
        ],
        document_grants=[
            DocumentGrant("doc-granted", "user", user_id="u1", granted_by_uid="m1", granted_at=now, status="active")
        ],
        roles=[Role(None, "Developer", scope="global", status="active")],
        permissions=permissions,
    )
    return uow


def _service(uow):
    return OrganizationExplorerService(lambda: uow)


def _body(uow, uid):
    return _service(uow).get_organization(AuthenticatedPrincipal(uid))


def test_developer_sees_only_authorized_department_projects_and_documents():
    body = _body(_explorer_unit_of_work(), "u1")
    assert [dept["department_id"] for dept in body["departments"]] == ["d1"]

    project = body["departments"][0]["projects"][0]
    assert project["project_id"] == "p1"
    assert project["department_name"] == "Engineering"
    assert project["manager"] == {"uid": "m1", "name": "Maya Boss"}
    assert project["status"] == "active"
    assert project["members_visible"] is False
    assert project["members"] == []
    assert [document["document_id"] for document in project["documents"]] == ["doc-a"]


def test_developer_never_sees_hidden_information():
    body = _body(_explorer_unit_of_work(), "u1")
    raw = str(body)
    assert "Hidden Project" not in raw
    assert "doc-secret" not in raw
    assert "Secret Planning" not in raw
    assert "Other" not in raw
    assert "Manager Manual" not in raw


def test_granted_document_lands_in_additional_bucket_without_project_leak():
    body = _body(_explorer_unit_of_work(), "u1")
    additional = body["additional_documents"]
    assert [document["document_id"] for document in additional] == ["doc-granted"]
    assert additional[0]["access"] == "document_grant"
    assert additional[0]["granted_by"] == {"uid": "m1", "name": "Maya Boss"}
    assert additional[0]["granted_at"] is not None
    for document in additional:
        assert "project_id" not in document
        assert "project_name" not in document


def test_description_is_truncated_to_500_characters():
    body = _body(_explorer_unit_of_work(), "u1")
    document = body["departments"][0]["projects"][0]["documents"][0]
    assert len(document["description"]) == 500


def test_manager_sees_roster_and_unassigned_documents():
    body = _body(_explorer_unit_of_work(), "m1")
    project = body["departments"][0]["projects"][0]
    assert project["members_visible"] is True
    assert [member["name"] for member in project["members"]] == ["Asha Rao"]
    assert [document["document_id"] for document in project["documents"]] == ["doc-a"]
    assert [document["document_id"] for document in body["unassigned_documents"]] == ["doc-unassigned"]
    assert body["additional_documents"] == []


def test_inactive_user_is_rejected():
    uow = _explorer_unit_of_work()
    uow.users.get_by_uid("u1").status = "inactive"
    with pytest.raises(ForbiddenError):
        _body(uow, "u1")


def test_archived_projects_are_omitted():
    body = _body(_explorer_unit_of_work(), "m1")
    project_ids = [project["project_id"] for dept in body["departments"] for project in dept["projects"]]
    assert "p3" not in project_ids