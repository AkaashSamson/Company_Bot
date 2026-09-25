from datetime import datetime, timezone

import jwt

from app.domain.entities.organization_models import User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authentication_service import AuthenticationServiceImpl
from app.domain.services.organization_errors import AuthenticationError
from app.infrastructure.authentication.password_hasher import PasswordHasher
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def make_user(uid="u1", username="asha", email="asha@example.com", password="secret-123", status="active"):
    hasher = PasswordHasher()
    return User(
        uid, "Asha", email, "Developer", "d1", status=status,
        username=username, password_representation=hasher.hash(password),
    )


def make_service(users):
    hasher = PasswordHasher()
    return AuthenticationServiceImpl(lambda: InMemoryUnitOfWork(users=users), hasher, "test-secret")


def decode(token, secret="test-secret"):
    return jwt.decode(token, secret, algorithms=["HS256"])


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


def test_login_issues_typed_tokens_with_expiry():
    service = make_service([make_user()])

    principal = service.authenticate("asha", "secret-123")

    access = decode(principal.token)
    refresh = decode(principal.refresh_token)
    assert access["sub"] == "u1"
    assert access["token_type"] == "access"
    assert access["exp"] > int(datetime.now(timezone.utc).timestamp())
    assert access["exp"] - access["iat"] == 480 * 60
    assert refresh["token_type"] == "refresh"
    assert refresh["exp"] - refresh["iat"] == 10080 * 60


def test_expired_token_is_rejected():
    service = make_service([make_user()])

    now = int(datetime.now(timezone.utc).timestamp())
    expired = jwt.encode(
        {"sub": "u1", "token_type": "access", "iat": now - 7200, "exp": now - 3600},
        "test-secret",
        algorithm="HS256",
    )

    try:
        service.resolve_token(expired)
    except Exception as error:
        assert "Invalid token" in str(error)
    else:
        raise AssertionError("Expired tokens must be rejected")


def test_refresh_token_rotates_and_returns_new_pair():
    service = make_service([make_user()])

    principal = service.authenticate("asha", "secret-123")
    uid, access_token, refresh_token = service.refresh_access_token(principal.refresh_token)

    assert uid == "u1"
    assert decode(access_token)["token_type"] == "access"
    assert decode(refresh_token)["token_type"] == "refresh"
    assert refresh_token != principal.refresh_token


def test_refresh_token_cannot_be_used_as_access_token():
    service = make_service([make_user()])

    principal = service.authenticate("asha", "secret-123")

    try:
        service.resolve_token(principal.refresh_token)
    except Exception as error:
        assert "Invalid token" in str(error)
    else:
        raise AssertionError("Refresh tokens must not authenticate API calls")


def test_invalid_refresh_token_is_rejected():
    service = make_service([make_user()])

    for bad in ("not-a-jwt", "eyJ.garbage.zzz"):
        try:
            service.refresh_access_token(bad)
        except Exception as error:
            assert isinstance(error, AuthenticationError)
        else:
            raise AssertionError("Invalid refresh tokens must be rejected")

    access = jwt.encode(
        {"sub": "u1", "token_type": "access", "iat": datetime.now(timezone.utc)},
        "test-secret",
        algorithm="HS256",
    )
    try:
        service.refresh_access_token(access)
    except Exception as error:
        assert isinstance(error, AuthenticationError)
    else:
        raise AssertionError("Access tokens must not be accepted as refresh tokens")


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