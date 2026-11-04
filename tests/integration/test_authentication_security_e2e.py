from app.domain.entities.organization_models import User
from app.domain.services.authentication_service import AuthenticationServiceImpl
from app.infrastructure.authentication.password_hasher import PasswordHasher
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_password_representation_does_not_contain_plaintext():
    hasher = PasswordHasher()
    user = User("u1", "User", "u@example.com", "Developer", "d1", username="user", password_representation=hasher.hash("secret-password"))
    unit_of_work = InMemoryUnitOfWork(users=[user])
    service = AuthenticationServiceImpl(lambda: unit_of_work, hasher, "a" * 32)

    service.authenticate("user", "secret-password")

    assert "secret-password" not in unit_of_work.users.get_by_uid("u1").password_representation


def test_old_password_stops_working_after_password_change():
    hasher = PasswordHasher()
    user = User("u1", "User", "u@example.com", "Developer", "d1", username="user", password_representation=hasher.hash("old-password"))
    unit_of_work = InMemoryUnitOfWork(users=[user])
    service = AuthenticationServiceImpl(lambda: unit_of_work, hasher, "a" * 32)
    principal = service.authenticate("user", "old-password")
    service.change_password(principal, "old-password", "new-password")

    try:
        service.authenticate("user", "old-password")
    except Exception as error:
        assert "Invalid credentials" in str(error)
    else:
        raise AssertionError("Old passwords must stop working")