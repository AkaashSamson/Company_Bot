import base64
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_principal, get_document_management_service
from app.domain.entities.organization_models import User, Project
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.main import app
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.use_cases.organization.document_management import DocumentManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


class MockEmbeddingModel:
    def encode(self, texts, convert_to_numpy=True):
        class Dummy:
            def tolist(self):
                if isinstance(texts, list):
                    return [[0.1, 0.2, 0.3] for _ in texts]
                return [0.1, 0.2, 0.3]
        return Dummy()


@pytest.fixture
def test_setup(tmp_path):
    chroma_dir = str(tmp_path / ".chroma")
    store = ChromaVectorStore(collection_name="test_async_col", persist_directory=chroma_dir)
    store.embedding_model = MockEmbeddingModel()
    
    uow = InMemoryUnitOfWork(
        users=[
            User("admin", "Admin", "admin@example.com", "Admin", "d1"),
            User("lead", "Project Lead", "lead@example.com", "Manager", "d1"),
        ],
        projects=[
            Project("PRJ-TEST", "Test Project", "d1", manager_uid="lead"),
            Project("PRJ-ARCHIVE", "Archive Project", "d1", manager_uid="lead"),
            Project("PRJ-PURGE", "Purge Project", "d1", manager_uid="lead"),
        ]
    )
    
    app.dependency_overrides[get_current_principal] = lambda: AuthenticatedPrincipal("admin")
    service = DocumentManagementService(
        lambda: uow,
        ingestion_handler=lambda src, doc, content: store.add_documents([
            {"id": f"{doc.document_id}-0", "text": "Test chunk content for document", "metadata": {"document_id": doc.document_id, "project_id": doc.project_id, "status": "active"}}
        ]),
        deletion_handler=lambda doc_id: store.collection.delete(where={"document_id": doc_id})
    )
    app.dependency_overrides[get_document_management_service] = lambda: service
    client = TestClient(app)
    
    yield client, uow, store
    app.dependency_overrides.clear()


def test_async_document_upload_and_status_polling(test_setup):
    client, uow, store = test_setup
    content = base64.b64encode(b"Policy content for background ingestion.").decode("utf-8")
    payload = {
        "document_name": "Policy.txt",
        "project_id": "PRJ-TEST",
        "content": content,
    }

    res = client.post("/api/documents", json=payload)
    assert res.status_code in (201, 202)
    doc_id = res.json()["document_id"]
    assert res.json()["status"] in ("processing", "active")

    # Poll status endpoint
    status_resp = client.get(f"/api/documents/{doc_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["document_id"] == doc_id
    assert status_data["status"] in ("processing", "active")


def test_duplicate_file_hash_in_same_project_rejected(test_setup):
    client, uow, store = test_setup
    content = base64.b64encode(b"Exact duplicate content test.").decode("utf-8")
    payload = {"document_name": "doc1.txt", "project_id": "PRJ-TEST", "content": content}

    res1 = client.post("/api/documents", json=payload)
    assert res1.status_code in (201, 202)

    # Re-upload same content to same project
    payload2 = {"document_name": "doc2.txt", "project_id": "PRJ-TEST", "content": content}
    res2 = client.post("/api/documents", json=payload2)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"].lower()


def test_get_document_chunks_and_vector_search(test_setup):
    client, uow, store = test_setup
    content = base64.b64encode(b"Security guidelines content.").decode("utf-8")
    payload = {"document_name": "sec.txt", "project_id": "PRJ-TEST", "content": content}
    res = client.post("/api/documents", json=payload)
    doc_id = res.json()["document_id"]

    # 1. Chunk inspection
    chunks_resp = client.get(f"/api/documents/{doc_id}/chunks")
    assert chunks_resp.status_code == 200
    chunks = chunks_resp.json()
    assert isinstance(chunks, list)
    assert len(chunks) > 0
    assert chunks[0]["metadata"]["document_id"] == doc_id

    # 2. Vector search endpoint
    search_payload = {"query": "security guidelines", "project_id": "PRJ-TEST", "top_k": 2}
    search_resp = client.post("/api/documents/chunks/search", json=search_payload)
    assert search_resp.status_code == 200
    assert isinstance(search_resp.json(), list)


def test_archive_document_preserves_chunks_and_moves_file(test_setup, tmp_path):
    client, uow, store = test_setup
    content = base64.b64encode(b"Archive me.").decode("utf-8")
    payload = {"document_name": "archive_me.txt", "project_id": "PRJ-ARCHIVE", "content": content}
    res = client.post("/api/documents", json=payload)
    doc_id = res.json()["document_id"]

    # Soft delete (archive)
    del_resp = client.delete(f"/api/documents/{doc_id}")
    assert del_resp.status_code == 204
    assert uow.documents.get(doc_id).status == "archived"

    # Chunks are preserved in Chroma
    chunks_resp = client.get(f"/api/documents/{doc_id}/chunks")
    assert chunks_resp.status_code == 200
    assert len(chunks_resp.json()) > 0


def test_permanent_delete_purges_chunks(test_setup):
    client, uow, store = test_setup
    content = base64.b64encode(b"Purge me.").decode("utf-8")
    payload = {"document_name": "purge_me.txt", "project_id": "PRJ-PURGE", "content": content}
    res = client.post("/api/documents", json=payload)
    doc_id = res.json()["document_id"]

    # Permanent delete
    del_resp = client.delete(f"/api/documents/{doc_id}?permanent=true")
    assert del_resp.status_code == 204

    # Chunks purged from Chroma
    chunks_resp = client.get(f"/api/documents/{doc_id}/chunks")
    assert chunks_resp.status_code == 200
    assert len(chunks_resp.json()) == 0


def test_archive_document_listing_toggle_and_restore(test_setup):
    client, uow, store = test_setup
    content = base64.b64encode(b"Toggle me.").decode("utf-8")
    payload = {"document_name": "toggle_me.txt", "project_id": "PRJ-ARCHIVE", "content": content}
    res = client.post("/api/documents", json=payload)
    doc_id = res.json()["document_id"]

    # Initially active
    list_res = client.get("/api/documents")
    assert any(d["document_id"] == doc_id for d in list_res.json())

    # Archive document
    client.delete(f"/api/documents/{doc_id}")

    # Excluded by default
    list_default = client.get("/api/documents")
    assert not any(d["document_id"] == doc_id for d in list_default.json())

    # Included when include_archived=true
    list_archived = client.get("/api/documents?include_archived=true")
    assert any(d["document_id"] == doc_id and d["status"] == "archived" for d in list_archived.json())

    # Restore document
    restore_res = client.post(f"/api/documents/{doc_id}/restore")
    assert restore_res.status_code == 200
    assert restore_res.json()["status"] == "active"

    # Visible again in default list
    list_after_restore = client.get("/api/documents")
    assert any(d["document_id"] == doc_id and d["status"] == "active" for d in list_after_restore.json())
