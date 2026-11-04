"""End-to-end verification that the canonical chunk metadata contract survives
into the Chroma vector store, on both the text and the structural ingestion
path, alongside the pre-canonical keys retrieval and citation code still reads.
"""
import base64

import app.infrastructure.ingestion.provisioner as provisioner
from app.domain.entities.organization_models import Document
from app.domain.ports.document_processing import ProcessedChunk, ProcessedDocument, SectionHeading
from app.infrastructure.ingestion.provisioner import provision_document
from app.infrastructure.vector.chroma_client import ChromaVectorStore


class _StubProcessor:
    """A port implementation that reports fixed structure, with no parser.

    The contract under test is the metadata, not the parsing, so this keeps the
    end-to-end check independent of any document conversion stack.
    """

    def __init__(self, processed: ProcessedDocument):
        self._processed = processed

    def supported_extensions(self):
        return (".txt",)

    def supports(self, file_name: str) -> bool:
        return file_name.lower().endswith(".txt")

    def process(self, content: bytes, file_name: str) -> ProcessedDocument:
        return self._processed


def _stored(store, document_id):
    return store.collection.get(where={"document_id": document_id}, include=["metadatas"])[
        "metadatas"
    ]


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


def test_text_path_stores_the_full_canonical_contract(tmp_path, monkeypatch):
    """Every stored chunk satisfies the contract, whichever pipeline produced it."""
    monkeypatch.setattr(provisioner, "DOCUMENTS_DIR", str(tmp_path / "input"))
    store = ChromaVectorStore(
        collection_name="test_canonical_text", persist_directory=str(tmp_path / "chroma-canonical")
    )
    (tmp_path / "input").mkdir()

    document = Document("c-doc-1", "Onboarding.txt", project_id="p1", version="2.1")
    provision_document(
        None,
        document,
        base64.b64encode(b"Employees complete onboarding within 30 days.").decode("utf-8"),
        store=store,
    )

    for metadata in _stored(store, "c-doc-1"):
        assert {
            "document_id",
            "project_id",
            "source_filename",
            "chunk_index",
            "content_type",
        } <= metadata.keys()
        assert metadata["document_id"] == "c-doc-1"
        assert metadata["project_id"] == "p1"
        assert metadata["source_filename"] == "Onboarding.txt"
        assert metadata["content_type"] == "text"
        # The text pipeline reports no structure, so these are absent, not empty.
        assert "page_number" not in metadata
        assert "section_heading" not in metadata
        assert "hierarchy_path" not in metadata


def test_structural_path_stores_page_heading_and_hierarchy(tmp_path, monkeypatch):
    """Structure survives the store, including hierarchy as a real ordered list."""
    monkeypatch.setattr(provisioner, "DOCUMENTS_DIR", str(tmp_path / "input"))
    store = ChromaVectorStore(
        collection_name="test_canonical_structured",
        persist_directory=str(tmp_path / "chroma-structural"),
    )
    (tmp_path / "input").mkdir()

    processed = ProcessedDocument(
        file_type="txt",
        chunks=(
            ProcessedChunk(
                text="Reviews run twice a year.",
                index=0,
                page_number=42,
                section_path=(
                    SectionHeading(level=1, title="14. Performance Management"),
                    SectionHeading(level=2, title="14.4 Performance Review Process"),
                ),
            ),
            ProcessedChunk(text="No heading above this chunk.", index=1),
        ),
    )

    document = Document("s-doc-1", "Handbook.txt", project_id="p2", version="1.0")
    provision_document(
        None,
        document,
        base64.b64encode(b"Reviews run twice a year.").decode("utf-8"),
        store=store,
        processor=_StubProcessor(processed),
    )

    structured, unstructured = _stored(store, "s-doc-1")

    assert structured["page_number"] == 42
    assert structured["section_heading"] == "14.4 Performance Review Process"
    assert structured["hierarchy_path"] == [
        "14. Performance Management",
        "14.4 Performance Review Process",
    ]
    # Pre-canonical keys stay in step with the canonical ones.
    assert structured["section"] == "14. Performance Management > 14.4 Performance Review Process"
    assert structured["source"] == structured["source_filename"] == "Handbook.txt"

    assert "page_number" not in unstructured
    assert "section_heading" not in unstructured
    assert "hierarchy_path" not in unstructured
    assert "section" not in unstructured


def test_stored_chunk_indexes_are_deterministic_and_zero_based(tmp_path, monkeypatch):
    monkeypatch.setattr(provisioner, "DOCUMENTS_DIR", str(tmp_path / "input"))
    store = ChromaVectorStore(
        collection_name="test_canonical_indexes", persist_directory=str(tmp_path / "chroma-index")
    )
    (tmp_path / "input").mkdir()

    processed = ProcessedDocument(
        file_type="txt",
        chunks=tuple(
            # Deliberately out-of-order parser numbering.
            ProcessedChunk(text=f"Chunk {n}", index=n * 10) for n in range(3)
        ),
    )
    document = Document("i-doc-1", "Notes.txt", project_id="p3")
    provision_document(
        None,
        document,
        base64.b64encode(b"Body.").decode("utf-8"),
        store=store,
        processor=_StubProcessor(processed),
    )

    indexes = sorted(metadata["chunk_index"] for metadata in _stored(store, "i-doc-1"))

    assert indexes == [0, 1, 2]