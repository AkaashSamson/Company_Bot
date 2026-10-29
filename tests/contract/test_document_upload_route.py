import io
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_current_principal,
    get_current_user,
    get_document_ingestion_use_case,
)
from app.domain.entities.document_models import DocumentChunk
from app.domain.entities.organization_models import Employee
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app


def test_upload_document_endpoint_success():
    mock_use_case = MagicMock()
    mock_use_case.process_and_index_document.return_value = [
        DocumentChunk(chunk_id="DOC-123_0", document_id="DOC-TEST", text="Sample text")
    ]

    mock_user = Employee(
        uid="emp_1",
        name="Test Employee",
        email="emp@example.com",
        role="Admin",
        department_id="HR",
    )

    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("emp_1")
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_document_ingestion_use_case] = lambda: mock_use_case

    client = TestClient(app)

    try:
        file_content = b"# HR Policy\nEmployees are entitled to 20 days vacation."
        response = client.post(
            "/api/documents/upload",
            files={"file": ("policy.txt", io.BytesIO(file_content), "text/plain")},
            data={"project_id": "PROJ-HR"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "success"
        assert data["filename"] == "policy.txt"
        assert data["total_chunks_indexed"] == 1
        assert mock_use_case.process_and_index_document.called

        # Also verify /documents/upload alias
        response_alias = client.post(
            "/documents/upload",
            files={"file": ("policy.txt", io.BytesIO(file_content), "text/plain")},
            data={"project_id": "PROJ-HR"},
        )
        assert response_alias.status_code == 200, response_alias.text
    finally:
        app.dependency_overrides.clear()


def test_upload_document_endpoint_forbidden_rbac():
    mock_user = MagicMock(spec=Employee)
    mock_user.can_upload_to_project.return_value = False

    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("emp_blocked")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    client = TestClient(app)

    try:
        response = client.post(
            "/api/documents/upload",
            files={"file": ("policy.txt", io.BytesIO(b"content"), "text/plain")},
            data={"project_id": "PROJ-RESTRICTED"},
        )
        assert response.status_code == 403
        assert "User does not have upload access" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()

