from fastapi.testclient import TestClient

from app.api.dependencies import get_current_principal, get_document_management_service
from app.domain.entities.organization_models import Department, Project, User, UserProject
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app
from app.use_cases.organization.document_management import DocumentManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_project_documents_api_uses_path_project_id_and_autogenerates_id():
    unit_of_work = InMemoryUnitOfWork(
        users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")],
        departments=[Department("d1", "Engineering")],
        projects=[Project("p1", "Project One", "d1")],
    )
    captured = {}

    def handler(source_path, document, content):
        captured["project_id"] = document.project_id
        captured["document_id"] = document.document_id
        return 1

    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_document_management_service] = (
        lambda: DocumentManagementService(lambda: unit_of_work, handler)
    )
    client = TestClient(app)

    try:
        created = client.post("/api/projects/p1/documents", json={"document_name": "Runbook.txt", "content": "aGVsbG8="})
        assert created.status_code == 201
        body = created.json()
        assert body["project_id"] == "p1"
        assert body["document_id"] == "DOC-001"
        assert body["status"] == "active"
        assert captured["project_id"] == "p1"

        listed = client.get("/api/projects/p1/documents")
        assert listed.status_code == 200
        assert [item["document_id"] for item in listed.json()] == ["DOC-001"]
    finally:
        app.dependency_overrides.clear()


def test_project_documents_api_ignores_project_id_in_body():
    unit_of_work = InMemoryUnitOfWork(
        users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")],
        departments=[Department("d1", "Engineering"), Department("d2", "Finance")],
        projects=[Project("p1", "Project One", "d1")],
    )
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_document_management_service] = (
        lambda: DocumentManagementService(lambda: unit_of_work)
    )
    client = TestClient(app)

    try:
        created = client.post(
            "/api/projects/p1/documents",
            json={"document_name": "Runbook.txt", "project_id": "p-other"},
        )
        assert created.status_code == 201
        assert created.json()["project_id"] == "p1"
    finally:
        app.dependency_overrides.clear()


def test_project_documents_api_rejects_unauthorized_upload():
    unit_of_work = InMemoryUnitOfWork(
        users=[User("dev", "Dev", "dev@example.com", "Developer", "d1")],
        departments=[Department("d1", "Engineering")],
        projects=[Project("p1", "Project One", "d1")],
    )
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("dev")
    app.dependency_overrides[get_document_management_service] = (
        lambda: DocumentManagementService(lambda: unit_of_work)
    )
    client = TestClient(app)

    try:
        created = client.post("/api/projects/p1/documents", json={"document_name": "Sneaky.txt"})
        assert created.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_project_documents_api_limits_listing_to_viewers():
    unit_of_work = InMemoryUnitOfWork(
        users=[User("admin", "Admin", "admin@example.com", "Admin", "d1"), User("dev", "Dev", "dev@example.com", "Developer", "d1")],
        departments=[Department("d1", "Engineering")],
        projects=[Project("p1", "Project One", "d1")],
    )
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_document_management_service] = (
        lambda: DocumentManagementService(lambda: unit_of_work)
    )
    client = TestClient(app)

    try:
        assert client.post("/api/projects/p1/documents", json={"document_name": "Runbook.txt"}).status_code == 201

        app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("dev")
        denied = client.get("/api/projects/p1/documents")
        assert denied.status_code == 403

        unit_of_work.memberships.save(UserProject("dev", "p1"))
        allowed = client.get("/api/projects/p1/documents")
        assert allowed.status_code == 200
        assert [item["document_id"] for item in allowed.json()] == ["DOC-001"]
    finally:
        app.dependency_overrides.clear()