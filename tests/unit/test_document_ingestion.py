from pathlib import Path

from app.use_cases.ingestion.document_processing import chunk_text, extract_text_from_document
from app.use_cases.ingestion.document_ingestion_service import DocumentIngestionService


class FakeStore:
    def __init__(self):
        self.persist_directory = "/fake/.chroma"
        self.added = []

    def count_by_source(self, source):
        return 0

    def delete_by_source(self, source):
        return 0

    def add_documents(self, records):
        self.added = list(records)


def test_ingest_writes_document_id_into_every_chunk(tmp_path):
    text = "Information security policy. " * 60
    path = tmp_path / "security.txt"
    path.write_text(text, encoding="utf-8")

    service = DocumentIngestionService.__new__(DocumentIngestionService)
    store = FakeStore()
    service.store = store
    service.chunk_size = 50

    result = service.ingest(str(path), source_name="security.txt", document_id="DOC007")

    assert result.status == "stored"
    assert store.added, "chunks should have been persisted"
    for record in store.added:
        metadata = record["metadata"]
        assert metadata["document_id"] == "DOC007"
        assert metadata["chunk_index"] >= 0
        assert metadata["source"] == "security.txt"


def test_ingest_falls_back_to_file_stem_when_no_document_id(tmp_path):
    path = tmp_path / "orphan.txt"
    path.write_text("Some content. " * 60, encoding="utf-8")

    service = DocumentIngestionService.__new__(DocumentIngestionService)
    store = FakeStore()
    service.store = store
    service.chunk_size = 50

    service.ingest(str(path), source_name="orphan.txt")

    for record in store.added:
        assert record["metadata"]["document_id"] == "orphan"


def test_extract_text_from_nexora_docx():
    doc_path = Path("input/NEXORA TECHNOLOGIES PVT.docx")
    assert doc_path.exists(), "Nexora policy document should exist in input/"

    text = extract_text_from_document(str(doc_path))
    assert "NEXORA TECHNOLOGIES PVT" in text
    assert "Employee Handbook" in text

    chunks = chunk_text(text, chunk_size=400)
    assert len(chunks) >= 1
    assert all(chunk.strip() for chunk in chunks)
