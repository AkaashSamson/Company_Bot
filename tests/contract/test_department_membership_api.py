from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_current_principal,
    get_department_membership_service,
    get_user_management_service,
)
from app.domain.entities.organization_models import Department, User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app
from app.use_cases.organization.department_membership import DepartmentMembershipService
from app.use_cases.organization.user_management import UserManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def build_overrides(users=None, departments=None, department_members=None):
    unit_of_work = InMemoryUnitOfWork(users=users, departments=departments, department_members=department_members)
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_user_management_service] = lambda: UserManagementService(lambda: unit_of_work)
    app.dependency_overrides[get_department_membership_service] = lambda: DepartmentMembershipService(lambda: unit_of_work)
    return unit_of_work


def test_admin_can_assign_list_and_patch_department_membership():
    build_overrides(
        users=[
            User("admin", "Admin", "admin@example.com", "Admin", "d1"),
            User("u1", "User One", "u1@example.com", "Developer", "d1"),
        ],
        departments=[Department("d1", "Engineering")],
    )
    client = TestClient(app)
    try:
        assigned = client.post("/api/departments/d1/members", json={"user_id": "u1", "billable_status": "non-billable"})
        assert assigned.status_code == 201
        assert assigned.json()["billable_status"] == "non-billable"

        members = client.get("/api/departments/d1/members")
        assert members.status_code == 200
        assert len(members.json()) == 1

        updated = client.patch("/api/departments/d1/members/u1", json={"billable_status": "billable"})
        assert updated.status_code == 200
        assert updated.json()["billable_status"] == "billable"

        listing = client.get("/api/users/u1/memberships")
        assert listing.status_code == 200
        assert len(listing.json()) == 1
    finally:
        app.dependency_overrides.clear()


def test_leave_department_sets_inactive_status():
    build_overrides(
        users=[
            User("admin", "Admin", "admin@example.com", "Admin", "d1"),
            User("u1", "User One", "u1@example.com", "Developer", "d1"),
        ],
        departments=[Department("d1", "Engineering")],
    )
    client = TestClient(app)
    try:
        assert client.post("/api/departments/d1/members", json={"user_id": "u1"}).status_code == 201
        response = client.delete("/api/departments/d1/members/u1")
        assert response.status_code == 204

        members = client.get("/api/departments/d1/members").json()
        assert members[0]["status"] == "inactive"
        assert members[0]["left_at"] is not None
        assert members[0]["billable_status"] is None
    finally:
        app.dependency_overrides.clear()


def test_department_update_preserves_member_billable_override():
    build_overrides(
        users=[
            User("admin", "Admin", "admin@example.com", "Admin", "d1"),
            User("u1", "User One", "u1@example.com", "Developer", "d1"),
        ],
        departments=[Department("d1", "Engineering", default_billable="billable")],
    )
    client = TestClient(app)
    try:
        assert client.post("/api/departments/d1/members", json={"user_id": "u1", "billable_status": "billable"}).status_code == 201

        changed = client.patch("/api/departments/d1", json={"default_billable": "non-billable"})
        assert changed.status_code == 200
        assert changed.json()["default_billable"] == "non-billable"

        members = client.get("/api/departments/d1/members").json()
        assert members[0]["billable_status"] == "billable"
    finally:
        app.dependency_overrides.clear()


def test_user_create_exposes_employee_id_and_names():
    build_overrides(
        users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")],
        departments=[Department("d1", "Engineering")],
    )
    client = TestClient(app)
    try:
        created = client.post(
            "/api/users",
            json={
                "uid": "u1",
                "name": "Asha Rao",
                "email": "asha@example.com",
                "role": "Developer",
                "department_id": "d1",
                "first_name": "Asha",
                "last_name": "Rao",
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["employee_id"] == "MSS-001"
        assert body["first_name"] == "Asha"
        assert body["last_name"] == "Rao"

        fetched = client.get("/api/users/u1").json()
        assert fetched["employee_id"] == "MSS-001"
    finally:
        app.dependency_overrides.clear()


def test_invalid_billable_policy_is_rejected_by_api():
    build_overrides(users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")])
    client = TestClient(app)
    try:
        response = client.post(
            "/api/departments",
            json={"department_id": "d2", "department_name": "QA", "default_billable": "maybe"},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()