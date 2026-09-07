import os

from dotenv import load_dotenv

from app.core.settings import BASE_DIR, COLLECTION_NAME
from app.infrastructure.document.local_document_loader import LocalDocumentLoader
from app.use_cases.ingestion.document_ingestion_service import DocumentIngestionService

load_dotenv()


def main():
    documents_dir = os.getenv("DOCUMENTS_DIR", str(BASE_DIR / "input"))
    collection_name = os.getenv("COLLECTION_NAME", COLLECTION_NAME)
    persist_directory = str(BASE_DIR / ".chroma")

    loader = LocalDocumentLoader(documents_dir)
    files = loader.list_documents()
    if not files:
        print("No documents found.")
        return

    service = DocumentIngestionService(
        collection_name=collection_name,
        persist_directory=persist_directory,
    )

    for file_path in files:
        result = service.ingest(file_path)
        if result.already_existed:
            print(f"Already indexed {result.source}: {result.chunks_count} chunks")
        else:
            print(f"Processed {result.source}: {result.chunks_count} chunks")

    print(f"Stored documents in collection: {collection_name}")


if __name__ == "__main__":
    main()
