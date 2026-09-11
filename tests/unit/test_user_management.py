from datetime import datetime, timezone

import pytest

from app.core.settings import DEFAULT_USER_PASSWORD
from app.domain.entities.organization_models import Department, User
from app.domain.services.organization_errors import ConflictError, NotFoundError
from app.domain.services.authentication_service import AuthenticationServiceImpl
from app.infrastructure.authentication.password_hasher import PasswordHasher
from app.use_cases.organization.user_management import UserManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def make_service(users=None, departments=None):
    admin = User("admin", "Admin", "admin@example.com", "Admin", "d1")
    return UserManagementService(lambda: InMemoryUnitOfWork([admin, *(users or [])], departments))


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


def test_created_user_without_initial_password_login_uses_default_password():
    department = Department("d1", "Engineering")
    uow = InMemoryUnitOfWork(users=[], departments=[department])
    admin = User("admin", "Admin", "admin@example.com", "Admin", "d1")
    uow.users.save(admin)
    service = UserManagementService(lambda: uow, PasswordHasher())

    user = service.create_user(
        actor_uid="admin",
        uid="u1",
        name="Asha Rao",
        email="asha@example.com",
        role="Developer",
        department_id="d1",
    )
    auth = AuthenticationServiceImpl(lambda: uow, PasswordHasher(), "a" * 32)

    principal = auth.authenticate("u1", DEFAULT_USER_PASSWORD)

    assert principal.uid == "u1"
    assert principal.must_change_password is True
