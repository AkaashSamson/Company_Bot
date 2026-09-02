import os
from pathlib import Path

from dotenv import load_dotenv

from app.core.settings import BASE_DIR, COLLECTION_NAME
from app.infrastructure.document.local_document_loader import LocalDocumentLoader
from app.infrastructure.vector.chroma_client import ChromaVectorStore
from app.use_cases.ingestion.document_processing import chunk_text, extract_text_from_document

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

    store = ChromaVectorStore(collection_name=collection_name, persist_directory=persist_directory)

    for file_path in files:
        text = extract_text_from_document(file_path)
        chunks = chunk_text(text)
        if not chunks:
            continue

        records = []
        for index, chunk in enumerate(chunks):
            records.append({
                "id": f"{Path(file_path).stem}-{index}",
                "text": chunk,
                "metadata": {
                    "source": Path(file_path).name,
                    "chunk_index": index,
                    "section": "Policy",
                },
            })

        store.add_documents(records)
        print(f"Processed {Path(file_path).name}: {len(chunks)} chunks")

    print(f"Stored documents in collection: {collection_name}")


if __name__ == "__main__":
    main()
