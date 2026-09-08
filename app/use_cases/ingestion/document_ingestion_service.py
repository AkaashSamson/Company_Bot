from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from app.core.settings import BASE_DIR, COLLECTION_NAME
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.use_cases.ingestion.document_processing import (
    chunk_text,
    extract_text_from_document,
)


@dataclass
class IngestionResult:
    source: str
    chunks_count: int
    already_existed: bool
    stored_in: str
    status: str


class DocumentIngestionService:
    """Reusable single-document ingestion pipeline.

    The pipeline mirrors the batch flow used by ``scripts/ingest_documents.py``:
    extract text, clean and chunk it, embed, and persist into the shared Chroma
    collection. Keeping this logic in a service allows both the CLI batch
    script and the HTTP upload endpoint to reuse the exact same processing
    path.
    """

    def __init__(
        self,
        collection_name: str = COLLECTION_NAME,
        persist_directory: Optional[str] = None,
        chunk_size: int = 500,
    ):
        self.store = ChromaVectorStore(
            collection_name=collection_name,
            persist_directory=persist_directory or str(BASE_DIR / ".chroma"),
        )
        self.chunk_size = chunk_size

    def ingest(
        self,
        file_path: str,
        source_name: Optional[str] = None,
        overwrite: bool = False,
        section: str = "Policy",
        document_id: Optional[str] = None,
    ) -> IngestionResult:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(file_path)

        source = source_name or path.name
        doc_id = document_id or path.stem

        existing_chunks = self.store.count_by_source(source)
        if existing_chunks > 0 and not overwrite:
            return IngestionResult(
                source=source,
                chunks_count=existing_chunks,
                already_existed=True,
                stored_in=self.store.persist_directory,
                status="duplicate",
            )

        text = extract_text_from_document(str(path))
        if not text.strip():
            raise ValueError(f"No extractable text found in {source}")

        chunks = chunk_text(text, chunk_size=self.chunk_size)
        if not chunks:
            raise ValueError(f"Document {source} produced no text chunks")

        if existing_chunks > 0 and overwrite:
            self.store.delete_by_source(source)

        records: List[Dict] = []
        for index, chunk in enumerate(chunks):
            records.append({
                "id": f"{path.stem}-{index}",
                "text": chunk,
                "metadata": {
                    "source": source,
                    "document_id": doc_id,
                    "chunk_index": index,
                    "section": section,
                },
            })

        self.store.add_documents(records)

        return IngestionResult(
            source=source,
            chunks_count=len(chunks),
            already_existed=False,
            stored_in=self.store.persist_directory,
            status="stored",
        )
