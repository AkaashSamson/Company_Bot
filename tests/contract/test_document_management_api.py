from fastapi.testclient import TestClient

from app.api.dependencies import get_current_principal, get_document_management_service
from app.domain.entities.organization_models import User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app
from app.use_cases.organization.document_management import DocumentManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_document_api_registers_lists_and_archives_documents():
    unit_of_work = InMemoryUnitOfWork(users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")])
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_document_management_service] = lambda: DocumentManagementService(lambda: unit_of_work)
    client = TestClient(app)

    try:
        created = client.post("/api/documents", json={"document_id": "doc-1", "document_name": "Handbook"})
        assert created.status_code == 201
        assert created.json()["project_id"] is None

        listed = client.get("/api/documents")
        assert listed.status_code == 200
        assert listed.json()[0]["document_id"] == "doc-1"

        deleted = client.delete("/api/documents/doc-1")
        assert deleted.status_code == 204
        assert unit_of_work.documents.get("doc-1").status == "archived"
    finally:
        app.dependency_overrides.clear()