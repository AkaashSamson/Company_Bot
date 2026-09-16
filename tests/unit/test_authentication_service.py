from app.domain.entities.organization_models import User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authentication_service import AuthenticationServiceImpl
from app.infrastructure.authentication.password_hasher import PasswordHasher
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_password_hash_is_not_plaintext_and_can_be_verified():
    hasher = PasswordHasher()
    encoded = hasher.hash("secret-123")

    assert encoded != "secret-123"
    assert hasher.verify("secret-123", encoded)
    assert not hasher.verify("wrong", encoded)


def test_user_can_login_and_change_password():
    hasher = PasswordHasher()
    user = User(
        "u1", "Asha", "asha@example.com", "Developer", "d1",
        username="asha", password_representation=hasher.hash("old-pass"),
    )
    unit_of_work = InMemoryUnitOfWork(users=[user])
    service = AuthenticationServiceImpl(lambda: unit_of_work, hasher, "test-secret")

    principal = service.authenticate("asha", "old-pass")
    service.change_password(principal, "old-pass", "new-pass")

    assert service.authenticate("asha", "new-pass").uid == "u1"


def test_inactive_user_cannot_login():
    hasher = PasswordHasher()
    user = User(
        "u1", "Asha", "asha@example.com", "Developer", "d1", status="inactive",
        username="asha", password_representation=hasher.hash("old-pass"),
    )
    service = AuthenticationServiceImpl(lambda: InMemoryUnitOfWork(users=[user]), hasher, "test-secret")

    try:
        service.authenticate("asha", "old-pass")
    except Exception as error:
        assert "Invalid credentials" in str(error)
    else:
        raise AssertionError("Inactive users must not authenticate")