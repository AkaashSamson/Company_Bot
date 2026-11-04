"""Unit tests for financial number sanitization during document ingestion."""

from __future__ import annotations

import pytest

from app.domain.ports.document_processing import ProcessedChunk, ProcessedDocument
from app.use_cases.ingestion.document_processing import (
    build_chunk_records_from_processed,
    sanitize_financial_text,
)


def test_sanitize_financial_text_comma_and_decimal_spacing():
    raw = "Running costs, 31 December 2021 (in EUR). = 350, 390. 24."
    expected = "Running costs, 31 December 2021 (in EUR). = 350,390.24."
    assert sanitize_financial_text(raw) == expected


def test_sanitize_financial_text_millions_with_multiple_commas():
    raw = "TOTAL EXPENSES = 1, 744, 964. 57 EUR"
    expected = "TOTAL EXPENSES = 1,744,964.57 EUR"
    assert sanitize_financial_text(raw) == expected


def test_sanitize_financial_text_parentheses_negative_amounts():
    raw = "Depreciation usage = (13, 699. 88) and decrease = (1, 464. 48)"
    expected = "Depreciation usage = (13,699.88) and decrease = (1,464.48)"
    assert sanitize_financial_text(raw) == expected


def test_sanitize_financial_text_zero_and_small_decimals():
    assert sanitize_financial_text("NET SURPLUS = 0. 00") == "NET SURPLUS = 0.00"
    assert sanitize_financial_text("Prepayment: 648. 13.") == "Prepayment: 648.13."


def test_sanitize_financial_text_preserves_sentence_boundary_years():
    text = "In 2021. 50 employees joined the team."
    assert sanitize_financial_text(text) == text


def test_sanitize_financial_text_empty_and_none():
    assert sanitize_financial_text("") == ""
    assert sanitize_financial_text(None) is None


def test_build_chunk_records_applies_financial_sanitization():
    chunk = ProcessedChunk(
        text="Balance as at January 1, 2021 = 3, 254, 632. 46 EUR",
        index=0,
    )
    doc = ProcessedDocument(
        chunks=(chunk,),
        file_type="pdf",
        page_count=1,
    )
    records = build_chunk_records_from_processed(
        doc,
        document_id="DOC-004",
        project_id="PROJ-01",
    )
    assert len(records) == 1
    assert "3,254,632.46 EUR" in records[0]["text"]
    assert "3, 254, 632. 46" not in records[0]["text"]
