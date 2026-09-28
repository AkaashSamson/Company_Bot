"""Tests for the neutral-document to canonical-record bridge.

Covers the seam that lets structurally parsed documents be written through the
same Chroma contract as the fixed-width text pipeline, including the rule that
absent structure is omitted rather than filled in with a default.
"""

from app.domain.ports.document_processing import (
    ProcessedChunk,
    ProcessedDocument,
    SectionHeading,
)
from app.infrastructure.document.plaintext_processor import PlainTextDocumentProcessor
from app.use_cases.ingestion.document_processing import build_chunk_records_from_processed

#: The canonical contract every stored chunk must satisfy, whichever pipeline
#: produced it. Structural keys are optional: absent structure is omitted.
CANONICAL_REQUIRED_KEYS = {
    "document_id",
    "project_id",
    "source_filename",
    "chunk_index",
    "content_type",
}

#: Pre-canonical keys retrieval, RBAC, and citation code still read.
LEGACY_KEYS = {
    "source",
    "file_type",
    "version",
}

#: Keys the document entity owns and that predate the canonical contract.
DOCUMENT_ENTITY_KEYS = {"file_type", "version"}


def _document(*chunks, file_type="docx", page_count=None, outline=()):
    return ProcessedDocument(
        chunks=tuple(chunks), file_type=file_type, page_count=page_count, outline=tuple(outline)
    )


def _text_records(text="Body", file_name="Body.txt", **kwargs):
    """Records produced by the real text pipeline, through the port."""
    processed = PlainTextDocumentProcessor().process(text.encode("utf-8"), file_name)
    return build_chunk_records_from_processed(processed, document_id="doc-1", **kwargs)


def test_both_pipelines_emit_the_canonical_contract():
    """The text pipeline reports no structure, but still satisfies the contract."""
    structural = build_chunk_records_from_processed(
        _document(ProcessedChunk(text="Body", index=0)),
        document_id="doc-1",
        project_id="p-1",
    )
    text = _text_records("Body", project_id="p-1")

    for record in structural + text:
        assert CANONICAL_REQUIRED_KEYS <= record["metadata"].keys()
        assert LEGACY_KEYS <= record["metadata"].keys()


def test_both_pipelines_preserve_the_pre_canonical_keys():
    """RBAC and citation reads of ``source``/``file_type``/``version`` still hold."""
    structural = build_chunk_records_from_processed(
        _document(ProcessedChunk(text="Body", index=0)),
        document_id="doc-1",
        project_id="p-1",
        source="Body.txt",
        version="2.1",
    )
    text = _text_records("Body", project_id="p-1", source="Body.txt", version="2.1")

    for record in structural + text:
        assert record["metadata"]["source"] == "Body.txt"
        assert record["metadata"]["version"] == "2.1"
        assert record["metadata"]["project_id"] == "p-1"
        assert record["metadata"]["document_id"] == "doc-1"


def test_legacy_and_canonical_names_agree():
    processed = _document(
        ProcessedChunk(
            text="Body",
            index=0,
            section_path=(SectionHeading(level=1, title="Scope"),),
        )
    )

    metadata = build_chunk_records_from_processed(
        processed, document_id="doc-1", source="Body.docx"
    )[0]["metadata"]

    assert metadata["source"] == metadata["source_filename"]
    assert metadata["section"] == " > ".join(metadata["hierarchy_path"])


def test_structural_facts_are_added_only_when_present():
    processed = _document(
        ProcessedChunk(
            text="Leave policy detail",
            index=0,
            page_number=4,
            section_path=(SectionHeading(level=1, title="Leave"),),
            content_type="text",
        ),
        ProcessedChunk(text="No structural information", index=1),
    )

    records = build_chunk_records_from_processed(processed, document_id="doc-1")

    assert records[0]["metadata"]["page_number"] == 4
    assert records[0]["metadata"]["section"] == "Leave"
    # Absent page and section are omitted, not defaulted, so the existing
    # citation fallbacks in retrieval still decide what to show.
    assert "page_number" not in records[1]["metadata"]
    assert "section" not in records[1]["metadata"]


def test_nested_section_path_is_flattened_for_citation_display():
    processed = _document(
        ProcessedChunk(
            text="Nested body",
            index=0,
            section_path=(
                SectionHeading(level=1, title="Part One"),
                SectionHeading(level=2, title="Topic Two"),
            ),
        )
    )

    records = build_chunk_records_from_processed(processed, document_id="doc-1")

    assert records[0]["metadata"]["section"] == "Part One > Topic Two"


def test_identity_and_scope_are_never_taken_from_parsed_content():
    """A document cannot widen its own authorization scope by naming a project."""
    processed = _document(ProcessedChunk(text="Body", index=0))

    records = build_chunk_records_from_processed(processed, document_id="doc-1")

    assert records[0]["metadata"]["project_id"] == "unassigned"
    assert records[0]["metadata"]["document_id"] == "doc-1"
    assert records[0]["metadata"]["source"] == "doc-1"


def test_caller_scope_wins_over_defaults():
    processed = _document(ProcessedChunk(text="Body", index=0))

    records = build_chunk_records_from_processed(
        processed,
        document_id="doc-1",
        project_id="project-7",
        source="HR_Policy_Manual.docx",
        version="2.1",
    )

    assert records[0]["metadata"]["project_id"] == "project-7"
    assert records[0]["metadata"]["source"] == "HR_Policy_Manual.docx"
    assert records[0]["metadata"]["version"] == "2.1"


def test_resolved_file_type_takes_precedence_over_the_parser_report():
    processed = _document(ProcessedChunk(text="Body", index=0), file_type="pdf")

    records = build_chunk_records_from_processed(processed, document_id="doc-1", file_type="docx")

    assert records[0]["metadata"]["file_type"] == "docx"


def test_parser_report_is_used_when_the_caller_has_no_type():
    processed = _document(ProcessedChunk(text="Body", index=0), file_type="pdf")

    records = build_chunk_records_from_processed(processed, document_id="doc-1")

    assert records[0]["metadata"]["file_type"] == "pdf"


def test_file_type_falls_back_to_text_when_no_type_is_known():
    processed = _document(ProcessedChunk(text="Body", index=0), file_type=None)

    records = build_chunk_records_from_processed(processed, document_id="doc-1")

    assert records[0]["metadata"]["file_type"] == "text"


def test_record_ids_are_unique_and_chunk_indexes_contiguous():
    processed = _document(*[ProcessedChunk(text=f"Body {n}", index=n) for n in range(4)])

    records = build_chunk_records_from_processed(processed, document_id="doc-1")

    assert [record["id"] for record in records] == [
        "doc-1-0",
        "doc-1-1",
        "doc-1-2",
        "doc-1-3",
    ]
    assert [record["metadata"]["chunk_index"] for record in records] == [0, 1, 2, 3]


def test_ids_stay_unique_even_if_a_chunker_repeats_an_ordinal():
    processed = _document(
        ProcessedChunk(text="First", index=0),
        ProcessedChunk(text="Second", index=0),
    )

    records = build_chunk_records_from_processed(processed, document_id="doc-1")

    assert len({record["id"] for record in records}) == 2


def test_every_metadata_value_is_storable_by_chroma():
    """Chroma accepts scalars and non-empty lists, and rejects nulls.

    Verified against chromadb 1.5.9: a null value raises a conversion error and
    an empty list raises "to be non-empty", which is why absent structure is
    omitted rather than written as null or ``[]``.
    """
    complete = _document(
        ProcessedChunk(
            text="Body",
            index=0,
            page_number=2,
            section_path=(SectionHeading(level=1, title="Leave"),),
        )
    )
    bare = _document(ProcessedChunk(text="Body", index=0))

    records = build_chunk_records_from_processed(complete, document_id="doc-1") + (
        build_chunk_records_from_processed(bare, document_id="doc-1")
    )

    for record in records:
        for key, value in record["metadata"].items():
            assert value is not None, f"{key} is null, which the store rejects"
            if isinstance(value, (list, tuple)):
                assert value, f"{key} is an empty list, which the store rejects"
            else:
                assert isinstance(value, (str, int, float, bool)), f"{key} is not a scalar"


def test_absent_structure_is_omitted_rather_than_written_as_empty():
    processed = _document(ProcessedChunk(text="Body", index=0))

    metadata = build_chunk_records_from_processed(processed, document_id="doc-1")[0]["metadata"]

    assert "page_number" not in metadata
    assert "section_heading" not in metadata
    assert "hierarchy_path" not in metadata
    assert "section" not in metadata


def test_document_with_no_chunks_produces_no_records():
    processed = _document(file_type="pdf", page_count=3)

    assert build_chunk_records_from_processed(processed, document_id="doc-1") == []
