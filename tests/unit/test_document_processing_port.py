"""Unit tests for the neutral data contract of ``DocumentProcessingPort``.

The port is the seam that keeps a concrete conversion technology out of the
application layer, so these tests pin the *shape* of the neutral result rather
than the behaviour of any adapter: what a parser is allowed to return, what it
must never supply, and whether a non-vendor implementation satisfies the
protocol.
"""
from dataclasses import FrozenInstanceError

import pytest

from app.domain.ports import document_processing
from app.domain.ports.document_processing import (
    DocumentProcessingPort,
    ProcessedChunk,
    ProcessedDocument,
    SectionHeading,
)


class FakeDocumentProcessor:
    """Non-vendor implementation used to exercise the port contract."""

    def __init__(self, result=None, extensions=(".txt", ".pdf")):
        self._result = result
        self._extensions = extensions

    def supported_extensions(self):
        return self._extensions

    def supports(self, file_name):
        return file_name.lower().endswith(tuple(self._extensions))

    def process(self, content, file_name):
        if self._result is not None:
            return self._result
        return ProcessedDocument(
            chunks=(ProcessedChunk(text=content.decode("utf-8"), index=0),),
            file_type="txt",
        )


def test_non_vendor_processor_satisfies_the_protocol():
    """Verify the Open/Closed principle: a plain implementation satisfies the port."""
    processor = FakeDocumentProcessor()

    assert isinstance(processor, DocumentProcessingPort)


def test_port_module_exposes_no_vendor_specific_types():
    """The seam must stay swappable: no conversion-technology names leak into it."""
    leaked = [name for name in dir(document_processing) if "docling" in name.lower()]

    assert leaked == []


def test_chunk_defaults_are_neutral_and_self_describing():
    """A parser with no structure to report still returns a well-formed chunk."""
    chunk = ProcessedChunk(text="Employees get 10 sick leave days.", index=0)

    assert chunk.text == "Employees get 10 sick leave days."
    assert chunk.index == 0
    assert chunk.page_number is None
    assert chunk.section_path == ()
    assert chunk.content_type == "text"
    assert chunk.metadata == {}


def test_chunk_flattens_heading_hierarchy_into_a_section_label():
    """Structural hierarchy must reduce to a citation-ready label."""
    chunk = ProcessedChunk(
        text="Accrual is capped at 30 days.",
        index=4,
        section_path=(
            SectionHeading(level=1, title="Leave Policy"),
            SectionHeading(level=2, title="Accrual"),
        ),
    )

    assert chunk.section == "Leave Policy > Accrual"


def test_chunk_reports_no_section_when_the_document_has_no_outline():
    """Returning None lets the metadata builder omit the key and keep existing defaults."""
    assert ProcessedChunk(text="Body text.", index=0).section is None


def test_processed_document_carries_document_level_facts():
    """Page count, format, and outline are content-derived document facts."""
    document = ProcessedDocument(
        chunks=(ProcessedChunk(text="Body text.", index=0, page_number=1),),
        file_type="pdf",
        page_count=12,
        outline=(SectionHeading(level=1, title="Leave Policy"),),
    )

    assert len(document.chunks) == 1
    assert document.file_type == "pdf"
    assert document.page_count == 12
    assert document.outline[0].title == "Leave Policy"
    assert document.chunks[0].page_number == 1


def test_chunk_indexes_carry_the_information_canonical_metadata_requires():
    """The neutral result must supply every content-derived canonical metadata key."""
    document = ProcessedDocument(
        chunks=(
            ProcessedChunk(
                text="Employees get 10 sick leave days.",
                index=0,
                page_number=3,
                section_path=(SectionHeading(level=1, title="Sick Leave"),),
                content_type="text",
                metadata={"asset_index": 0},
            ),
            ProcessedChunk(text="Carryover is capped at 5 days.", index=1, page_number=4),
        ),
        file_type="pdf",
    )

    assert [chunk.index for chunk in document.chunks] == [0, 1]
    assert [chunk.page_number for chunk in document.chunks] == [3, 4]
    assert document.file_type == "pdf"
    assert document.chunks[0].section == "Sick Leave"
    assert document.chunks[0].metadata["asset_index"] == 0


def test_identity_and_scope_are_absent_from_the_neutral_result():
    """A parser must never be the source of document identity or RBAC scope."""
    forbidden = {"document_id", "project_id", "source", "version"}

    document = ProcessedDocument(
        chunks=(ProcessedChunk(text="Body text.", index=0, metadata={"language": "en"}),),
        file_type="txt",
    )

    assert not forbidden & set(document.metadata)
    assert not forbidden & set(document.chunks[0].metadata)
    assert not hasattr(document, "document_id")
    assert not hasattr(document, "project_id")


def test_scalar_metadata_is_accepted():
    assert ProcessedChunk(
        text="Body text.", index=0, metadata={"language": "en", "page_confidence": 0.91, "is_header": False}
    ).metadata["page_confidence"] == 0.91


def test_non_scalar_metadata_is_rejected_at_the_port_boundary():
    """Nested parser structures must fail as a contract error, not inside a store."""
    with pytest.raises(TypeError, match="scalar"):
        ProcessedChunk(text="Body text.", index=0, metadata={"tables": [{"cells": []}]})

    with pytest.raises(TypeError, match="scalar"):
        ProcessedDocument(chunks=(), metadata={"outline": [1, 2, 3]})


def test_non_string_metadata_keys_are_rejected():
    with pytest.raises(TypeError, match="keys must be str"):
        ProcessedChunk(text="Body text.", index=0, metadata={1: "one"})


def test_result_objects_are_immutable():
    """Port value objects are frozen so an adapter cannot mutate a shared result."""
    chunk = ProcessedChunk(text="Body text.", index=0)

    with pytest.raises(FrozenInstanceError):
        chunk.text = "Mutated text."  # type: ignore[misc]
