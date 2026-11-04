"""End-to-end verification that an uploaded document flows through the real
extraction, chunking, embedding, vector-storage, and project-scoped retrieval
steps of the existing document pipeline.
"""
import base64

import app.infrastructure.ingestion.provisioner as provisioner
from app.domain.entities.organization_models import Document
from app.infrastructure.ingestion.provisioner import provision_document
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.use_cases.chat.provenance_service import ProvenanceService
from app.use_cases.chat.retrieval_service import RetrievalService


def test_uploaded_document_is_provisioned_and_retrievable_within_project_scope(tmp_path, monkeypatch):
    documents_dir = tmp_path / "input"
    documents_dir.mkdir()
    monkeypatch.setattr(provisioner, "DOCUMENTS_DIR", str(documents_dir))
    monkeypatch.setattr(provisioner, "COLLECTION_NAME", "test_upload_collection")

    store = ChromaVectorStore(
        collection_name="test_upload_collection",
        persist_directory=str(tmp_path / "chroma"),
    )

    document = Document("upload-001", "Cloud Budget Policy.txt", project_id="p1")
    content = base64.b64encode(
        b"The company allocates an annual cloud budget of 50000 units. "
        b"Budget approval is required before any new cloud spending. "
        b"The allocation covers all production cloud services."
    ).decode("utf-8")

    chunk_count = provision_document(None, document, content, store=store)

    assert chunk_count > 0
    assert store.collection.count() == chunk_count
    assert (tmp_path / "input" / "upload-001.txt").exists()

    results = store.query("What is the annual cloud budget?", top_k=3, project_ids=["p1"])
    assert results, "Uploaded document must be retrievable under the authorized project scope"
    assert any("50000" in result["text"] for result in results)

    selected = RetrievalService.select_relevant("What is the annual cloud budget?", results)
    assert any("50000" in item["text"] for item in selected)

    citations = ProvenanceService().build_citations(results)
    assert citations[0]["source"] == "Cloud Budget Policy.txt"

    restricted = store.query("What is the annual cloud budget?", top_k=3, project_ids=["p-other"])
    assert restricted == [], "Document must not be retrievable outside the authorized project scope"


def test_unassigned_upload_without_name_extension_is_provisioned_via_byte_sniffing(tmp_path, monkeypatch):
    documents_dir = tmp_path / "input"
    documents_dir.mkdir()
    monkeypatch.setattr(provisioner, "DOCUMENTS_DIR", str(documents_dir))

    store = ChromaVectorStore(
        collection_name="test_upload_collection",
        persist_directory=str(tmp_path / "chroma-org"),
    )

    document = Document("org-doc-1", "Sick Leave Policy", project_id=None)
    content = base64.b64encode(
        b"All employees are entitled to 10 sick leave days per calendar year. "
        b"Sick leave days must be reported to the manager the same day."
    ).decode("utf-8")

    chunk_count = provision_document(None, document, content, store=store)

    assert chunk_count > 0
    assert (tmp_path / "input" / "org-doc-1.txt").exists()
    assert store.collection.count() == chunk_count

    results = store.query("How many sick leave days?", top_k=3, project_ids=["unassigned"])
    assert results, "Unassigned documents must be stored with org-wide metadata"
    assert any("10" in result["text"] for result in results)