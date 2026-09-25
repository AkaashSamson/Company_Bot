from pathlib import Path

import pytest

from app.use_cases.ingestion.document_processing import (
    chunk_text,
    extract_text_from_bytes,
    extract_text_from_document,
)


def test_extract_text_from_nexora_docx():
    doc_path = Path("input/")
    assert doc_path.exists(), "Nexora policy document should exist in input/"

    text = extract_text_from_document(str(doc_path))
    assert "NEXORA TECHNOLOGIES PVT" in text
    assert "Employee Handbook" in text

    chunks = chunk_text(text, chunk_size=400)
    assert len(chunks) >= 1
    assert all(chunk.strip() for chunk in chunks)


def test_extract_text_from_bytes_for_docx():
    doc_path = Path("input/NEXORA TECHNOLOGIES PVT.docx")
    text = extract_text_from_bytes(doc_path.read_bytes(), doc_path.name)
    assert "Employee Handbook" in text


def test_extract_text_from_bytes_for_plain_text():
    text = extract_text_from_bytes("Hello world.\nSecond paragraph.".encode("utf-8"), "notes.txt")
    assert "Hello world" in text


def test_extract_text_from_bytes_unsupported_extension():
    with pytest.raises(ValueError):
        extract_text_from_bytes(b"content", "policy.pdf")
