from pathlib import Path

import pytest

from app.infrastructure.document.plaintext_processor import (
    chunk_text,
    extract_text_from_bytes,
)


def test_extract_text_from_nexora_docx():
    doc_path = Path("input/HR_Policy_Manual.docx")
    if not doc_path.exists():
        pytest.skip("HR policy document not present in input/")

    text = extract_text_from_bytes(doc_path.read_bytes(), doc_path.name)
    assert "NEXORA TECHNOLOGIES" in text
    assert "HUMAN RESOURCES POLICY MANUAL" in text

    chunks = chunk_text(text, chunk_size=400)
    assert len(chunks) >= 1
    assert all(chunk.strip() for chunk in chunks)


def test_extract_text_from_bytes_for_docx():
    doc_path = Path("input/HR_Policy_Manual.docx")
    if not doc_path.exists():
        pytest.skip("HR policy document not present in input/")
    text = extract_text_from_bytes(doc_path.read_bytes(), doc_path.name)
    assert "HUMAN RESOURCES POLICY MANUAL" in text


def test_extract_text_from_bytes_for_plain_text():
    text = extract_text_from_bytes("Hello world.\nSecond paragraph.".encode("utf-8"), "notes.txt")
    assert "Hello world" in text


def test_extract_text_from_bytes_unsupported_extension():
    with pytest.raises(ValueError):
        extract_text_from_bytes(b"content", "policy.pdf")
