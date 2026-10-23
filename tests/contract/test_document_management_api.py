from fastapi.testclient import TestClient

from app.api.dependencies import get_current_principal, get_document_management_service
from app.domain.entities.organization_models import User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app
from app.use_cases.organization.document_management import DocumentManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_document_upload_content_is_forwarded_to_provisioning_handler():
    unit_of_work = InMemoryUnitOfWork(users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")])
    captured = {}

    def handler(source_path, document, content):
        captured["source_path"] = source_path
        captured["document_id"] = document.document_id
        captured["content"] = content
        return 1

    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_document_management_service] = (
        lambda: DocumentManagementService(lambda: unit_of_work, handler)
    )
    client = TestClient(app)

    try:
        payload = {"document_id": "doc-2", "document_name": "Notes.txt", "content": "aGVsbG8gd29ybGQ="}
        created = client.post("/api/documents", json=payload)
        assert created.status_code in (201, 202)
        assert captured["content"] == "aGVsbG8gd29ybGQ="
        assert captured["document_id"] == "doc-2"
        assert captured["source_path"] is None
        assert unit_of_work.documents.get("doc-2") is not None
    finally:
        app.dependency_overrides.clear()


def test_document_upload_with_invalid_content_returns_bad_request():
    unit_of_work = InMemoryUnitOfWork(users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")])

    def handler(source_path, document, content):
        if not content or not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in content):
            raise ValueError("Document content is not valid base64")
        return 0

    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_document_management_service] = (
        lambda: DocumentManagementService(lambda: unit_of_work, handler)
    )
    client = TestClient(app)

    try:
        payload = {"document_id": "doc-3", "document_name": "Notes.txt", "content": "not-base64-!!!"}
        created = client.post("/api/documents", json=payload)
        assert created.status_code == 400
        assert "base64" in created.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_document_api_registers_lists_and_archives_documents():
    unit_of_work = InMemoryUnitOfWork(users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")])
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_document_management_service] = lambda: DocumentManagementService(lambda: unit_of_work)
    client = TestClient(app)

    try:
        created = client.post("/api/documents", json={"document_id": "doc-1", "document_name": "Handbook"})
        assert created.status_code in (201, 202)
        assert created.json()["project_id"] is None

        listed = client.get("/api/documents")
        assert listed.status_code == 200
        assert listed.json()[0]["document_id"] == "doc-1"

        deleted = client.delete("/api/documents/doc-1")
        assert deleted.status_code == 204
        assert unit_of_work.documents.get("doc-1").status == "archived"
    finally:
        app.dependency_overrides.clear()