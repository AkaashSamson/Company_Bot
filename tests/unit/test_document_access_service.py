"""Unit tests for DocumentAccessService — grant/revoke/list document-level access."""
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
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError
from app.infrastructure.persistence.rbac_seed import seed_rbac
from tests.fixtures.organization_repositories import InMemoryUnitOfWork

from app.use_cases.organization.document_access import DocumentAccessService

ADMIN = AuthenticatedPrincipal("admin")
MANAGER = AuthenticatedPrincipal("mgr")
DEVELOPER = AuthenticatedPrincipal("dev")
TESTER = AuthenticatedPrincipal("tester")


def _build(projects=None, memberships=None, documents=None):
    users = [
        User("admin", "Admin", "a@ex.com", "Admin", "d1"),
        User("mgr", "Manager", "m@ex.com", "Manager", "d1"),
        User("dev", "Developer", "d@ex.com", "Developer", "d1"),
        User("tester", "Tester", "t@ex.com", "Tester", "d1"),
    ]
    uow = InMemoryUnitOfWork(
        users,
        [Department("d1", "Eng")],
        projects or [],
        memberships or [],
        documents or [],
        [],
    )
    seed_rbac(lambda: uow)
    engine = AuthorizationEngine(lambda: uow)
    return uow, DocumentAccessService(lambda: uow, engine), engine


def _svc(projects=None, memberships=None, documents=None):
    return _build(projects, memberships, documents)


class TestListGrants:
    def test_empty_when_no_grants(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        assert svc.list(ADMIN, "d1") == []

    def test_grants_visible_to_admin(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        uow.document_grants.save(DocumentGrant("d1", "user", user_id="dev"))
        result = svc.list(ADMIN, "d1")
        assert len(result) == 1
        assert result[0].user_id == "dev"

    def test_grants_visible_to_manager_same_dept(self):
        uow, svc, _ = _svc(
            projects=[Project("p1", "P", "d1")],
            documents=[Document("d1", "Doc 1", project_id="p1")],
        )
        uow.document_grants.save(DocumentGrant("d1", "role", role_id=2))
        result = svc.list(MANAGER, "d1")
        assert len(result) == 1

    def test_grants_visible_to_pm(self):
        uow, svc, _ = _svc(
            projects=[Project("p1", "P", "d1", manager_uid="dev")],
            documents=[Document("d1", "Doc 1", project_id="p1")],
        )
        developer_role = uow.roles.get_by_name("Developer")
        manage_id = uow.permissions.get_by_name("DOCUMENT_MANAGE_ACCESS").permission_id
        uow.roles.set_permissions(
            developer_role.role_id,
            [p.permission_id for p in uow.roles.permissions_for_role(developer_role.role_id)] + [manage_id],
        )
        uow.document_grants.save(DocumentGrant("d1", "user", user_id="tester"))
        result = svc.list(DEVELOPER, "d1")
        assert len(result) == 1

    def test_developer_cannot_list_when_not_pm_or_manager(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        uow.document_grants.save(DocumentGrant("d1", "user", user_id="tester"))
        with pytest.raises(ForbiddenError):
            svc.list(DEVELOPER, "d1")


class TestGrant:
    def test_admin_grants_to_user(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        result = svc.grant(ADMIN, "d1", principal_type="user", user_id="dev")
        assert result.principal_type == "user"
        assert result.user_id == "dev"
        assert len(uow.document_grants.list()) == 1

    def test_admin_grants_to_role(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        result = svc.grant(ADMIN, "d1", principal_type="role", role_id=2)
        assert result.principal_type == "role"
        assert result.role_id == 2

    def test_duplicate_user_grant_rejected(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        svc.grant(ADMIN, "d1", principal_type="user", user_id="dev")
        with pytest.raises(ConflictError, match="Grant already exists"):
            svc.grant(ADMIN, "d1", principal_type="user", user_id="dev")

    def test_duplicate_role_grant_rejected(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        svc.grant(ADMIN, "d1", principal_type="role", role_id=2)
        with pytest.raises(ConflictError, match="Grant already exists"):
            svc.grant(ADMIN, "d1", principal_type="role", role_id=2)

    def test_user_grant_requires_user_id(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        with pytest.raises(ValueError, match="requires user_id"):
            svc.grant(ADMIN, "d1", principal_type="user")

    def test_role_grant_requires_role_id(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        with pytest.raises(ValueError, match="requires role_id"):
            svc.grant(ADMIN, "d1", principal_type="role")

    def test_user_grant_user_must_exist(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        with pytest.raises(NotFoundError, match="not found"):
            svc.grant(ADMIN, "d1", principal_type="user", user_id="noone")

    def test_role_grant_role_must_exist(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        with pytest.raises(NotFoundError, match="not found"):
            svc.grant(ADMIN, "d1", principal_type="role", role_id=999)

    def test_manager_same_dept_can_grant(self):
        uow, svc, _ = _svc(
            projects=[Project("p1", "P", "d1")],
            documents=[Document("d1", "Doc 1", project_id="p1")],
        )
        result = svc.grant(MANAGER, "d1", principal_type="user", user_id="dev")
        assert result is not None

    def test_developer_cannot_grant(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        with pytest.raises(ForbiddenError):
            svc.grant(DEVELOPER, "d1", principal_type="user", user_id="tester")


class TestRevoke:
    def test_admin_revokes(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        grant = svc.grant(ADMIN, "d1", principal_type="user", user_id="dev")
        svc.revoke(ADMIN, grant.internal_id)
        assert len(uow.document_grants.for_document("d1")) == 0

    def test_revoke_nonexistent_rejected(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        with pytest.raises(NotFoundError, match="not found"):
            svc.revoke(ADMIN, 999)

    def test_manager_same_dept_can_revoke(self):
        uow, svc, _ = _svc(
            projects=[Project("p1", "P", "d1")],
            documents=[Document("d1", "Doc 1", project_id="p1")],
        )
        grant = svc.grant(ADMIN, "d1", principal_type="user", user_id="dev")
        svc.revoke(MANAGER, grant.internal_id)
        assert len(uow.document_grants.for_document("d1")) == 0

    def test_developer_cannot_revoke(self):
        uow, svc, _ = _svc(documents=[Document("d1", "Doc 1", project_id="p1")])
        grant = svc.grant(ADMIN, "d1", principal_type="user", user_id="dev")
        with pytest.raises(ForbiddenError):
            svc.revoke(DEVELOPER, grant.internal_id)
