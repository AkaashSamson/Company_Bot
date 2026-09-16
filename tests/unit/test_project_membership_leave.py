from datetime import datetime, timezone

import pytest

from app.domain.entities.organization_models import Department, Project, User, UserProject
from app.domain.services.organization_errors import ForbiddenError, NotFoundError
from app.use_cases.organization.membership_management import MembershipManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def _service(uow):
    return MembershipManagementService(lambda: uow)


def test_designated_project_manager_can_assign_members_to_own_project():
    manager = User("m1", "Manager", "m@example.com", "Developer", "d1")
    member = User("u1", "User", "u@example.com", "Developer", "d1")
    project = Project("p1", "Project A", "d1", manager_uid="m1")
    uow = InMemoryUnitOfWork([manager, member], [Department("d1", "Engineering")], [project])
    assignment = _service(uow).assign("m1", "u1", "p1", membership_role="Lead")
    assert assignment.membership_role == "Lead"
    assert assignment.status == "active"


def test_project_manager_cannot_manage_other_project():
    manager = User("m1", "Manager", "m@example.com", "Developer", "d1")
    member = User("u1", "User", "u@example.com", "Developer", "d1")
    projects = [Project("p1", "Project A", "d1", manager_uid="m1"), Project("p2", "Project B", "d1")]
    uow = InMemoryUnitOfWork([manager, member], [Department("d1", "Engineering")], projects)
    with pytest.raises(ForbiddenError):
        _service(uow).assign("m1", "u1", "p2")


def test_admin_can_assign_regardless_of_scope():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    member = User("u1", "User", "u@example.com", "Developer", "d2")
    project = Project("p1", "Project A", "d2")
    uow = InMemoryUnitOfWork([admin, member], [Department("d1", "Engineering"), Department("d2", "QA")], [project])
    assignment = _service(uow).assign("a1", "u1", "p1", membership_role="Member")
    assert assignment.uid == "u1"


def test_user_can_leave_project():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    member = User("u1", "User", "u@example.com", "Developer", "d1")
    project = Project("p1", "Project A", "d1")
    membership = UserProject("u1", "p1")
    uow = InMemoryUnitOfWork([admin, member], [Department("d1", "Engineering")], [project], [membership])
    _service(uow).leave("u1", "p1")
    assert uow.memberships.get("u1", "p1").status == "left"
    assert uow.memberships.get("u1", "p1").left_at is not None


def test_user_cannot_leave_project_they_do_not_belong_to():
    user = User("u1", "User", "u@example.com", "Developer", "d1")
    uow = InMemoryUnitOfWork([user], [Department("d1", "Engineering")], [Project("p1", "Project A", "d1")])
    with pytest.raises(NotFoundError):
        _service(uow).leave("u1", "p1")


def test_leaving_clears_designated_project_managership():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    manager = User("m1", "Manager", "m@example.com", "Developer", "d1")
    project = Project("p1", "Project A", "d1", manager_uid="m1")
    membership = UserProject("m1", "p1")
    uow = InMemoryUnitOfWork([admin, manager], [Department("d1", "Engineering")], [project], [membership])
    _service(uow).leave("m1", "p1")
    assert uow.projects.get("p1").manager_uid is None


def test_revoked_membership_can_be_reassigned():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    member = User("u1", "User", "u@example.com", "Developer", "d1")
    project = Project("p1", "Project A", "d1")
    membership = UserProject("u1", "p1", status="revoked")
    uow = InMemoryUnitOfWork([admin, member], [Department("d1", "Engineering")], [project], [membership])
    assignment = _service(uow).assign("a1", "u1", "p1")
    assert assignment.status == "active"
    assert assignment.left_at is None


def test_list_members_allowed_for_same_department_user():
    viewer = User("v1", "Viewer", "v@example.com", "Manager", "d1")
    project = Project("p1", "Project A", "d1")
    memberships = [UserProject("u1", "p1"), UserProject("u2", "p1")]
    uow = InMemoryUnitOfWork([viewer], [Department("d1", "Engineering")], [project], memberships)
    members = _service(uow).list_members("v1", "p1")
    assert {member.uid for member in members} == {"u1", "u2"}


def test_list_members_forbidden_outside_department():
    viewer = User("v1", "Viewer", "v@example.com", "Manager", "d2")
    project = Project("p1", "Project A", "d1")
    uow = InMemoryUnitOfWork([viewer], [Department("d1", "Engineering"), Department("d2", "QA")], [project])
    with pytest.raises(ForbiddenError):
        _service(uow).list_members("v1", "p1")