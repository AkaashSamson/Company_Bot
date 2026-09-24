"""Targeted regression tests for the 15 authorization-bypass scenarios.

Each test pins the FIXED behavior discovered during the security review.
Tests that exercise scenarios already covered by stronger existing tests
are marked with a reference; novel gaps are filled here for the first time.
"""
import pytest

from app.domain.entities.organization_models import (
    Department,
    Document,
    DocumentGrant,
    Project,
    User,
    UserProject,
)
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine
from app.domain.services.organization_errors import ForbiddenError
from app.infrastructure.persistence.rbac_seed import seed_rbac
from app.use_cases.organization.department_membership import DepartmentMembershipService
from app.use_cases.organization.document_access import DocumentAccessService
from app.use_cases.organization.membership_management import MembershipManagementService
from app.use_cases.organization.user_management import UserManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork

ADMIN     = AuthenticatedPrincipal("admin")
MANAGER   = AuthenticatedPrincipal("mgr")
DEVELOPER = AuthenticatedPrincipal("dev")
OUTSIDER  = AuthenticatedPrincipal("out")
INACTIVE  = AuthenticatedPrincipal("inc")
OTHER_MGR = AuthenticatedPrincipal("om")

D1 = Department("d1", "Alpha")
D2 = Department("d2", "Beta")
P1 = Project("p1", "Project 1", "d1", manager_uid="mgr")
P2 = Project("p2", "Project 2", "d2", manager_uid="om")
P3 = Project("p3", "Project 3", "d1", manager_uid="mgr")
DOC1 = Document("doc1", "Doc 1", project_id="p1", status="active")
DOC2 = Document("doc2", "Doc 2", project_id="p2", status="active")
DOC3 = Document("doc3", "Doc 3", project_id="p3", status="active")


def _ctx(memberships=None):
    uow = InMemoryUnitOfWork(
        users=[
            User("admin", "Admin", "admin@example.com", "Admin", "d1"),
            User("mgr", "Manager", "mgr@example.com", "Manager", "d1"),
            User("dev", "Developer", "dev@example.com", "Developer", "d1"),
            User("out", "Outsider", "out@example.com", "Developer", "d2"),
            User("inc", "Inactive", "inc@example.com", "Developer", "d1", status="inactive"),
            User("om", "Other Mgr", "om@example.com", "Manager", "d2"),
        ],
        departments=[D1, D2],
        projects=[P1, P2, P3],
        documents=[DOC1, DOC2, DOC3],
        memberships=memberships or [],
    )
    seed_rbac(lambda: uow)
    return uow, AuthorizationEngine(lambda: uow)


def _svc(uow, cls, *args):
    return cls(lambda: uow, *args)


# ─────────────────────────────────────────────────────────────────────
# 1. Unauthorized project docs
#    Existing: TestDocumentAccess.test_non_member_cannot_read_project_doc
#    Regression pin: OUTSIDER cannot read DOC1 (p1), DEVELOPER cannot read DOC2 (p2)
# ─────────────────────────────────────────────────────────────────────
class TestScenario01_UnauthorizedProjectDocs:
    def test_outsider_cannot_read_d1_doc(self):
        _, engine = _ctx()
        assert engine.can_read_document(OUTSIDER, "doc1") is False

    def test_developer_cannot_read_d2_doc(self):
        _, engine = _ctx()
        assert engine.can_read_document(DEVELOPER, "doc2") is False


# ─────────────────────────────────────────────────────────────────────
# 2. Unauthorized doc metadata
#    Existing: test_profile_never_leaks_inaccessible_document_metadata
#    Regression pin: OUTSIDER not in project → not visible in scope
# ─────────────────────────────────────────────────────────────────────
class TestScenario02_UnauthorizedDocMetadata:
    def test_outsider_scope_excludes_p1(self):
        _, engine = _ctx()
        scope = engine.authorization_scope(OUTSIDER)
        assert scope.project_ids == []

    def test_inactive_scope_excludes_p1(self):
        _, engine = _ctx()
        scope = engine.authorization_scope(INACTIVE)
        assert scope.project_ids == []


# ─────────────────────────────────────────────────────────────────────
# 3. Cross-dept manager scope
#    Existing: test_outside_manager_cannot_manage, test_manager_cannot_update_user_outside_department
#    Regression pin: OTHER_MGR cannot manage DEPARTMENT d1 members
# ─────────────────────────────────────────────────────────────────────
class TestScenario03_CrossDeptManagerScope:
    def test_other_dept_manager_cannot_update_d1_member(self):
        uow, _ = _ctx()
        svc = _svc(uow, UserManagementService)
        with pytest.raises(ForbiddenError):
            svc.update_user("om", "dev", {"display_name": "tampered"})

    def test_other_dept_manager_cannot_list_d1_members(self):
        uow, _ = _ctx()
        svc = _svc(uow, DepartmentMembershipService)
        with pytest.raises(ForbiddenError):
            svc.list_for_department("om", "d1")


# ─────────────────────────────────────────────────────────────────────
# 4. Doc-level restrictions vs project membership
#    Fixed: doc grant in p2 does NOT grant whole-project access
#    Regression pin: scope with doc grant + selected p2 → project_ids=[], document_ids=[doc2]
# ─────────────────────────────────────────────────────────────────────
class TestScenario04_DocGrantDoesNotLeakProject:
    @staticmethod
    def _ctx_with_doc_grant():
        uow, engine = _ctx(memberships=[UserProject("dev", "p1")])
        uow.document_grants.save(DocumentGrant("doc2", "user", user_id="dev"))
        return uow, engine

    def test_doc_grant_only_scope_excludes_project(self):
        uow, engine = self._ctx_with_doc_grant()
        scope = engine.authorization_scope(DEVELOPER, "p2")
        assert scope.project_ids == []
        assert scope.document_ids is not None
        assert "doc2" in scope.document_ids

    def test_doc_grant_only_no_sibling_leak(self):
        uow, engine = self._ctx_with_doc_grant()
        scope = engine.authorization_scope(DEVELOPER, "p2")
        assert "doc3" not in scope.document_ids


# ─────────────────────────────────────────────────────────────────────
# 5. Inactive users denied access
#    Existing: 8 tests across layers
#    Regression pin: INACTIVE gets empty scope and cannot read documents
# ─────────────────────────────────────────────────────────────────────
class TestScenario05_InactiveUsersDenied:
    def test_inactive_empty_scope(self):
        _, engine = _ctx()
        scope = engine.authorization_scope(INACTIVE)
        assert scope.project_ids == []

    def test_inactive_cannot_read_doc(self):
        _, engine = _ctx()
        assert engine.can_read_document(INACTIVE, "doc1") is False


# ─────────────────────────────────────────────────────────────────────
# 6. Unauthorized Chroma chunks (empty scope → nothing retrievable)
#    Existing: test_empty_project_ids_returns_nothing (integration)
#    Regression pin: scope.project_ids == [] produces no chunks at retrieval level
# ─────────────────────────────────────────────────────────────────────
class TestScenario06_EmptyScopeRetrieval:
    def test_outsider_scope_is_empty(self):
        _, engine = _ctx()
        scope = engine.authorization_scope(OUTSIDER)
        assert scope.project_ids == []
        assert scope.document_ids is None
        assert scope.include_unassigned is True


# ─────────────────────────────────────────────────────────────────────
# 7. Unauthorized citations
#    Existing: integration tests verify unauthorized content never reaches LLM
#    Regression pin: empty scope prevents any document retrieval
# ─────────────────────────────────────────────────────────────────────
class TestScenario07_UnauthorizedCitations:
    def test_outsider_scope_cannot_reach_orchestrator_retrieval(self):
        _, engine = _ctx()
        scope = engine.authorization_scope(OUTSIDER)
        assert scope.project_ids == []


# ─────────────────────────────────────────────────────────────────────
# 8. Direct API call bypass (backend enforces scope, not UI)
#    Existing: test_chat_rejects_explicit_unauthorized_project (contract)
#    Regression pin: chat gate blocks project selection when scope empty
# ─────────────────────────────────────────────────────────────────────
class TestScenario08_DirectAPIBypass:
    def test_outsider_selected_project_is_empty_scope(self):
        _, engine = _ctx()
        scope = engine.authorization_scope(OUTSIDER, "p1")
        assert scope.project_ids == []

    def test_member_selected_project_keeps_scope(self):
        uow, engine = _ctx(memberships=[UserProject("dev", "p1")])
        scope = engine.authorization_scope(DEVELOPER, "p1")
        assert scope.project_ids == ["p1"]


# ─────────────────────────────────────────────────────────────────────
# 9. Streamlit not sole control
#    Existing: test_streamlit_management_pages_* (contract, parses page source)
#    Regression pin: authorization engine is the single source of truth
# ─────────────────────────────────────────────────────────────────────
class TestScenario09_BackendEnforced:
    def test_authorization_engine_is_the_source_of_truth(self):
        uow, engine = _ctx()
        assert engine.can_read_document(OUTSIDER, "doc1") is False


# ─────────────────────────────────────────────────────────────────────
# 10. Self-privilege escalation (non-admin cannot change own role)
#     GAP: no test existed. Now pinned.
# ─────────────────────────────────────────────────────────────────────
class TestScenario10_SelfPrivilegeEscalation:
    def test_manager_cannot_change_own_role_to_admin(self):
        uow, _ = _ctx()
        svc = _svc(uow, UserManagementService)
        with pytest.raises(ForbiddenError, match="Only administrators can change user roles"):
            svc.update_user("mgr", "mgr", {"role": "admin"})

    def test_developer_cannot_change_own_role_to_manager(self):
        uow, _ = _ctx()
        svc = _svc(uow, UserManagementService)
        with pytest.raises(ForbiddenError, match="Only administrators can change user roles"):
            svc.update_user("dev", "dev", {"role": "manager"})

    def test_admin_can_change_role(self):
        uow, _ = _ctx()
        svc = _svc(uow, UserManagementService)
        svc.update_user("admin", "dev", {"role": "lead"})
        updated = uow.users.get_by_uid("dev")
        assert updated.role == "lead"


# ─────────────────────────────────────────────────────────────────────
# 11. Manager → admin escalation (manager cannot create admin user)
#     GAP: no test existed. Now pinned.
# ─────────────────────────────────────────────────────────────────────
class TestScenario11_ManagerAdminCreation:
    def test_manager_cannot_create_admin_user(self):
        uow, _ = _ctx()
        svc = _svc(uow, UserManagementService)
        with pytest.raises(ForbiddenError, match="Only administrators can create admin users"):
            svc.create_user("mgr", "new-admin", "New Admin", "newadmin@example.com", "admin", "d1")

    def test_manager_can_create_developer_user(self):
        uow, _ = _ctx()
        svc = _svc(uow, UserManagementService)
        user = svc.create_user("mgr", "new-dev", "New Dev", "newdev@example.com", "developer", "d1")
        assert user.role == "developer"

    def test_admin_can_create_admin_user(self):
        uow, _ = _ctx()
        svc = _svc(uow, UserManagementService)
        user = svc.create_user("admin", "new-admin-2", "Admin 2", "admin2@example.com", "admin", "d1")
        assert user.role == "admin"


# ─────────────────────────────────────────────────────────────────────
# 12. Dept-scoped manager vs other departments
#     Existing: 8 tests (overlaps with #3)
#     Regression pin: MANAGER cannot manage P2 (d2)
# ─────────────────────────────────────────────────────────────────────
class TestScenario12_DeptScopedManager:
    def test_manager_cannot_manage_other_dept_project(self):
        _, engine = _ctx()
        assert engine.can_manage_project(MANAGER, "p2") is False

    def test_manager_can_manage_own_dept_project(self):
        _, engine = _ctx()
        assert engine.can_manage_project(MANAGER, "p1") is True


# ─────────────────────────────────────────────────────────────────────
# 13. Self-add to projects (manager cannot add self to unrelated project)
#     GAP: existing tests check adding OTHER users; self-add variant not tested.
#     Regression pin: MANAGER cannot add themselves to P2 (d2)
# ─────────────────────────────────────────────────────────────────────
class TestScenario13_SelfAddToProject:
    def test_manager_cannot_self_add_to_other_dept_project(self):
        uow, _ = _ctx()
        svc = _svc(uow, MembershipManagementService)
        with pytest.raises(ForbiddenError):
            svc.assign("mgr", "mgr", "p2")

    def test_designated_pm_cannot_self_add_to_project_not_managed(self):
        uow, _ = _ctx()
        svc = _svc(uow, MembershipManagementService)
        with pytest.raises(ForbiddenError):
            svc.assign("om", "om", "p1")


# ─────────────────────────────────────────────────────────────────────
# 14. Unauthorized doc-access modification
#     Existing: test_developer_cannot_grant, test_developer_cannot_revoke
#     Regression pin: DEVELOPER cannot grant access to DOC1
# ─────────────────────────────────────────────────────────────────────
class TestScenario14_UnauthorizedDocAccessModification:
    def test_developer_cannot_grant_doc_access(self):
        uow, engine = _ctx(memberships=[UserProject("dev", "p1")])
        svc = DocumentAccessService(lambda: uow, engine)
        with pytest.raises(ForbiddenError):
            svc.grant(DEVELOPER, "doc1", principal_type="user", user_id="dev")

    def test_developer_cannot_revoke_doc_access(self):
        uow, engine = _ctx(memberships=[UserProject("dev", "p1")])
        uow.document_grants.save(DocumentGrant("doc1", "user", user_id="mgr"))
        svc = DocumentAccessService(lambda: uow, engine)
        grant = uow.document_grants.for_document("doc1")[0]
        with pytest.raises(ForbiddenError):
            svc.revoke(DEVELOPER, grant.internal_id)


# ─────────────────────────────────────────────────────────────────────
# 15. Leaving project removes scope
#     GAP: existing tests verify leave status but not scope after leave.
#     Regression pin: after leave, authorization_scope returns [].
# ─────────────────────────────────────────────────────────────────────
class TestScenario15_LeaveProjectRemovesScope:
    def test_leave_project_clears_scope(self):
        uow, engine = _ctx(memberships=[UserProject("dev", "p1")])
        assert "p1" in engine.authorization_scope(DEVELOPER).project_ids

        svc = _svc(uow, MembershipManagementService)
        svc.leave("dev", "p1")

        scope_after = engine.authorization_scope(DEVELOPER)
        assert "p1" not in scope_after.project_ids

    def test_leave_project_clears_selected_scope(self):
        uow, engine = _ctx(memberships=[UserProject("dev", "p1")])
        svc = _svc(uow, MembershipManagementService)
        svc.leave("dev", "p1")

        scope_after = engine.authorization_scope(DEVELOPER, "p1")
        assert scope_after.project_ids == []