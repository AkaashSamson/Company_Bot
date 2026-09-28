"""Tests for the canonical chunk metadata contract.

The contract is exercised through the domain model and the builder, and the
store projection is checked against the two constraints Chroma actually
enforces: metadata values must be non-null, and list values must be non-empty.
Both constraints are what make "omit what is unknown" the correct behaviour
rather than merely a stylistic choice.
"""

import pytest

from app.domain.entities.chunk_metadata import (
    CANONICAL_FIELDS,
    CONTENT_TYPE_TEXT,
    HIERARCHY_SEPARATOR,
    UNASSIGNED_PROJECT_ID,
    ChunkMetadata,
    build_chunk_metadata,
)
from app.domain.ports.document_processing import ProcessedChunk, ProcessedDocument, SectionHeading


def _document(*chunks):
    return ProcessedDocument(chunks=tuple(chunks))


def _complete() -> ChunkMetadata:
    """The fully populated shape from the canonical contract's example."""
    return ChunkMetadata(
        document_id="unique-document-id",
        project_id="project-7",
        source_filename="NEXORA TECHNOLOGIES PVT.docx",
        page_number=42,
        section_heading="14.4 Performance Review Process",
        hierarchy_path=("14. Performance Management", "14.4 Performance Review Process"),
        chunk_index=304,
    )


# --- complete metadata -------------------------------------------------------


def test_complete_metadata_carries_every_canonical_field():
    assert _complete().as_dict() == {
        "document_id": "unique-document-id",
        "project_id": "project-7",
        "source_filename": "NEXORA TECHNOLOGIES PVT.docx",
        "page_number": 42,
        "section_heading": "14.4 Performance Review Process",
        "hierarchy_path": [
            "14. Performance Management",
            "14.4 Performance Review Process",
        ],
        "chunk_index": 304,
        "content_type": CONTENT_TYPE_TEXT,
    }


def test_complete_metadata_exposes_no_key_outside_the_contract():
    assert set(_complete().as_dict()) == set(CANONICAL_FIELDS)


def test_hierarchy_is_ordered_outermost_first():
    assert _complete().hierarchy_path == (
        "14. Performance Management",
        "14.4 Performance Review Process",
    )
    assert _complete().hierarchy_text == HIERARCHY_SEPARATOR.join(_complete().hierarchy_path)


def test_section_heading_is_the_most_specific_hierarchy_entry():
    """The contract's example pairs the innermost heading with the full path."""
    entry = _complete()

    assert entry.section_heading == entry.hierarchy_path[-1]


# --- missing page ------------------------------------------------------------


def test_missing_page_is_none_in_the_model():
    assert ChunkMetadata("d", "f.docx", 0).page_number is None


def test_missing_page_is_omitted_from_the_store_projection():
    """A null is rejected by the store, and must not be invented as a number."""
    payload = ChunkMetadata("d", "f.docx", 0, page_number=None).as_dict()

    assert "page_number" not in payload
    assert payload["document_id"] == "d"


# --- missing heading ---------------------------------------------------------


def test_missing_heading_is_none_and_omitted():
    entry = ChunkMetadata("d", "f.docx", 0)

    assert entry.section_heading is None
    assert "section_heading" not in entry.as_dict()


def test_blank_heading_is_rejected_rather_than_stored_as_empty():
    with pytest.raises(ValueError, match="section_heading"):
        ChunkMetadata("d", "f.docx", 0, section_heading="   ")


# --- empty hierarchy ---------------------------------------------------------


def test_empty_hierarchy_is_omitted_because_the_store_rejects_empty_lists():
    entry = ChunkMetadata("d", "f.docx", 0)

    assert entry.hierarchy_path == ()
    assert entry.hierarchy_text is None
    assert "hierarchy_path" not in entry.as_dict()


def test_a_single_heading_populates_both_heading_fields():
    entry = ChunkMetadata("d", "f.docx", 0, section_heading="Scope", hierarchy_path=("Scope",))

    payload = entry.as_dict()
    assert payload["section_heading"] == "Scope"
    assert payload["hierarchy_path"] == ["Scope"]


def test_blank_hierarchy_entry_is_rejected():
    with pytest.raises(ValueError, match="hierarchy_path"):
        ChunkMetadata("d", "f.docx", 0, hierarchy_path=("Scope", ""))


# --- unassigned project ------------------------------------------------------


def test_unassigned_project_is_the_default():
    assert ChunkMetadata("d", "f.docx", 0).project_id == UNASSIGNED_PROJECT_ID
    assert UNASSIGNED_PROJECT_ID == "unassigned"


@pytest.mark.parametrize("blank", [None, ""])
def test_unassigned_project_survives_a_blank_value(blank):
    """Retrieval authorization filters on the literal, so a blank must not leak."""
    entry = ChunkMetadata("d", "f.docx", 0, project_id=blank)

    assert entry.project_id == UNASSIGNED_PROJECT_ID
    assert entry.as_dict()["project_id"] == "unassigned"


def test_project_id_is_never_sourced_from_the_parsed_document():
    processed = _document(ProcessedChunk(text="Body", index=0))

    entries = build_chunk_metadata(processed, document_id="d", source_filename="f.docx")

    assert [entry.project_id for entry in entries] == [UNASSIGNED_PROJECT_ID]


def test_caller_scope_is_used_when_supplied():
    processed = _document(ProcessedChunk(text="Body", index=0))

    entries = build_chunk_metadata(
        processed, document_id="d", source_filename="f.docx", project_id="project-7"
    )

    assert entries[0].project_id == "project-7"


# --- deterministic chunk index ----------------------------------------------


def test_chunk_index_is_zero_based_and_deterministic():
    processed = _document(*[ProcessedChunk(text=f"Body {n}", index=n) for n in range(3)])

    first = build_chunk_metadata(processed, document_id="d", source_filename="f.docx")
    second = build_chunk_metadata(processed, document_id="d", source_filename="f.docx")

    assert [entry.chunk_index for entry in first] == [0, 1, 2]
    assert [entry.chunk_index for entry in first] == [entry.chunk_index for entry in second]


def test_chunk_index_follows_chunk_sequence_not_parser_numbering():
    """A parser that numbers its own output cannot perturb the stored index."""
    processed = _document(
        ProcessedChunk(text="First", index=7),
        ProcessedChunk(text="Second", index=99),
    )

    entries = build_chunk_metadata(processed, document_id="d", source_filename="f.docx")

    assert [entry.chunk_index for entry in entries] == [0, 1]


def test_negative_chunk_index_is_rejected():
    with pytest.raises(ValueError, match="zero-based"):
        ChunkMetadata("d", "f.docx", -1)


# --- identity ----------------------------------------------------------------


def test_document_id_and_source_filename_must_be_supplied_by_the_caller():
    processed = _document(ProcessedChunk(text="Body", index=0))

    for kwargs in (
        {"document_id": "", "source_filename": "f.docx"},
        {"document_id": "d", "source_filename": "  "},
    ):
        with pytest.raises(ValueError):
            build_chunk_metadata(processed, **kwargs)


def test_source_filename_is_recorded_verbatim():
    processed = _document(ProcessedChunk(text="Body", index=0))

    entries = build_chunk_metadata(
        processed, document_id="d", source_filename="NEXORA TECHNOLOGIES PVT.docx"
    )

    assert entries[0].as_dict()["source_filename"] == "NEXORA TECHNOLOGIES PVT.docx"


# --- structure propagation ---------------------------------------------------


def test_builder_takes_page_and_hierarchy_from_the_parsed_chunk():
    processed = _document(
        ProcessedChunk(
            text="Body",
            index=0,
            page_number=42,
            section_path=(
                SectionHeading(level=1, title="14. Performance Management"),
                SectionHeading(level=2, title="14.4 Performance Review Process"),
            ),
        )
    )

    entry = build_chunk_metadata(processed, document_id="d", source_filename="f.docx")[0]

    assert entry.page_number == 42
    assert entry.section_heading == "14.4 Performance Review Process"
    assert entry.hierarchy_path == (
        "14. Performance Management",
        "14.4 Performance Review Process",
    )


# --- store compatibility -----------------------------------------------------


def test_every_projected_value_is_storable():
    """Chroma accepts scalars and non-empty lists only."""
    for entry in (_complete(), ChunkMetadata("d", "f.docx", 0)):
        for key, value in entry.as_dict().items():
            if value is None:
                pytest.fail(f"{key} is null, which the store rejects")
            if isinstance(value, (list, tuple)):
                assert value, f"{key} is an empty list, which the store rejects"
            else:
                assert isinstance(value, (str, int, float, bool)), f"{key} is not a scalar"


def test_page_number_must_be_one_based_when_present():
    with pytest.raises(ValueError, match="one-based"):
        ChunkMetadata("d", "f.docx", 0, page_number=0)


def test_hierarchy_path_is_normalised_to_a_tuple():
    entry = ChunkMetadata("d", "f.docx", 0, hierarchy_path=["Scope"])

    assert entry.hierarchy_path == ("Scope",)


# --- legacy compatibility ---------------------------------------------------


def test_legacy_keys_are_derived_from_canonical_fields():
    entry = _complete()

    assert entry.as_legacy() == {
        "source": "NEXORA TECHNOLOGIES PVT.docx",
        "section": "14. Performance Management > 14.4 Performance Review Process",
    }


def test_legacy_keys_cannot_disagree_with_canonical_fields():
    entry = _complete()
    payload = entry.as_dict()
    legacy = entry.as_legacy()

    assert legacy["source"] == payload["source_filename"]
    assert legacy["section"] == HIERARCHY_SEPARATOR.join(payload["hierarchy_path"])


def test_legacy_section_is_omitted_without_hierarchy():
    assert "section" not in ChunkMetadata("d", "f.docx", 0).as_legacy()


def test_legacy_source_is_always_present():
    assert ChunkMetadata("d", "f.docx", 0).as_legacy()["source"] == "f.docx"
