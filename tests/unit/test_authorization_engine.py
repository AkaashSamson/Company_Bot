"""Comprehensive tests of the AuthorizationEngine — single source of truth
for every identity, project, document and retrieval-scope decision.
"""
import pytest

from app.domain.entities.organization_models import (
    Department,
    Document,
    DepartmentMember,
    DocumentGrant,
    Project,
    ProjectGrant,
    User,
    UserProject,
)
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine, AuthorizationScope
from app.infrastructure.persistence.rbac_seed import seed_rbac
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


ADMIN = AuthenticatedPrincipal("admin")
MANAGER = AuthenticatedPrincipal("mgr")
DEVELOPER = AuthenticatedPrincipal("dev")
TESTER = AuthenticatedPrincipal("tester")
OUTSIDER = AuthenticatedPrincipal("outsider")
OTHER_MANAGER = AuthenticatedPrincipal("other-mgr")
INACTIVE = AuthenticatedPrincipal("inactive")
UNKNOWN = AuthenticatedPrincipal("unknown")
PM = AuthenticatedPrincipal("pm")


def _build(departments=None, users=None, projects=None, memberships=None, documents=None, department_members=None):
    users = [
        User("admin", "Admin", "admin@example.com", "Admin", "d1"),
        User("mgr", "Manager", "mgr@example.com", "Manager", "d1"),
        User("dev", "Developer", "dev@example.com", "Developer", "d1"),
        User("tester", "Tester", "tester@example.com", "Tester", "d1"),
        User("pm", "PM", "pm@example.com", "Developer", "d1"),
        User("inactive", "Inactive", "inc@example.com", "Developer", "d1", status="inactive"),
        User("other-mgr", "Other Mgr", "om@example.com", "Manager", "d2"),
        User("outsider", "Outsider", "out@example.com", "Developer", "d2"),
        *(users or []),
    ]
    all_departments = [Department("d1", "Engineering"), Department("d2", "QA")]
    if departments:
        all_departments.extend(departments)
    uow = InMemoryUnitOfWork(
        users,
        all_departments,
        projects or [],
        memberships or [],
        documents or [],
        department_members or [],
    )
    seed_rbac(lambda: uow)
    engine = AuthorizationEngine(lambda: uow)
    return uow, engine


# ------------------------------------------------------------------- identity

class TestIdentity:
    def test_admin_bypasses_every_permission(self, _p=(_build,)):
        uow, engine = _build()
        assert engine.is_admin(ADMIN) is True
        assert engine.has_permission(ADMIN, "DOCUMENT_DELETE") is True
        assert engine.has_permission(ADMIN, "NOT_IN_CATALOG") is True

    def test_inactive_user_has_no_permissions(self):
        uow, engine = _build()
        assert engine.has_permission(INACTIVE, "DOCUMENT_VIEW") is False
        assert engine.permissions_for_user("inactive") == set()

    def test_unknown_user_has_no_permissions(self):
        uow, engine = _build()
        assert engine.has_permission(UNKNOWN, "DOCUMENT_VIEW") is False
        assert engine.roles_for_user("unknown") == []

    def test_permission_is_db_driven_not_hardcoded(self):
        uow, engine = _build(users=[User("dev2", "Dev2", "dev2@example.com", "Developer", "d1")])
        dev2 = AuthenticatedPrincipal("dev2")
        assert engine.has_permission(dev2, "DOCUMENT_VIEW") is True
        assert engine.has_permission(dev2, "USER_CREATE") is False
        developer = uow.roles.get_by_name("Developer")
        create_id = uow.permissions.get_by_name("USER_CREATE").permission_id
        current = [p.permission_id for p in uow.roles.permissions_for_role(developer.role_id)]
        uow.roles.set_permissions(developer.role_id, current + [create_id])
        assert engine.has_permission(dev2, "USER_CREATE") is True

    def test_department_scoped_role_is_scoped(self):
        uow, engine = _build()
        create_id = uow.permissions.get_by_name("USER_CREATE").permission_id
        role = _dept_role("Eng Lead", "d1")
        uow.roles.save(role)
        uow.roles.set_permissions(role.role_id, [create_id])
        uow.department_members.save(DepartmentMember("dev", "d1", membership_role="Eng Lead"))
        assert engine.has_permission(DEVELOPER, "USER_CREATE") is True
        assert engine.has_permission(OUTSIDER, "USER_CREATE") is False

    def test_roles_for_user_resolves_named_and_membership_roles(self):
        uow, engine = _build()
        uow.roles.save(_dept_role("Eng Lead", "d1"))
        uow.department_members.save(DepartmentMember("dev", "d1", membership_role="Eng Lead"))
        role_names = {role.name for role in engine.roles_for_user("dev")}
        assert "Developer" in role_names
        assert "Eng Lead" in role_names

    def test_can_action_maps_to_permission(self):
        uow, engine = _build()
        assert engine.can(ADMIN, "create_project") is True
        assert engine.can(DEVELOPER, "create_project") is False
        assert engine.can(DEVELOPER, "view_projects") is True
        assert engine.can(ADMIN, "unknown_action") is False

    def test_can_manage_role_respects_scope(self):
        uow, engine = _build()
        global_role = uow.roles.get_by_name("Developer")
        eng_role = _dept_role("Eng Lead", "d1")
        uow.roles.save(eng_role)
        qa_role = _dept_role("QA Lead", "d2")
        uow.roles.save(qa_role)
        assert engine.can_manage_role(ADMIN, global_role) is True
        assert engine.can_manage_role(MANAGER, global_role) is False
        assert engine.can_manage_role(MANAGER, eng_role) is True
        assert engine.can_manage_role(MANAGER, qa_role) is False

    def test_can_manage_department(self):
        uow, engine = _build()
        assert engine.can_manage_department(ADMIN, "d1") is True
        assert engine.can_manage_department(ADMIN, "d2") is True
        assert engine.can_manage_department(MANAGER, "d1") is True
        assert engine.can_manage_department(MANAGER, "d2") is False
        assert engine.can_manage_department(DEVELOPER, "d1") is True
        assert engine.can_manage_department(DEVELOPER, "d2") is False
        assert engine.can_manage_department(OUTSIDER, "d1") is False
        assert engine.can_manage_department(INACTIVE, "d1") is False


# ------------------------------------------------------------------- projects

class TestProjectAccess:
    @pytest.fixture()
    def ctx(self):
        p1 = Project("p1", "Project A", "d1", manager_uid="pm")
        p2 = Project("p2", "Project B", "d1")
        p3 = Project("p3", "Project C", "d2")
        uow, engine = _build(
            projects=[p1, p2, p3],
            memberships=[UserProject("dev", "p1"), UserProject("tester", "p1")],
        )
        return uow, engine

    def test_admin_can_access_every_project(self, ctx):
        uow, engine = ctx
        assert engine.can_access_project(ADMIN, "p1") is True
        assert engine.can_access_project(ADMIN, "p3") is True
        assert engine.accessible_project_ids(ADMIN) == ["p1", "p2", "p3"]

    def test_manager_same_dept_can_manage_project(self, ctx):
        uow, engine = ctx
        assert engine.can_manage_project(MANAGER, "p1") is True
        assert engine.can_manage_project(MANAGER, "p3") is False

    def test_outside_manager_cannot_manage(self, ctx):
        uow, engine = ctx
        assert engine.can_manage_project(OTHER_MANAGER, "p1") is False

    def test_project_member_can_access(self, ctx):
        uow, engine = ctx
        assert engine.can_access_project(DEVELOPER, "p1") is True

    def test_same_department_can_access_management_view(self, ctx):
        uow, engine = ctx
        assert engine.can_access_project(DEVELOPER, "p2") is True

    def test_non_member_not_in_document_scope(self, ctx):
        uow, engine = ctx
        assert engine.can_view_project_documents(DEVELOPER, "p2") is False

    def test_designated_pm_can_manage(self, ctx):
        uow, engine = ctx
        assert engine.can_manage_project(PM, "p1") is True
        assert engine.can_manage_project(PM, "p2") is False

    def test_cross_department_access_denied(self, ctx):
        uow, engine = ctx
        assert engine.can_access_project(OUTSIDER, "p1") is False

    def test_inactive_user_denied(self, ctx):
        uow, engine = ctx
        assert engine.can_access_project(INACTIVE, "p1") is False

    def test_accessible_project_ids_for_non_admin(self, ctx):
        uow, engine = ctx
        ids = engine.accessible_project_ids(DEVELOPER)
        assert ids == ["p1"]

    def test_project_grant_to_user(self, ctx):
        uow, engine = ctx
        uow.project_grants.save(ProjectGrant("p2", "user", user_id="dev"))
        assert engine.can_access_project(DEVELOPER, "p2") is True
        assert "p2" in engine.accessible_project_ids(DEVELOPER)

    def test_project_grant_to_role(self, ctx):
        uow, engine = ctx
        tester_role = uow.roles.get_by_name("Tester")
        uow.project_grants.save(ProjectGrant("p2", "role", role_id=tester_role.role_id))
        assert engine.can_view_project_documents(TESTER, "p2") is True
        assert engine.can_view_project_documents(DEVELOPER, "p2") is False

    def test_can_manage_project_members(self, ctx):
        uow, engine = ctx
        assert engine.can_manage_project_members(MANAGER, "p1") is True
        assert engine.can_manage_project_members(OUTSIDER, "p1") is False


# ------------------------------------------------------------------- documents

class TestDocumentAccess:
    @pytest.fixture()
    def ctx(self):
        p1 = Project("p1", "Project A", "d1", manager_uid="pm")
        p2 = Project("p2", "Project B", "d2")
        docs = [
            Document("doc1", "Doc 1", project_id="p1"),
            Document("doc2", "Doc 2", project_id="p2"),
            Document("doc3", "Unassigned Doc", project_id=None),
        ]
        uow, engine = _build(
            projects=[p1, p2],
            memberships=[UserProject("dev", "p1"), UserProject("tester", "p1")],
            documents=docs,
        )
        return uow, engine

    def test_admin_can_read_and_manage_all(self, ctx):
        uow, engine = ctx
        for doc_id in ("doc1", "doc2", "doc3"):
            assert engine.can_read_document(ADMIN, doc_id) is True
            assert engine.can_manage_document(ADMIN, doc_id) is True

    def test_non_member_cannot_read_project_doc(self, ctx):
        uow, engine = ctx
        assert engine.can_read_document(DEVELOPER, "doc2") is False

    def test_member_can_read_project_doc(self, ctx):
        uow, engine = ctx
        assert engine.can_read_document(DEVELOPER, "doc1") is True

    def test_manager_same_dept_can_manage_doc(self, ctx):
        uow, engine = ctx
        assert engine.can_manage_document(MANAGER, "doc1") is True

    def test_pm_can_manage_doc(self, ctx):
        uow, engine = ctx
        assert engine.can_manage_document(PM, "doc1") is True

    def test_member_cannot_manage_doc(self, ctx):
        uow, engine = ctx
        assert engine.can_manage_document(DEVELOPER, "doc1") is False

    def test_unassigned_doc_manager_can_read(self, ctx):
        uow, engine = ctx
        assert engine.can_read_document(MANAGER, "doc3") is True

    def test_unassigned_doc_developer_can_read(self, ctx):
        uow, engine = ctx
        assert engine.can_read_document(DEVELOPER, "doc3") is True

    def test_unassigned_doc_pm_can_read(self, ctx):
        uow, engine = ctx
        assert engine.can_read_document(PM, "doc3") is True

    def test_document_grant_to_user(self, ctx):
        uow, engine = ctx
        uow.document_grants.save(DocumentGrant("doc2", "user", user_id="dev"))
        assert engine.can_read_document(DEVELOPER, "doc2") is True

    def test_document_grant_to_role(self, ctx):
        uow, engine = ctx
        tester_role = uow.roles.get_by_name("Tester")
        uow.document_grants.save(DocumentGrant("doc2", "role", role_id=tester_role.role_id))
        assert engine.can_read_document(TESTER, "doc2") is True
        assert engine.can_read_document(DEVELOPER, "doc2") is False

    def test_document_grant_bypasses_project_membership(self, ctx):
        uow, engine = ctx
        outsider = AuthenticatedPrincipal("outsider")
        uow.document_grants.save(DocumentGrant("doc1", "user", user_id="outsider"))
        assert engine.can_read_document(outsider, "doc1") is True
        assert engine.can_manage_document(outsider, "doc1") is False

    def test_inactive_user_denied(self, ctx):
        uow, engine = ctx
        assert engine.can_read_document(INACTIVE, "doc1") is False

    def test_inactive_document_denied(self, ctx):
        uow, engine = ctx
        doc = uow.documents.get("doc1")
        doc.status = "inactive"
        uow.documents.save(doc)
        assert engine.can_read_document(DEVELOPER, "doc1") is False

    def test_upload_unassigned_admin_manager_only(self, ctx):
        uow, engine = ctx
        assert engine.can_upload_document(ADMIN, None) is True
        assert engine.can_upload_document(MANAGER, None) is True
        assert engine.can_upload_document(DEVELOPER, None) is False
        assert engine.can_upload_document(PM, None) is False

    def test_upload_project_admin_pm_manager(self, ctx):
        uow, engine = ctx
        assert engine.can_upload_document(ADMIN, "p1") is True
        assert engine.can_upload_document(PM, "p1") is True
        assert engine.can_upload_document(MANAGER, "p1") is True
        assert engine.can_upload_document(DEVELOPER, "p1") is False
        assert engine.can_upload_document(OTHER_MANAGER, "p1") is False

    def test_upload_unknown_project(self, ctx):
        uow, engine = ctx
        assert engine.can_upload_document(DEVELOPER, "missing") is False

    def test_manage_access_requires_permission(self, ctx):
        uow, engine = ctx
        assert engine.can(ADMIN, "manage_document_access") is True
        assert engine.can(MANAGER, "manage_document_access") is True
        assert engine.can(DEVELOPER, "manage_document_access") is False
        assert engine.can(TESTER, "manage_document_access") is False


# ------------------------------------------------------------------- scope

class TestAuthorizationScope:
    @pytest.fixture()
    def ctx(self):
        p1 = Project("p1", "Project A", "d1", manager_uid="pm")
        p2 = Project("p2", "Project B", "d1")
        p3 = Project("p3", "Project C", "d2")
        docs = [
            Document("doc1", "Doc 1", project_id="p1"),
            Document("doc2", "Doc 2", project_id="p2"),
            Document("doc3", "Doc 3", project_id="p3"),
            Document("doc-u", "Unassigned", project_id=None),
        ]
        uow, engine = _build(
            projects=[p1, p2, p3],
            memberships=[UserProject("dev", "p1"), UserProject("tester", "p1"), UserProject("pm", "p1")],
            documents=docs,
        )
        return uow, engine

    def test_admin_scope_is_unrestricted(self, ctx):
        uow, engine = ctx
        scope = engine.authorization_scope(ADMIN)
        assert scope.is_admin is True
        assert scope.project_ids is None
        assert scope.document_ids is None
        assert scope.include_unassigned is True

    def test_developer_scope_is_membership_only(self, ctx):
        uow, engine = ctx
        scope = engine.authorization_scope(DEVELOPER)
        assert scope.is_admin is False
        assert scope.project_ids == ["p1"]
        assert scope.include_unassigned is True

    def test_manager_scope_includes_unassigned(self, ctx):
        uow, engine = ctx
        scope = engine.authorization_scope(MANAGER)
        assert scope.include_unassigned is True
        assert "p1" in scope.project_ids
        assert "p3" not in scope.project_ids

    def test_pm_project_in_scope(self, ctx):
        uow, engine = ctx
        scope = engine.authorization_scope(PM)
        assert "p1" in scope.project_ids

    def test_outsider_empty_scope(self, ctx):
        uow, engine = ctx
        scope = engine.authorization_scope(OUTSIDER)
        assert scope.project_ids == []

    def test_inactive_empty_scope(self, ctx):
        uow, engine = ctx
        scope = engine.authorization_scope(INACTIVE)
        assert scope.project_ids == []

    def test_selected_project_in_scope(self, ctx):
        uow, engine = ctx
        scope = engine.authorization_scope(DEVELOPER, "p1")
        assert scope.project_ids == ["p1"]

    def test_selected_project_not_in_scope_denied(self, ctx):
        uow, engine = ctx
        scope = engine.authorization_scope(DEVELOPER, "p2")
        assert scope.project_ids == []

    def test_selected_project_with_document_grant(self, ctx):
        uow, engine = ctx
        uow.document_grants.save(DocumentGrant("doc2", "user", user_id="dev"))
        scope = engine.authorization_scope(DEVELOPER, "p2")
        assert scope.project_ids == []
        assert scope.document_ids is not None
        assert "doc2" in scope.document_ids
        assert "doc3" not in scope.document_ids

    def test_project_grant_expands_scope(self, ctx):
        uow, engine = ctx
        uow.project_grants.save(ProjectGrant("p3", "user", user_id="dev"))
        scope = engine.authorization_scope(DEVELOPER)
        assert "p3" in scope.project_ids

    def test_project_grant_to_role_expands_scope(self, ctx):
        uow, engine = ctx
        tester_role = uow.roles.get_by_name("Tester")
        uow.project_grants.save(ProjectGrant("p3", "role", role_id=tester_role.role_id))
        scope = engine.authorization_scope(TESTER)
        assert "p3" in scope.project_ids

    def test_document_ids_only_active(self, ctx):
        uow, engine = ctx
        uow.document_grants.save(DocumentGrant("doc-u", "user", user_id="dev"))
        doc = uow.documents.get("doc-u")
        doc.status = "inactive"
        uow.documents.save(doc)
        scope = engine.authorization_scope(DEVELOPER)
        assert scope.document_ids is None


# ---------------------------------------------------------------- access contacts

class TestProjectAccessContact:
    @pytest.fixture()
    def ctx(self):
        p1 = Project("p1", "Project Alpha", "d1", manager_uid="pm")
        p2 = Project("p2", "Project Bravo", "d1")
        uow, engine = _build(projects=[p1, p2])
        return uow, engine

    def test_returns_managed_project_and_manager_name(self, ctx):
        uow, engine = ctx
        contact = engine.project_access_contact("p1")
        assert contact == {
            "project_id": "p1",
            "project_name": "Project Alpha",
            "manager_name": "PM",
        }

    def test_placeholder_manager_when_project_has_no_manager(self, ctx):
        uow, engine = ctx
        contact = engine.project_access_contact("p2")
        assert contact["project_name"] == "Project Bravo"
        assert contact["manager_name"] == "the project manager"

    def test_placeholder_manager_when_manager_unknown(self, ctx):
        uow, engine = ctx
        p3 = Project("p3", "Project Gamma", "d1", manager_uid="ghost")
        uow.projects.save(p3)
        contact = engine.project_access_contact("p3")
        assert contact["manager_name"] == "the project manager"

    def test_unknown_project_returns_none(self, ctx):
        uow, engine = ctx
        assert engine.project_access_contact("nope") is None


def _dept_role(name, department_id, permission_ids=None):
    from app.domain.entities.organization_models import Role, Permission
    role = Role(None, name, f"{name} role", scope="department", department_id=department_id)
    return role
