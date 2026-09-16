"""End-to-end verification that the document metadata (document id, project id,
source, file type, version, section) is stored in the Chroma vector store.
"""
import base64

import app.infrastructure.ingestion.provisioner as provisioner
from app.domain.entities.organization_models import Document
from app.infrastructure.ingestion.provisioner import provision_document
from app.infrastructure.vector.chroma_client import ChromaVectorStore


def test_chroma_stores_document_and_project_metadata(tmp_path, monkeypatch):
    documents_dir = tmp_path / "input"
    documents_dir.mkdir()
    monkeypatch.setattr(provisioner, "DOCUMENTS_DIR", str(documents_dir))
    monkeypatch.setattr(provisioner, "COLLECTION_NAME", "test_meta_collection")

    store = ChromaVectorStore(
        collection_name="test_meta_collection",
        persist_directory=str(tmp_path / "chroma"),
    )

    document = Document("m-doc-1", "Onboarding.txt", project_id="p1", version="2.1")
    content = base64.b64encode(b"All new employees complete onboarding within 30 days.").decode("utf-8")

    chunk_count = provision_document(None, document, content, store=store)

    assert chunk_count > 0
    assert document.file_type == "txt"
    assert document.original_filename == "Onboarding.txt"
    assert document.storage_location is not None
    assert document.storage_location.endswith("m-doc-1.txt")

    stored = store.collection.get(where={"document_id": "m-doc-1"}, include=["metadatas"])
    metadatas = stored.get("metadatas", [])
    assert metadatas, "document metadata must be present in the vector store"

    metadata = metadatas[0]
    assert metadata["document_id"] == "m-doc-1"
    assert metadata["project_id"] == "p1"
    assert metadata["source"] == "Onboarding.txt"
    assert metadata["file_type"] == "txt"
    assert metadata["version"] == "2.1"
    assert metadata["section"] == "Policy"


def test_chroma_metadata_defaults_for_unassigned_document(tmp_path, monkeypatch):
    documents_dir = tmp_path / "input"
    documents_dir.mkdir()
    monkeypatch.setattr(provisioner, "DOCUMENTS_DIR", str(documents_dir))
    monkeypatch.setattr(provisioner, "COLLECTION_NAME", "test_meta_collection_defaults")

    store = ChromaVectorStore(
        collection_name="test_meta_collection_defaults",
        persist_directory=str(tmp_path / "chroma-defaults"),
    )

    document = Document("org-doc-9", "Sick Leave Policy", project_id=None)
    content = base64.b64encode(b"Employees get 10 sick leave days per year.").decode("utf-8")

    provision_document(None, document, content, store=store)

    stored = store.collection.get(where={"document_id": "org-doc-9"}, include=["metadatas"])
    metadata = stored["metadatas"][0]
    assert metadata["project_id"] == "unassigned"
    assert metadata["file_type"] == "txt"
    assert metadata["version"] == "1.0"