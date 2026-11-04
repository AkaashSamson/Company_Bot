"""Chunk record metadata for the ingestion pipeline.

Records are produced from a neutral ``ProcessedDocument`` by
``build_chunk_records_from_processed``, so these exercise the same path every
ingestion entry point now uses.
"""
from app.domain.ports.document_processing import ProcessedChunk, ProcessedDocument
from app.use_cases.ingestion.document_processing import build_chunk_records_from_processed


def _records(text="Some policy text.", **kwargs):
    """Build records for a single-chunk text document."""
    processed = ProcessedDocument(
        chunks=(ProcessedChunk(text=text, index=0),), file_type=kwargs.pop("file_type", None)
    )
    return build_chunk_records_from_processed(processed, document_id="doc-1", **kwargs)


def test_chunk_records_include_document_and_section_metadata():
    records = _records(project_id="p1", source="Policy.txt")

    assert records
    metadata = records[0]["metadata"]
    assert metadata["document_id"] == "doc-1"
    assert metadata["project_id"] == "p1"
    assert metadata["source"] == "Policy.txt"
    assert metadata["source_filename"] == "Policy.txt"
    assert metadata["chunk_index"] == 0


def test_chunk_records_default_file_type_and_version():
    records = _records(project_id="p1")

    metadata = records[0]["metadata"]
    assert metadata["file_type"] == "text"
    assert metadata["version"] == "1.0"


def test_chunk_records_include_file_type_and_version_metadata():
    records = _records(project_id="p1", file_type="txt", version="2.1")

    metadata = records[0]["metadata"]
    assert metadata["file_type"] == "txt"
    assert metadata["version"] == "2.1"


def test_chunk_records_mark_unassigned_documents():
    records = _records(project_id=None)

    assert records[0]["metadata"]["project_id"] == "unassigned"


def test_chunk_records_are_indexed_per_chunk():
    processed = ProcessedDocument(
        chunks=(
            ProcessedChunk(text="First block.", index=0),
            ProcessedChunk(text="Second block.", index=1),
            ProcessedChunk(text="Third block.", index=2),
        )
    )

    records = build_chunk_records_from_processed(processed, document_id="doc-1", project_id="p1")

    assert [record["metadata"]["chunk_index"] for record in records] == list(range(len(records)))
    assert [record["metadata"]["document_id"] for record in records] == ["doc-1"] * len(records)
