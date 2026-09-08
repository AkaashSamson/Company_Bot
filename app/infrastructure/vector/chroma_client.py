from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from sentence_transformers import SentenceTransformer


class ChromaVectorStore:
    def __init__(
        self,
        collection_name: str = "hr_policy_docs",
        persist_directory: Optional[str] = None,
    ):
        self.collection_name = collection_name
        self.persist_directory = Path(persist_directory or ".chroma")
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(self.persist_directory))
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    def add_documents(self, documents: List[Dict[str, Any]]) -> None:
        if not documents:
            return

        ids = [str(doc["id"]) for doc in documents]
        texts = [str(doc["text"]) for doc in documents]
        metadatas = [doc.get("metadata", {}) for doc in documents]
        embeddings = self.embedding_model.encode(texts, convert_to_numpy=True).tolist()

        self.collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    def count_by_source(self, source: str) -> int:
        """Return the number of stored chunks tagged with a source file name."""
        result = self.collection.get(where={"source": source})
        return len(result.get("ids", []) or [])

    def delete_by_source(self, source: str) -> int:
        """Delete every chunk tagged with a source file name and return the count."""
        result = self.collection.get(where={"source": source})
        ids = result.get("ids", []) or []
        if ids:
            self.collection.delete(ids=ids)
        return len(ids)

    def query(
        self,
        query_text: str,
        top_k: int = 3,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[dict]:
        if not query_text.strip():
            return []

        query_embedding = self.embedding_model.encode([query_text], convert_to_numpy=True).tolist()[0]
        query_kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where
        result = self.collection.query(**query_kwargs)

        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        if not documents:
            return []

        output: List[dict] = []
        for index, (document, metadata) in enumerate(zip(documents, metadatas)):
            output.append({
                "text": document,
                "metadata": metadata or {},
                "distance": distances[index] if index < len(distances) else None,
            })
        return output
