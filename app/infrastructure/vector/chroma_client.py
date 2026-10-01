from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

import chromadb
from sentence_transformers import SentenceTransformer


logger = logging.getLogger("knowlayer.retrieval")


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
        self._embedding_model = None

    @property
    def embedding_model(self):
        """Lazy load the embedding model to avoid blocking on startup."""
        if self._embedding_model is None:
            self._embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        return self._embedding_model

    @embedding_model.setter
    def embedding_model(self, value):
        self._embedding_model = value

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
        logger.info("stored %d vectors in collection %r (total=%d)", len(ids), self.collection_name, self.collection.count())

    def query(self, query_text: str, top_k: int = 3, project_ids=None, where=None) -> List[dict]:
        if not query_text.strip():
            return []
        if project_ids == []:
            return []

        query_embedding = self.embedding_model.encode([query_text], convert_to_numpy=True).tolist()[0]
        query_kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        filters = []
        if project_ids is not None:
            filters.append({"project_id": {"$in": list(project_ids)}})
            logger.info("vector query with project filter: %s", project_ids)
        if where is not None:
            filters.append(where)
        if len(filters) == 1:
            query_kwargs["where"] = filters[0]
        elif len(filters) > 1:
            query_kwargs["where"] = {"$and": filters}
        result = self.collection.query(
            **query_kwargs,
        )

        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        ids = result.get("ids", [[]])[0]
        if not documents:
            logger.info("vector query returned 0 candidates for query %r", query_text)
            return []

        logger.info(
            "vector query returned %d candidates for query %r: distances=%s",
            len(documents), query_text,
            [round(d, 4) if isinstance(d, (int, float)) else None for d in distances],
        )
        output: List[dict] = []
        for index, (document, metadata) in enumerate(zip(documents, metadatas)):
            meta = metadata or {}
            chunk_id = (
                ids[index]
                if index < len(ids) and ids[index]
                else f"{meta.get('document_id', 'chunk')}-{meta.get('chunk_index', index)}"
            )
            dist = distances[index] if index < len(distances) and isinstance(distances[index], (int, float)) else None
            score = round(1.0 - dist, 4) if dist is not None else 0.0
            output.append({
                "id": chunk_id,
                "text": document,
                "score": score,
                "distance": round(dist, 4) if dist is not None else None,
                "metadata": meta,
            })
        return output
