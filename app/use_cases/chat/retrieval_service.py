from app.core.settings import BASE_DIR, COLLECTION_NAME
from app.infrastructure.vector.chroma_client import ChromaVectorStore


class RetrievalService:
    def __init__(self, collection_name: str = COLLECTION_NAME, persist_directory: str | None = None):
        self.store = ChromaVectorStore(
            collection_name=collection_name,
            persist_directory=persist_directory or str(BASE_DIR / ".chroma"),
        )

    def retrieve(self, query_text: str, top_k: int = 3):
        return self.store.query(query_text, top_k=top_k)
