"""
Unit tests for Chunk Editor and Pre-Ingestion Remediation Engine.
"""

import json
from pathlib import Path
import pytest

from sandbox.engine.chunk_editor import (
    validate_chunk_content,
    auto_normalize_edited_chunk,
    edit_and_ingest_chunk,
    stage_chunk_for_review,
    load_staged_chunks_for_review,
    remove_from_staged_review,
    STAGED_REVIEW_FILE_PATH,
)


def test_validate_optimal_chunk():
    text = (
        "The Company provides standard annual leave of 20 days per calendar year. "
        "Employees must request leave at least two weeks in advance through the HR portal. "
        "All requests require supervisor approval prior to the scheduled leave start date. "
        "Unused leave may be carried forward up to a maximum of five days into the next calendar year, "
        "provided that prior written approval is obtained from department leadership."
    )
    res = validate_chunk_content(text)
    assert res["is_safe_budget"] is True
    assert res["is_truncated"] is False
    assert res["is_micro"] is False
    assert res["quality_score"] >= 0.80
    assert len(res["issues"]) == 0


def test_validate_truncated_chunk():
    # Long text with > 250 words
    text = " ".join(["policy"] * 260) + "."
    res = validate_chunk_content(text)
    assert res["is_truncated"] is True
    assert "CRITICAL_TRUNCATION" in res["issues"]
    assert res["quality_score"] < 0.60


def test_validate_micro_fragment():
    text = "Short text."
    res = validate_chunk_content(text)
    assert res["is_micro"] is True
    assert "MICRO_FRAGMENT" in res["issues"]


def test_validate_boundary_issues():
    # Ends without terminal punctuation, starts lowercase
    text = "this is an incomplete sentence that does not finish cleanly"
    res = validate_chunk_content(text)
    assert "UNTERMINATED_BOUNDARY" in res["issues"]
    assert "MID_SENTENCE_START" in res["issues"]


def test_validate_lone_heading():
    text = "# Annual Leave Entitlement"
    res = validate_chunk_content(text)
    assert "LONE_HEADING" in res["issues"]


def test_auto_normalize_edited_chunk():
    raw = "Section: Leave\n\n.... 1. Overview ........\n\nAll full-time staff get paid leave."
    meta = {"source_filename": "Handbook.docx", "section_heading": "Leave"}
    clean_txt, clean_meta, changes = auto_normalize_edited_chunk(raw, meta)
    assert "...." not in clean_txt
    assert isinstance(clean_txt, str)
    assert len(clean_txt) > 0


def test_stage_and_remove_chunk_review(tmp_path, monkeypatch):
    test_staging_file = tmp_path / "staged_chunks_test.json"
    monkeypatch.setattr("sandbox.engine.chunk_editor.STAGED_REVIEW_FILE_PATH", test_staging_file)

    chunk_id = "test_bad_chunk_001"
    stage_chunk_for_review(
        chunk_id=chunk_id,
        text="bad incomplete fragment",
        metadata={"document_id": "DOC-99"},
        quality_issues=["MICRO_FRAGMENT", "UNTERMINATED_BOUNDARY"],
    )

    staged = load_staged_chunks_for_review()
    assert chunk_id in staged
    assert staged[chunk_id]["text"] == "bad incomplete fragment"
    assert "MICRO_FRAGMENT" in staged[chunk_id]["quality_issues"]

    # Remove
    assert remove_from_staged_review(chunk_id) is True
    staged_after = load_staged_chunks_for_review()
    assert chunk_id not in staged_after


def test_edit_and_ingest_rejects_oversized_chunk():
    oversized_text = " ".join(["token"] * 300)
    success, msg, val = edit_and_ingest_chunk("oversized_001", oversized_text)
    assert success is False
    assert "exceeds 245-token ceiling" in msg

