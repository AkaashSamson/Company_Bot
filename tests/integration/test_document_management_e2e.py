from fastapi.testclient import TestClient

from app.api.dependencies import get_current_principal, get_document_management_service
from app.domain.entities.organization_models import Department, Project, User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app
from app.use_cases.organization.document_management import DocumentManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_document_project_assignment_and_archive_preserve_project_data():
    unit_of_work = InMemoryUnitOfWork(
        users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")],
        departments=[Department("d1", "Engineering")],
        projects=[Project("p1", "Project One", "d1")],
    )
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_document_management_service] = lambda: DocumentManagementService(lambda: unit_of_work)
    client = TestClient(app)

    try:
        created = client.post(
            "/api/documents",
            json={"document_id": "doc-1", "document_name": "Runbook", "project_id": "p1"},
        )
        assert created.status_code == 201
        assert created.json()["project_id"] == "p1"

        archived = client.delete("/api/documents/doc-1")
        assert archived.status_code == 204
        assert unit_of_work.projects.get("p1").status == "active"
        assert unit_of_work.documents.get("doc-1").status == "archived"
    finally:
        app.dependency_overrides.clear()
