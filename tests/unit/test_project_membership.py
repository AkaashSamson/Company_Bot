import pytest

from app.domain.entities.organization_models import Department, Project, User, UserProject
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError
from app.use_cases.organization.membership_management import MembershipManagementService
from app.use_cases.organization.project_management import ProjectManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_project_membership_is_idempotent_and_reversible():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    target = User("u1", "User", "u@example.com", "Developer", "d1")
    project = Project("p1", "Project A", "d1")
    uow = InMemoryUnitOfWork([admin, target], [Department("d1", "Engineering")], [project])
    service = MembershipManagementService(lambda: uow)

    first = service.assign("a1", "u1", "p1")
    second = service.assign("a1", "u1", "p1")
    assert first.uid == second.uid == "u1"
    assert len(uow.memberships.list_for_project("p1")) == 1

    service.revoke("a1", "u1", "p1")
    assert uow.memberships.get("u1", "p1").status == "revoked"


def test_manager_cannot_assign_user_to_other_department_project():
    manager = User("m1", "Manager", "m@example.com", "Manager", "d1")
    target = User("u1", "User", "u@example.com", "Developer", "d1")
    project = Project("p2", "Project B", "d2")
    uow = InMemoryUnitOfWork(
        [manager, target],
        [Department("d1", "Engineering"), Department("d2", "QA")],
        [project],
    )

    with pytest.raises(ForbiddenError):
        MembershipManagementService(lambda: uow).assign("m1", "u1", "p2")
