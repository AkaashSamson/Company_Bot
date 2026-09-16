import pytest

from app.domain.entities.organization_models import Department, User
from app.domain.services.organization_errors import ConflictError, ForbiddenError
from app.use_cases.organization.user_management import UserManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def make_service(users=None, departments=None, employee_id_prefix="MSS"):
    admin = User("admin", "Admin", "admin@example.com", "Admin", "d1")
    unit_of_work = InMemoryUnitOfWork([admin, *(users or [])], departments)
    return UserManagementService(lambda: unit_of_work, employee_id_prefix=employee_id_prefix)


def test_employee_ids_are_sequentially_generated_with_prefix():
    department = Department("d1", "Engineering")
    service = make_service(departments=[department])

    first = service.create_user("admin", "u1", "Asha Rao", "asha@example.com", "Developer", "d1")
    second = service.create_user("admin", "u2", "Bob Rao", "bob@example.com", "Developer", "d1")

    assert first.employee_id == "MSS-001"
    assert second.employee_id == "MSS-002"


def test_employee_id_prefix_is_configurable():
    department = Department("d1", "Engineering")
    service = make_service(departments=[department], employee_id_prefix="EMP")

    user = service.create_user("admin", "u1", "Asha Rao", "asha@example.com", "Developer", "d1")

    assert user.employee_id == "EMP-001"


def test_explicit_employee_id_is_respected():
    department = Department("d1", "Engineering")
    service = make_service(departments=[department])

    user = service.create_user("admin", "u1", "Asha Rao", "asha@example.com", "Developer", "d1", employee_id="MSS-500")

    assert user.employee_id == "MSS-500"


def test_duplicate_employee_id_is_rejected():
    department = Department("d1", "Engineering")
    service = make_service(departments=[department])
    service.create_user("admin", "u1", "Asha Rao", "asha@example.com", "Developer", "d1", employee_id="MSS-500")

    with pytest.raises(ConflictError):
        service.create_user("admin", "u2", "Bob Rao", "bob@example.com", "Developer", "d1", employee_id="MSS-500")


def test_employee_id_follows_highest_existing_suffix():
    department = Department("d1", "Engineering")
    existing = User("u0", "Old", "old@example.com", "Developer", "d1", employee_id="MSS-010")
    service = make_service(users=[existing], departments=[department])

    user = service.create_user("admin", "u1", "Asha Rao", "asha@example.com", "Developer", "d1")

    assert user.employee_id == "MSS-011"


def test_first_and_last_name_are_persisted():
    department = Department("d1", "Engineering")
    service = make_service(departments=[department])

    user = service.create_user("admin", "u1", "Asha Rao", "asha@example.com", "Developer", "d1", first_name="Asha", last_name="Rao")

    assert user.first_name == "Asha"
    assert user.last_name == "Rao"


def test_department_supports_description_and_billable_policy():
    service = make_service(departments=[Department("d1", "Engineering")])

    department = service.create_department("admin", "d2", "Quality Assurance", description="QA team", default_billable="non-billable")

    assert department.description == "QA team"
    assert department.default_billable == "non-billable"


def test_invalid_department_billable_policy_is_rejected():
    service = make_service(departments=[Department("d1", "Engineering")])

    with pytest.raises(ValueError):
        service.create_department("admin", "d2", "QA", default_billable="maybe")


def test_non_admin_cannot_create_department():
    manager = User("m1", "Manager", "manager@example.com", "Manager", "d1")
    unit_of_work = InMemoryUnitOfWork([manager], [Department("d1", "Engineering")])
    service = UserManagementService(lambda: unit_of_work)

    with pytest.raises(ForbiddenError):
        service.create_department("m1", "d2", "QA")


def test_update_department_changes_default_billable_policy():
    department = Department("d1", "Engineering", default_billable="billable")
    service = make_service(departments=[department])

    updated = service.update_department("admin", "d1", {"default_billable": "both"})

    assert updated.default_billable == "both"


def test_get_department_returns_404_for_missing():
    service = make_service(departments=[Department("d1", "Engineering")])

    from app.domain.services.organization_errors import NotFoundError

    with pytest.raises(NotFoundError):
        service.get_department("missing")