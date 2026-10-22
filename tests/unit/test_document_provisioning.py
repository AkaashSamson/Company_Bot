import base64

import pytest

from app.domain.entities.organization_models import Document
from app.domain.ports.document_processing import ProcessedChunk, ProcessedDocument
from app.infrastructure.ingestion.provisioner import provision_document, _safe_document_id
import app.infrastructure.ingestion.provisioner as provisioner


class _RecordingProcessor:
    def __init__(self, extension, text="Body"):
        self.extension = extension
        self.text = text
        self.seen = []

    def supported_extensions(self):
        return (self.extension,)

    def supports(self, file_name):
        return file_name.lower().endswith(self.extension)

    def process(self, content, file_name):
        self.seen.append(file_name)
        return ProcessedDocument(
            file_type=self.extension.lstrip("."),
            chunks=(ProcessedChunk(text=self.text, index=0),),
        )


class _RecordingStore:
    def __init__(self):
        self.records = []

    def add_documents(self, records):
        self.records.extend(records)


class _RecordingCollection:
    def __init__(self):
        self.where = None

    def delete(self, where):
        self.where = where

    def count(self):
        return 0


class _RecordingVectorStore:
    def __init__(self):
        self.collection = _RecordingCollection()


def test_safe_document_id_sanitizes_dangerous_characters():
    safe = _safe_document_id("My;DROP TABLE\nPolicy..")
    assert ".." not in safe
    assert "/" not in safe
    assert safe.replace("_", "").strip()


def test_safe_document_id_rejects_empty_result():
    with pytest.raises(ValueError):
        _safe_document_id("///...")

def test_provision_document_rejects_unsupported_extension_before_vector_store():
    document = Document("doc-1", "Report.pdf")
    content = base64.b64encode(b"\x89PNG\r\n\x1a\nbinary image payload\x00\xff").decode("utf-8")
    with pytest.raises(ValueError):
        provision_document(None, document, content)


def test_provision_document_rejects_invalid_base64():
    document = Document("doc-1", "Notes.txt")
    with pytest.raises(ValueError):
        provision_document(None, document, "not-base64-!!!")


def test_provision_document_without_source_or_content_is_noop():
    document = Document("doc-legend", "Notes.txt")
    assert provision_document(None, document, None) == 0


def test_named_upload_extension_is_preserved_for_port_routing(tmp_path, monkeypatch):
    monkeypatch.setattr(provisioner, "DOCUMENTS_DIR", str(tmp_path))
    processor = _RecordingProcessor(".csv")
    store = _RecordingStore()
    document = Document("doc-csv", "Policy.csv", project_id="project-1")
    content = base64.b64encode(b"header,value\npolicy,body").decode("utf-8")

    assert provision_document(None, document, content, store=store, processor=processor) == 1
    assert processor.seen == ["upload.csv"]
    assert store.records[0]["metadata"]["project_id"] == "project-1"


def test_remove_document_deletes_only_the_document_vectors(monkeypatch):
    vector_store = _RecordingVectorStore()
    monkeypatch.setattr(provisioner, "ChromaVectorStore", lambda **kwargs: vector_store)

    provisioner.remove_document("doc-1")

    assert vector_store.collection.where == {"document_id": "doc-1"}


def test_uploaded_document_saved_using_document_name_not_id(tmp_path, monkeypatch):
    monkeypatch.setattr(provisioner, "DOCUMENTS_DIR", str(tmp_path))
    processor = _RecordingProcessor(".docx")
    store = _RecordingStore()
    document = Document(
        document_id="DOC-999",
        document_name="Leave Policy",
        original_filename="Leave Policy.docx",
        project_id="proj-1",
    )
    content = base64.b64encode(b"PK\x03\x04test[Content_Types].xml").decode("utf-8")

    provision_document(None, document, content, store=store, processor=processor)

    assert (tmp_path / "Leave Policy.docx").exists()
    assert not (tmp_path / "DOC-999.docx").exists()
    assert document.storage_location == str(tmp_path / "Leave Policy.docx")
