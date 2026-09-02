from pathlib import Path

from app.use_cases.ingestion.document_processing import chunk_text, extract_text_from_document


def test_extract_text_from_nexora_docx():
    doc_path = Path("input/NEXORA TECHNOLOGIES PVT.docx")
    assert doc_path.exists(), "Nexora policy document should exist in input/"

    text = extract_text_from_document(str(doc_path))
    assert "NEXORA TECHNOLOGIES PVT" in text
    assert "Employee Handbook" in text

    chunks = chunk_text(text, chunk_size=400)
    assert len(chunks) >= 1
    assert all(chunk.strip() for chunk in chunks)
