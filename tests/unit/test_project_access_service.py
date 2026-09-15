"""Unit tests for ProjectAccessService — grant/revoke/list project-level access."""
import pytest

from app.domain.entities.organization_models import (
    Department,
    Project,
    ProjectGrant,
    User,
    UserProject,
)
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError
from app.infrastructure.persistence.rbac_seed import seed_rbac
from tests.fixtures.organization_repositories import InMemoryUnitOfWork

from app.use_cases.organization.project_access import ProjectAccessService

ADMIN = AuthenticatedPrincipal("admin")
MANAGER = AuthenticatedPrincipal("mgr")
DEVELOPER = AuthenticatedPrincipal("dev")
TESTER = AuthenticatedPrincipal("tester")
OTHER_MGR = AuthenticatedPrincipal("other-mgr")


def _build(projects=None, memberships=None):
    users = [
        User("admin", "Admin", "a@ex.com", "Admin", "d1"),
        User("mgr", "Manager", "m@ex.com", "Manager", "d1"),
        User("dev", "Developer", "d@ex.com", "Developer", "d1"),
        User("tester", "Tester", "t@ex.com", "Tester", "d1"),
        User("other-mgr", "Other Mgr", "o@ex.com", "Manager", "d2"),
    ]
    uow = InMemoryUnitOfWork(
        users,
        [Department("d1", "Eng"), Department("d2", "QA")],
        projects or [],
        memberships or [],
        [],
        [],
    )
    seed_rbac(lambda: uow)
    engine = AuthorizationEngine(lambda: uow)
    return uow, ProjectAccessService(lambda: uow, engine), engine


_svc = _build


class TestListGrants:
    def test_empty_when_no_grants(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        assert svc.list(ADMIN, "p1") == []

    def test_grants_visible_to_admin(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        uow.project_grants.save(ProjectGrant("p1", "user", user_id="dev"))
        result = svc.list(ADMIN, "p1")
        assert len(result) == 1

    def test_grants_visible_to_manager_same_dept(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        uow.project_grants.save(ProjectGrant("p1", "role", role_id=2))
        result = svc.list(MANAGER, "p1")
        assert len(result) == 1

    def test_outside_manager_cannot_list(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        uow.project_grants.save(ProjectGrant("p1", "user", user_id="dev"))
        with pytest.raises(ForbiddenError):
            svc.list(OTHER_MGR, "p1")


class TestGrant:
    def test_admin_grants_to_user(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        result = svc.grant(ADMIN, "p1", principal_type="user", user_id="dev")
        assert result.principal_type == "user"
        assert result.user_id == "dev"
        assert len(uow.project_grants.list()) == 1

    def test_admin_grants_to_role(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        result = svc.grant(ADMIN, "p1", principal_type="role", role_id=2)
        assert result.principal_type == "role"
        assert result.role_id == 2

    def test_duplicate_user_grant_rejected(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        svc.grant(ADMIN, "p1", principal_type="user", user_id="dev")
        with pytest.raises(ConflictError, match="Grant already exists"):
            svc.grant(ADMIN, "p1", principal_type="user", user_id="dev")

    def test_duplicate_role_grant_rejected(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        svc.grant(ADMIN, "p1", principal_type="role", role_id=2)
        with pytest.raises(ConflictError, match="Grant already exists"):
            svc.grant(ADMIN, "p1", principal_type="role", role_id=2)

    def test_user_grant_requires_user_id(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        with pytest.raises(ValueError, match="requires user_id"):
            svc.grant(ADMIN, "p1", principal_type="user")

    def test_role_grant_requires_role_id(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        with pytest.raises(ValueError, match="requires role_id"):
            svc.grant(ADMIN, "p1", principal_type="role")

    def test_user_grant_user_must_exist(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        with pytest.raises(NotFoundError, match="not found"):
            svc.grant(ADMIN, "p1", principal_type="user", user_id="noone")

    def test_role_grant_role_must_exist(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        with pytest.raises(NotFoundError, match="not found"):
            svc.grant(ADMIN, "p1", principal_type="role", role_id=999)

    def test_manager_same_dept_can_grant(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        result = svc.grant(MANAGER, "p1", principal_type="user", user_id="dev")
        assert result is not None

    def test_developer_cannot_grant(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        with pytest.raises(ForbiddenError):
            svc.grant(DEVELOPER, "p1", principal_type="user", user_id="tester")

    def test_outside_manager_cannot_grant(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        with pytest.raises(ForbiddenError):
            svc.grant(OTHER_MGR, "p1", principal_type="user", user_id="dev")


class TestRevoke:
    def test_admin_revokes(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        grant = svc.grant(ADMIN, "p1", principal_type="user", user_id="dev")
        svc.revoke(ADMIN, grant.internal_id)
        assert len(uow.project_grants.list_for_project("p1")) == 0

    def test_revoke_nonexistent_rejected(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        with pytest.raises(NotFoundError, match="not found"):
            svc.revoke(ADMIN, 999)

    def test_manager_same_dept_can_revoke(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        grant = svc.grant(ADMIN, "p1", principal_type="user", user_id="dev")
        svc.revoke(MANAGER, grant.internal_id)
        assert len(uow.project_grants.list_for_project("p1")) == 0

    def test_developer_cannot_revoke(self):
        uow, svc, _ = _svc(projects=[Project("p1", "P", "d1")])
        grant = svc.grant(ADMIN, "p1", principal_type="user", user_id="dev")
        with pytest.raises(ForbiddenError):
            svc.revoke(DEVELOPER, grant.internal_id)
