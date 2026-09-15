import pytest

from app.domain.entities.organization_models import Department, User
from app.domain.services.organization_errors import ForbiddenError, NotFoundError
from app.use_cases.organization.department_membership import DepartmentMembershipService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def make_service(users=None, departments=None, department_members=None):
    admin = User("admin", "Admin", "admin@example.com", "Admin", "d1")
    unit_of_work = InMemoryUnitOfWork(
        [admin, *(users or [])],
        departments,
        department_members=department_members,
    )
    return DepartmentMembershipService(lambda: unit_of_work)


def test_assign_creates_active_member_following_department_default():
    department = Department("d1", "Engineering", default_billable="billable")
    user = User("u1", "Asha", "asha@example.com", "Developer", "d1")
    service = make_service(users=[user], departments=[department])

    member = service.assign("admin", "u1", "d1")

    assert member.status == "active"
    assert member.billable_status is None
    assert member.membership_role == "Member"


def test_explicit_billable_override_is_stored():
    department = Department("d1", "Engineering", default_billable="billable")
    user = User("u1", "Asha", "asha@example.com", "Developer", "d1")
    service = make_service(users=[user], departments=[department])

    member = service.assign("admin", "u1", "d1", billable_status="non-billable")

    assert member.billable_status == "non-billable"


def test_changing_department_default_does_not_overwrite_explicit_override():
    department = Department("d1", "Engineering", default_billable="billable")
    user_a = User("a", "Asha", "asha@example.com", "Developer", "d1")
    user_b = User("b", "Bob", "bob@example.com", "Developer", "d1")
    uow = InMemoryUnitOfWork(
        [User("admin", "Admin", "admin@example.com", "Admin", "d1"), user_a, user_b],
        [department],
    )
    service = DepartmentMembershipService(lambda: uow)

    service.assign("admin", "a", "d1")
    service.assign("admin", "b", "d1", billable_status="non-billable")

    department.default_billable = "non-billable"
    uow.departments.save(department)

    members = {member.user_id: member for member in service.list_for_department("admin", "d1")}

    assert members["a"].billable_status is None
    assert members["a"].billable_status or department.default_billable == "non-billable"
    assert members["b"].billable_status == "non-billable"
    assert members["b"].billable_status or department.default_billable == "non-billable"


def test_leave_marks_member_inactive_and_sets_left_at():
    department = Department("d1", "Engineering")
    user = User("u1", "Asha", "asha@example.com", "Developer", "d1")
    service = make_service(users=[user], departments=[department])
    service.assign("admin", "u1", "d1")

    member = service.leave("admin", "u1", "d1")

    assert member.status == "inactive"
    assert member.left_at is not None


def test_reassign_reactivates_member():
    department = Department("d1", "Engineering")
    user = User("u1", "Asha", "asha@example.com", "Developer", "d1")
    service = make_service(users=[user], departments=[department])
    service.assign("admin", "u1", "d1")
    service.leave("admin", "u1", "d1")

    member = service.assign("admin", "u1", "d1")

    assert member.status == "active"
    assert member.left_at is None


def test_invalid_billable_status_is_rejected():
    department = Department("d1", "Engineering")
    user = User("u1", "Asha", "asha@example.com", "Developer", "d1")
    service = make_service(users=[user], departments=[department])

    with pytest.raises(ValueError):
        service.assign("admin", "u1", "d1", billable_status="maybe")


def test_update_can_clear_billable_override():
    department = Department("d1", "Engineering")
    user = User("u1", "Asha", "asha@example.com", "Developer", "d1")
    service = make_service(users=[user], departments=[department])
    service.assign("admin", "u1", "d1", billable_status="billable")

    member = service.update("admin", "u1", "d1", {"billable_status": None})

    assert member.billable_status is None


def test_assign_requires_existing_user():
    department = Department("d1", "Engineering")
    service = make_service(departments=[department])

    with pytest.raises(NotFoundError):
        service.assign("admin", "ghost", "d1")


def test_assign_requires_existing_department():
    user = User("u1", "Asha", "asha@example.com", "Developer", "d1")
    service = make_service(users=[user])

    with pytest.raises(NotFoundError):
        service.assign("admin", "u1", "missing")


def test_manager_cannot_assign_outside_department():
    manager = User("m1", "Manager", "manager@example.com", "Manager", "d1")
    user = User("u2", "Bob", "bob@example.com", "Developer", "d2")
    service = DepartmentMembershipService(
        lambda: InMemoryUnitOfWork([manager, user], [Department("d1", "Engineering"), Department("d2", "QA")])
    )

    with pytest.raises(ForbiddenError):
        service.assign("m1", "u2", "d2")


def test_update_missing_membership_is_rejected():
    department = Department("d1", "Engineering")
    user = User("u1", "Asha", "asha@example.com", "Developer", "d1")
    service = make_service(users=[user], departments=[department])

    with pytest.raises(NotFoundError):
        service.update("admin", "u1", "d1", {"membership_role": "Lead"})