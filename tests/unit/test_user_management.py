from datetime import datetime, timezone

import pytest

from app.domain.entities.organization_models import Department, User
from app.domain.services.organization_errors import ConflictError, NotFoundError
from app.use_cases.organization.user_management import UserManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def make_service(users=None, departments=None):
    return UserManagementService(lambda: InMemoryUnitOfWork(users, departments))


def test_admin_can_create_user_with_dynamic_role():
    department = Department("d1", "Engineering")
    service = make_service(departments=[department])

    user = service.create_user(
        actor_uid="admin",
        uid="u1",
        name="Asha Rao",
        email="asha@example.com",
        role="Solution Architect",
        department_id="d1",
    )

    assert user.role == "Solution Architect"
    assert user.department_id == "d1"


def test_duplicate_user_identifier_is_rejected():
    existing = User("u1", "Asha", "asha@example.com", "Developer", "d1")
    service = make_service(users=[existing], departments=[Department("d1", "Engineering")])

    with pytest.raises(ConflictError):
        service.create_user("admin", "u1", "Other", "other@example.com", "Tester", "d1")


def test_unknown_department_is_rejected():
    service = make_service()

    with pytest.raises(NotFoundError):
        service.create_user("admin", "u1", "Asha", "asha@example.com", "Developer", "missing")


def test_deactivate_user_changes_status():
    existing = User("u1", "Asha", "asha@example.com", "Developer", "d1")
    service = make_service(users=[existing], departments=[Department("d1", "Engineering")])

    updated = service.deactivate_user("admin", "u1")

    assert updated.status == "inactive"
