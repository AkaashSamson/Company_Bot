"""End-to-end test: RetrievalService enforces authorized_project_ids and
authorized_document_ids against a real Chroma vector store."""
import base64

import pytest

import app.infrastructure.ingestion.provisioner as provisioner
from app.domain.entities.organization_models import Document
from app.infrastructure.ingestion.provisioner import provision_document
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.use_cases.chat.retrieval_service import RetrievalService


def _doc_ids(results):
    return {r["metadata"].get("document_id") for r in results}


def _project_ids(results):
    return {r["metadata"].get("project_id") for r in results}


@pytest.fixture()
def chroma_store(tmp_path, monkeypatch):
    documents_dir = tmp_path / "input"
    documents_dir.mkdir()
    monkeypatch.setattr(provisioner, "DOCUMENTS_DIR", str(documents_dir))
    monkeypatch.setattr(provisioner, "COLLECTION_NAME", "test_scope_collection")

    store = ChromaVectorStore(
        collection_name="test_scope_collection",
        persist_directory=str(tmp_path / "chroma"),
    )

    doc1 = Document("doc1", "ProjectA_Policy.txt", project_id="p1", version="1.0")
    content1 = base64.b64encode(b"Project A policy: annual leave is ten days.").decode("utf-8")
    provision_document(None, doc1, content1, store=store)

    doc2 = Document("doc2", "ProjectB_Policy.txt", project_id="p2", version="1.0")
    content2 = base64.b64encode(b"Project B policy: annual leave is fifteen days.").decode("utf-8")
    provision_document(None, doc2, content2, store=store)

    doc3 = Document("doc3", "Global_Handbook.txt", project_id=None, version="1.0")
    content3 = base64.b64encode(b"Global handbook: sick leave is five days.").decode("utf-8")
    provision_document(None, doc3, content3, store=store)

    svc = RetrievalService.__new__(RetrievalService)
    svc.store = store
    return svc


def test_project_filter_retrieves_only_matching_docs(chroma_store):
    svc = chroma_store
    results = svc.retrieve(
        "What is the annual leave policy?",
        authorized_project_ids=["p1"],
        include_unassigned=False,
    )
    project_ids = _project_ids(results)
    assert "p1" in project_ids
    assert "p2" not in project_ids


def test_empty_project_ids_returns_nothing(chroma_store):
    svc = chroma_store
    results = svc.retrieve(
        "What is the annual leave policy?",
        authorized_project_ids=[],
        include_unassigned=False,
    )
    assert results == []


def test_document_id_filter(chroma_store):
    svc = chroma_store
    results = svc.retrieve(
        "What is the annual leave policy?",
        authorized_document_ids=["doc2"],
    )
    document_ids = _doc_ids(results)
    assert document_ids and document_ids == {"doc2"}


def test_document_ids_add_to_project_scope(chroma_store):
    svc = chroma_store
    results = svc.retrieve(
        "What is the annual leave policy?",
        authorized_project_ids=["p1"],
        authorized_document_ids=["doc2"],
        include_unassigned=False,
    )
    document_ids = _doc_ids(results)
    assert document_ids and "doc2" in document_ids