from fastapi.testclient import TestClient

from app.api.dependencies import get_current_principal, get_unit_of_work, get_user_management_service
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app
from app.use_cases.organization.user_management import UserManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_admin_can_create_and_read_user():
    unit_of_work = InMemoryUnitOfWork()
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_unit_of_work] = lambda: unit_of_work
    app.dependency_overrides[get_user_management_service] = lambda: UserManagementService(lambda: unit_of_work)
    client = TestClient(app)

    try:
        department = client.post(
            "/api/departments",
            json={"department_id": "d1", "department_name": "Engineering"},
        )
        assert department.status_code == 201

        created = client.post(
            "/api/users",
            json={
                "uid": "u1",
                "name": "Asha Rao",
                "email": "asha@example.com",
                "role": "Solution Architect",
                "department_id": "d1",
            },
        )
        assert created.status_code == 201
        assert created.json()["role"] == "Solution Architect"

        fetched = client.get("/api/users/u1")
        assert fetched.status_code == 200
        assert fetched.json()["uid"] == "u1"
    finally:
        app.dependency_overrides.clear()
