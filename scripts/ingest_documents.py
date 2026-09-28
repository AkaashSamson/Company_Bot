import os
from pathlib import Path

from dotenv import load_dotenv

from app.core.settings import BASE_DIR, COLLECTION_NAME
from app.infrastructure.document.local_document_loader import LocalDocumentLoader
from app.infrastructure.document.processor_factory import build_document_processor
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.use_cases.ingestion.document_processing import build_chunk_records_from_processed

load_dotenv()


def main():
    documents_dir = os.getenv("DOCUMENTS_DIR", str(BASE_DIR / "input"))
    collection_name = os.getenv("COLLECTION_NAME", COLLECTION_NAME)
    persist_directory = str(BASE_DIR / ".chroma")
    project_id = os.getenv("DEFAULT_PROJECT_ID")

    # Built here, as for the API path, so the batch script never constructs a
    # parser itself and both entry points ingest through the same port.
    processor = build_document_processor()
    loader = LocalDocumentLoader(documents_dir, processor=processor)
    files = loader.list_documents()
    if not files:
        print("No documents found.")
        return

    store = ChromaVectorStore(collection_name=collection_name, persist_directory=persist_directory)

    for file_path in files:
        path = Path(file_path)
        if not processor.supports(path.name):
            supported = ", ".join(sorted(processor.supported_extensions()))
            print(f"Skipped {path.name}: unsupported type (supported: {supported})")
            continue

        processed = processor.process(path.read_bytes(), path.name)
        records = build_chunk_records_from_processed(
            processed,
            document_id=path.stem,
            project_id=project_id,
            source=path.name,
        )
        if not records:
            continue

        store.add_documents(records)
        print(f"Processed {path.name}: {len(records)} chunks")

    print(f"Stored documents in collection: {collection_name}")


if __name__ == "__main__":
    main()
