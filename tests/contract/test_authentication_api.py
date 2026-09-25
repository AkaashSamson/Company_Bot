from fastapi.testclient import TestClient

from app.api.dependencies import get_authentication_service, get_current_principal, get_user_management_service
from app.domain.entities.organization_models import User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app
from app.infrastructure.authentication.password_hasher import PasswordHasher
from app.domain.services.authentication_service import AuthenticationServiceImpl
from app.use_cases.organization.user_management import UserManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_login_returns_bearer_token_and_password_change_replaces_old_password():
    hasher = PasswordHasher()
    unit_of_work = InMemoryUnitOfWork(users=[User(
        "admin", "Admin", "admin@example.com", "Admin", "d1",
        username="admin", password_representation=hasher.hash("old-password"),
    )])
    service = AuthenticationServiceImpl(lambda: unit_of_work, hasher, "a" * 32)
    app.dependency_overrides[get_authentication_service] = lambda: service
    app.dependency_overrides[get_user_management_service] = lambda: UserManagementService(lambda: unit_of_work, hasher)
    client = TestClient(app)

    try:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "old-password"})
        assert login.status_code == 200
        token = login.json()["access_token"]
        assert login.json()["token_type"] == "bearer"

        app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin", token)
        changed = client.post(
            "/api/auth/change-password",
            json={"current_password": "old-password", "new_password": "new-password"},
        )
        assert changed.status_code == 204
        assert service.authenticate("admin", "new-password").uid == "admin"
    finally:
        app.dependency_overrides.clear()


def test_invalid_login_returns_401():
    hasher = PasswordHasher()
    service = AuthenticationServiceImpl(
        lambda: InMemoryUnitOfWork(users=[User(
            "admin", "Admin", "admin@example.com", "Admin", "d1",
            username="admin", password_representation=hasher.hash("correct-password"),
        )]),
        hasher,
        "a" * 32,
    )
    app.dependency_overrides[get_authentication_service] = lambda: service
    client = TestClient(app)
    try:
        response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-password"})
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_bearer_token_resolves_for_protected_route():
    hasher = PasswordHasher()
    unit_of_work = InMemoryUnitOfWork(users=[User(
        "admin", "Admin", "admin@example.com", "Admin", "d1",
        username="admin", password_representation=hasher.hash("admin-password"),
    )])
    service = AuthenticationServiceImpl(lambda: unit_of_work, hasher, "a" * 32)
    app.dependency_overrides[get_authentication_service] = lambda: service
    app.dependency_overrides[get_user_management_service] = lambda: UserManagementService(lambda: unit_of_work, hasher)
    client = TestClient(app)

    try:
        token = client.post("/api/auth/login", json={"username": "admin", "password": "admin-password"}).json()["access_token"]
        response = client.get("/api/users/admin", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["uid"] == "admin"
    finally:
        app.dependency_overrides.clear()


def test_refresh_endpoint_issues_new_tokens_and_rotates():
    hasher = PasswordHasher()
    unit_of_work = InMemoryUnitOfWork(users=[User(
        "admin", "Admin", "admin@example.com", "Admin", "d1",
        username="admin", password_representation=hasher.hash("admin-password"),
    )])
    service = AuthenticationServiceImpl(lambda: unit_of_work, hasher, "a" * 32)
    app.dependency_overrides[get_authentication_service] = lambda: service
    app.dependency_overrides[get_user_management_service] = lambda: UserManagementService(lambda: unit_of_work, hasher)
    client = TestClient(app)

    try:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "admin-password"}).json()
        refresh_token = login["refresh_token"]
        assert refresh_token

        refreshed = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert refreshed.status_code == 200
        assert refreshed.json()["token_type"] == "bearer"
        assert refreshed.json()["uid"] == "admin"
        assert refreshed.json()["access_token"]
        assert refreshed.json()["refresh_token"] != refresh_token

        protected = client.get(
            "/api/users/admin",
            headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
        )
        assert protected.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_refresh_token_cannot_authenticate_api_calls():
    hasher = PasswordHasher()
    unit_of_work = InMemoryUnitOfWork(users=[User(
        "admin", "Admin", "admin@example.com", "Admin", "d1",
        username="admin", password_representation=hasher.hash("admin-password"),
    )])
    service = AuthenticationServiceImpl(lambda: unit_of_work, hasher, "a" * 32)
    app.dependency_overrides[get_authentication_service] = lambda: service
    app.dependency_overrides[get_user_management_service] = lambda: UserManagementService(lambda: unit_of_work, hasher)
    client = TestClient(app)

    try:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "admin-password"}).json()
        response = client.get("/api/users/admin", headers={"Authorization": f"Bearer {login['refresh_token']}"})
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_refresh_with_invalid_token_returns_401():
    hasher = PasswordHasher()
    service = AuthenticationServiceImpl(
        lambda: InMemoryUnitOfWork(users=[User(
            "admin", "Admin", "admin@example.com", "Admin", "d1",
            username="admin", password_representation=hasher.hash("correct-password"),
        )]),
        hasher,
        "a" * 32,
    )
    app.dependency_overrides[get_authentication_service] = lambda: service
    client = TestClient(app)
    try:
        response = client.post("/api/auth/refresh", json={"refresh_token": "not-a-real-token"})
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()