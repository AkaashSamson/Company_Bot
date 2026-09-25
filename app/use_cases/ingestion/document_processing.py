import re
from io import BytesIO
from pathlib import Path
from typing import List

from docx import Document


SUPPORTED_EXTENSIONS = {".docx", ".txt", ".md", ".rst", ".csv", ".tsv", ".json"}


def _clean_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 500) -> List[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", cleaned) if part.strip()]
    if not paragraphs:
        paragraphs = [cleaned]

    chunks: List[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            if not current:
                current = paragraph
            elif len(current) + 1 + len(paragraph) <= chunk_size:
                current = f"{current} {paragraph}"
            else:
                chunks.append(current.strip())
                current = paragraph
            continue

        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if not current:
                current = sentence
            elif len(current) + 1 + len(sentence) <= chunk_size:
                current = f"{current} {sentence}"
            else:
                chunks.append(current.strip())
                current = sentence

    if current.strip():
        chunks.append(current.strip())

    final_chunks = [chunk for chunk in chunks if chunk.strip()]
    if not final_chunks:
        return [cleaned[:chunk_size]] if len(cleaned) > chunk_size else [cleaned]
    return final_chunks


def build_chunk_records(
    text: str,
    document_id: str,
    project_id: str | None = None,
    source: str | None = None,
    file_type: str | None = None,
    version: str | None = None,
) -> list[dict]:
    return [
        {
            "id": f"{document_id}-{index}",
            "text": chunk,
            "metadata": {
                "document_id": document_id,
                "project_id": project_id or "unassigned",
                "source": source or document_id,
                "chunk_index": index,
                "file_type": (file_type or "text").lstrip("."),
                "version": version or "1.0",
            },
        }
        for index, chunk in enumerate(chunk_text(text))
    ]


def extract_text_from_bytes(content: bytes, file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()

    if suffix == ".docx":
        document = Document(BytesIO(content))
        paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    paragraphs.append(row_text)
        return "\n\n".join(paragraphs)

    if suffix in {".txt", ".md", ".rst", ".csv", ".tsv", ".json"}:
        return content.decode("utf-8", errors="ignore")

    raise ValueError(f"Unsupported document type: {suffix}")


def extract_text_from_document(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(file_path)

    return extract_text_from_bytes(path.read_bytes(), path.name)
