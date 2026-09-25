from app.use_cases.ingestion.document_processing import build_chunk_records


def test_chunk_records_include_document_and_section_metadata():
    records = build_chunk_records("Some policy text.", document_id="doc-1", project_id="p1", source="Policy.txt")

    assert records
    metadata = records[0]["metadata"]
    assert metadata["document_id"] == "doc-1"
    assert metadata["project_id"] == "p1"
    assert metadata["source"] == "Policy.txt"
    assert metadata["chunk_index"] == 0


def test_chunk_records_default_file_type_and_version():
    records = build_chunk_records("Some policy text.", document_id="doc-1", project_id="p1")

    metadata = records[0]["metadata"]
    assert metadata["file_type"] == "text"
    assert metadata["version"] == "1.0"


def test_chunk_records_include_file_type_and_version_metadata():
    records = build_chunk_records(
        "Some policy text.",
        document_id="doc-1",
        project_id="p1",
        file_type="txt",
        version="2.1",
    )

    metadata = records[0]["metadata"]
    assert metadata["file_type"] == "txt"
    assert metadata["version"] == "2.1"


def test_chunk_records_mark_unassigned_documents():
    records = build_chunk_records("Some policy text.", document_id="doc-1", project_id=None)

    assert records[0]["metadata"]["project_id"] == "unassigned"


def test_chunk_records_are_indexed_per_chunk():
    records = build_chunk_records(
        "First block.\n\nSecond block.\n\nThird block.",
        document_id="doc-1",
        project_id="p1",
    )

    assert [record["metadata"]["chunk_index"] for record in records] == list(range(len(records)))
    assert [record["metadata"]["document_id"] for record in records] == ["doc-1"] * len(records)