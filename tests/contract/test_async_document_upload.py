import base64
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_principal, get_document_management_service
from app.domain.entities.organization_models import User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app
from app.use_cases.organization.document_management import DocumentManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_async_document_upload_lifecycle_transitions_to_active():
    unit_of_work = InMemoryUnitOfWork(users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")])
    ingested = []

    def mock_ingestion(source_path, doc, content):
        ingested.append(doc.document_id)
        return 1

    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_document_management_service] = (
        lambda: DocumentManagementService(lambda: unit_of_work, ingestion_handler=mock_ingestion)
    )
    client = TestClient(app)

    try:
        content_b64 = base64.b64encode(b"Sample policy digital text content").decode("utf-8")
        payload = {
            "document_id": "async-doc-1",
            "document_name": "Policy.txt",
            "content": content_b64,
            "async_mode": True,
        }
        response = client.post("/api/documents", json=payload)
        assert response.status_code == 201

        # TestClient executes background tasks before returning
        assert "async-doc-1" in ingested

        # Document is retrieved and status is active
        get_res = client.get("/api/documents/async-doc-1")
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["document_id"] == "async-doc-1"
        assert data["status"] == "active"
    finally:
        app.dependency_overrides.clear()


def test_async_document_upload_failure_transitions_to_failed():
    unit_of_work = InMemoryUnitOfWork(users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")])

    def failing_ingestion(source_path, doc, content):
        raise RuntimeError("VLM/Chroma error simulation")

    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_document_management_service] = (
        lambda: DocumentManagementService(lambda: unit_of_work, ingestion_handler=failing_ingestion)
    )
    client = TestClient(app)

    try:
        content_b64 = base64.b64encode(b"Some text").decode("utf-8")
        payload = {
            "document_id": "fail-doc-1",
            "document_name": "Report.txt",
            "content": content_b64,
            "async_mode": True,
        }
        response = client.post("/api/documents", json=payload)
        assert response.status_code == 201

        # Check document status after background failure
        get_res = client.get("/api/documents/fail-doc-1")
        assert get_res.status_code == 200
        assert get_res.json()["status"] == "failed"
    finally:
        app.dependency_overrides.clear()
