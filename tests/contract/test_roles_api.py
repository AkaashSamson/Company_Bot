from fastapi.testclient import TestClient

from app.api.dependencies import get_current_principal, get_role_management_service
from app.domain.entities.organization_models import Department, User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_service import OrganizationAuthorizationService
from app.infrastructure.persistence.rbac_seed import seed_rbac
from app.main import app
from app.use_cases.organization.role_management import RoleManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def build(actor="admin"):
    unit_of_work = InMemoryUnitOfWork(
        users=[
            User("admin", "Admin", "admin@example.com", "Admin", "d1"),
            User("mgr", "Manager", "mgr@example.com", "Manager", "d1"),
            User("dev", "Dev", "dev@example.com", "Developer", "d1"),
        ],
        departments=[Department("d1", "Engineering"), Department("d2", "QA")],
    )
    seed_rbac(lambda: unit_of_work)
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal(actor)
    app.dependency_overrides[get_role_management_service] = lambda: RoleManagementService(
        lambda: unit_of_work, OrganizationAuthorizationService(unit_of_work)
    )
    return unit_of_work


def _permission_ids(client, *names):
    catalog = {item["name"]: item["permission_id"] for item in client.get("/api/permissions").json()}
    return [catalog[name] for name in names]


def test_permission_catalog_and_initial_roles_are_exposed():
    build()
    client = TestClient(app)
    try:
        permissions = client.get("/api/permissions")
        assert permissions.status_code == 200
        assert len(permissions.json()) == 25

        roles = client.get("/api/roles")
        assert roles.status_code == 200
        names = {role["name"] for role in roles.json()}
        assert {"Admin", "Manager", "Developer", "Tester", "Solution Architect"} <= names
    finally:
        app.dependency_overrides.clear()


def test_admin_creates_role_and_reads_permission_checkboxes():
    build()
    client = TestClient(app)
    try:
        permission_ids = _permission_ids(client, "USER_VIEW", "USER_CREATE")
        created = client.post("/api/roles", json={
            "name": "Release Manager",
            "description": "Manages releases",
            "scope": "global",
            "permission_ids": permission_ids,
        })
        assert created.status_code == 201
        role_id = created.json()["role_id"]
        assert created.json()["created_by_uid"] == "admin"

        permissions = client.get(f"/api/roles/{role_id}/permissions")
        assert permissions.status_code == 200
        assert set(permissions.json()["permission_ids"]) == set(permission_ids)
        assert {item["name"] for item in permissions.json()["permissions"]} == {"USER_VIEW", "USER_CREATE"}
    finally:
        app.dependency_overrides.clear()


def test_put_role_permissions_replaces_with_checkbox_semantics():
    build()
    client = TestClient(app)
    try:
        first = _permission_ids(client, "USER_VIEW", "USER_CREATE")
        role_id = client.post("/api/roles", json={"name": "Auditor", "scope": "global", "permission_ids": first}).json()["role_id"]
        second = _permission_ids(client, "USER_CREATE", "USER_DELETE")

        response = client.put(f"/api/roles/{role_id}/permissions", json={"permission_ids": second})

        assert response.status_code == 200
        assert set(response.json()["permission_ids"]) == set(second)
    finally:
        app.dependency_overrides.clear()


def test_duplicate_role_name_returns_conflict():
    build()
    client = TestClient(app)
    try:
        client.post("/api/roles", json={"name": "Auditor", "scope": "global"})
        response = client.post("/api/roles", json={"name": "Auditor", "scope": "global"})
        assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_invalid_scope_is_rejected_by_validation():
    build()
    client = TestClient(app)
    try:
        response = client.post("/api/roles", json={"name": "Bad", "scope": "team"})
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_manager_cannot_create_global_role_but_can_create_department_role():
    build(actor="mgr")
    client = TestClient(app)
    try:
        global_response = client.post("/api/roles", json={"name": "Global Auditor", "scope": "global"})
        assert global_response.status_code == 403

        department_response = client.post("/api/roles", json={
            "name": "Engineering Lead", "scope": "department", "department_id": "d1",
        })
        assert department_response.status_code == 201
        assert department_response.json()["department_id"] == "d1"

        other_department = client.post("/api/roles", json={
            "name": "QA Lead", "scope": "department", "department_id": "d2",
        })
        assert other_department.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_create_permission_validation_and_conflict():
    build()
    client = TestClient(app)
    try:
        created = client.post("/api/permissions", json={"name": "REPORT_EXPORT", "description": "Export reports"})
        assert created.status_code == 201
        assert created.json()["name"] == "REPORT_EXPORT"

        duplicate = client.post("/api/permissions", json={"name": "REPORT_EXPORT"})
        assert duplicate.status_code == 409

        invalid = client.post("/api/permissions", json={"name": "lowercase"})
        assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_delete_role_and_missing_role_returns_not_found():
    build()
    client = TestClient(app)
    try:
        role_id = client.post("/api/roles", json={"name": "Auditor", "scope": "global"}).json()["role_id"]

        assert client.delete(f"/api/roles/{role_id}").status_code == 204
        assert client.get(f"/api/roles/{role_id}").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_delete_assigned_role_returns_conflict():
    build()
    client = TestClient(app)
    try:
        roles = client.get("/api/roles").json()
        developer = next(role for role in roles if role["name"] == "Developer")
        # "Developer" is already assigned to uid "dev" from the fixture context
        response = client.delete(f"/api/roles/{developer['role_id']}")
        assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_user_permissions_and_roles_endpoints():
    build()
    client = TestClient(app)
    try:
        permissions = client.get("/api/users/dev/permissions")
        assert permissions.status_code == 200
        assert permissions.json()["uid"] == "dev"
        assert "DOCUMENT_VIEW" in permissions.json()["permissions"]
        assert "USER_CREATE" not in permissions.json()["permissions"]

        roles = client.get("/api/users/dev/roles")
        assert roles.status_code == 200
        assert "Developer" in {role["name"] for role in roles.json()}
    finally:
        app.dependency_overrides.clear()


def test_developer_cannot_view_role_catalog_without_permission():
    build(actor="dev")
    client = TestClient(app)
    try:
        response = client.get("/api/roles")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
