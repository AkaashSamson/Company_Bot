import re
from io import BytesIO
from pathlib import Path
from typing import List

from docx import Document

from app.domain.entities.chunk_metadata import build_chunk_metadata
from app.domain.ports.document_processing import ProcessedDocument

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


def build_chunk_records_from_processed(
    processed: ProcessedDocument,
    document_id: str,
    project_id: str | None = None,
    source: str | None = None,
    file_type: str | None = None,
    version: str | None = None,
) -> list[dict]:
    """Build store-ready chunk records from a port ``ProcessedDocument``.

    The canonical metadata contract is built by
    :func:`build_chunk_metadata`; this function only surrounds it with the
    record envelope the vector store expects and adds the two pre-existing
    non-canonical keys, ``file_type`` and ``version``, which the document
    entity owns and the store has always carried.
    """
    resolved_file_type = (file_type or processed.file_type or "text").lstrip(".")

    records: list[dict] = []
    entries = build_chunk_metadata(
        processed,
        document_id=document_id,
        source_filename=source or document_id,
        project_id=project_id,
    )
    for position, (entry, chunk) in enumerate(zip(entries, processed.chunks)):
        metadata = entry.as_dict()
        metadata.update(entry.as_legacy())
        metadata["file_type"] = resolved_file_type
        metadata["version"] = version or "1.0"
        hierarchy_text = entry.hierarchy_text
        text_with_context = f"{hierarchy_text}\n\n{chunk.text}" if hierarchy_text else chunk.text

        records.append(
            {
                "id": f"{document_id}-{position}",
                "text": text_with_context,
                "metadata": metadata,
            }
        )
    return records


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
