import base64

from fastapi.testclient import TestClient

import app.infrastructure.ingestion.provisioner as provisioner
from app.api.dependencies import get_current_principal, get_document_management_service
from app.domain.entities.organization_models import User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.infrastructure.ingestion.provisioner import provision_document
from app.main import app
from app.use_cases.organization.document_management import DocumentManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_upload_with_invalid_base64_is_rejected_without_persistence(tmp_path, monkeypatch):
    documents_dir = tmp_path / "input"
    documents_dir.mkdir()
    monkeypatch.setattr(provisioner, "DOCUMENTS_DIR", str(documents_dir))
    monkeypatch.setattr(provisioner, "COLLECTION_NAME", "test_invalid_collection")

    unit_of_work = InMemoryUnitOfWork(users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")])
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_document_management_service] = (
        lambda: DocumentManagementService(lambda: unit_of_work, ingestion_handler=provision_document)
    )
    client = TestClient(app)

    try:
        response = client.post(
            "/api/documents",
            json={"document_id": "bad-1", "document_name": "Notes.txt", "content": "not-base64-!!!"},
        )
        assert response.status_code == 400
        assert "base64" in response.json()["detail"]
        assert unit_of_work.documents.get("bad-1") is None
    finally:
        app.dependency_overrides.clear()


def test_upload_with_unsupported_file_type_is_rejected_without_persistence(tmp_path, monkeypatch):
    documents_dir = tmp_path / "input"
    documents_dir.mkdir()
    monkeypatch.setattr(provisioner, "DOCUMENTS_DIR", str(documents_dir))
    monkeypatch.setattr(provisioner, "COLLECTION_NAME", "test_invalid_collection")

    unit_of_work = InMemoryUnitOfWork(users=[User("admin", "Admin", "admin@example.com", "Admin", "d1")])
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    app.dependency_overrides[get_document_management_service] = (
        lambda: DocumentManagementService(lambda: unit_of_work, ingestion_handler=provision_document)
    )
    client = TestClient(app)

    try:
        payload = {
            "document_id": "bad-2",
            "document_name": "policy.exe",
            "content": base64.b64encode(b"\xff\xfe\x00\x01").decode("utf-8"),
        }
        response = client.post("/api/documents", json=payload)
        assert response.status_code == 400
        assert "Unsupported document type" in response.json()["detail"]
        assert unit_of_work.documents.get("bad-2") is None
    finally:
        app.dependency_overrides.clear()