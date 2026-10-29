from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import logging

import chromadb
from sentence_transformers import SentenceTransformer

from app.core.settings import BASE_DIR, COLLECTION_NAME, EMBEDDING_MODEL

logger = logging.getLogger("knowlayer.retrieval")


class ChromaVectorStore:
    def __init__(
        self,
        collection_name: str = "hr_policy_docs",
        persist_directory: Optional[str] = None,
    ):
        self.collection_name = collection_name
        self.persist_directory = Path(persist_directory or (BASE_DIR / ".chroma"))
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(self.persist_directory))
        self._collection = None
        self._embedding_model = None

    def refresh_collection(self):
        """Forces refreshing the collection handle from ChromaDB."""
        self._collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        return self._collection

    @property
    def collection(self):
        """Returns the active collection, auto-refreshing if handle is None or stale."""
        if self._collection is None:
            return self.refresh_collection()
        return self._collection

    @collection.setter
    def collection(self, val):
        self._collection = val

    @property
    def embedding_model(self):
        """Lazy load the embedding model to avoid blocking on startup."""
        if self._embedding_model is None:
            self._embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        return self._embedding_model

    @embedding_model.setter
    def embedding_model(self, value):
        self._embedding_model = value

    def delete_document_chunks(self, document_id: str) -> None:
        """Deletes all chunks associated with a specific document_id."""
        if not document_id:
            return
        try:
            self.collection.delete(where={"document_id": document_id})
            logger.info("deleted all existing chunks for document_id %r", document_id)
        except Exception as e:
            if "does not exist" in str(e).lower():
                self.refresh_collection().delete(where={"document_id": document_id})
                return
            logger.warning("failed to delete chunks for document_id %r: %s", document_id, e)

    def add_documents(
        self,
        documents: Optional[List[Any]] = None,
        ids: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        collection_name: Optional[str] = None,
        **kwargs,
    ) -> None:
        if ids is not None and documents is not None and (not documents or isinstance(documents[0], str)):
            # Formatted as (ids=..., documents=[str,...], metadatas=...)
            recs = [
                {"id": cid, "text": doc, "metadata": meta}
                for cid, doc, meta in zip(ids, documents, metadatas or [{}] * len(ids))
            ]
            documents = recs

        if not documents:
            return

        ids_to_add = [str(doc["id"]) for doc in documents]
        texts_to_add = [str(doc["text"]) for doc in documents]

        # Sanitize metadata for ChromaDB (convert tuples/sets to lists or strings)
        cleaned_metadatas = []
        for doc in documents:
            raw_meta = doc.get("metadata", {}) or {}
            clean_m = {}
            for k, v in raw_meta.items():
                if isinstance(v, (list, tuple, set)):
                    clean_m[k] = list(v)
                elif isinstance(v, (str, int, float, bool)) or v is None:
                    clean_m[k] = v
                else:
                    clean_m[k] = str(v)
            cleaned_metadatas.append(clean_m)

        embeddings = self.embedding_model.encode(texts_to_add, convert_to_numpy=True).tolist()

        try:
            self.collection.upsert(
                ids=ids_to_add,
                documents=texts_to_add,
                metadatas=cleaned_metadatas,
                embeddings=embeddings,
            )
        except Exception as e:
            if "does not exist" in str(e).lower():
                self.refresh_collection().upsert(
                    ids=ids_to_add,
                    documents=texts_to_add,
                    metadatas=cleaned_metadatas,
                    embeddings=embeddings,
                )
            else:
                raise
        logger.info(
            "stored %d vectors in collection %r (total=%d)",
            len(ids_to_add),
            self.collection_name,
            self.collection.count(),
        )

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
        try:
            result = self.collection.query(
                **query_kwargs,
            )
        except Exception as e:
            if "does not exist" in str(e).lower():
                result = self.refresh_collection().query(**query_kwargs)
            else:
                raise

        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        ids = result.get("ids", [[]])[0]
        if not documents:
            logger.info("vector query returned 0 candidates for query %r", query_text)
            return []

        logger.info(
            "vector query returned %d candidates for query %r: distances=%s",
            len(documents),
            query_text,
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


class ChromaClient:
    """
    ChromaDB Client providing collection-level persistence and querying.
    Supports both collection-targeted adds and multi-collection persistence.
    """

    def __init__(self, persist_directory: Optional[str] = None):
        self.persist_directory = Path(persist_directory or (BASE_DIR / ".chroma"))
        self._stores: Dict[str, ChromaVectorStore] = {}

    def get_store(self, collection_name: str) -> ChromaVectorStore:
        if collection_name not in self._stores:
            self._stores[collection_name] = ChromaVectorStore(
                collection_name=collection_name,
                persist_directory=str(self.persist_directory),
            )
        return self._stores[collection_name]

    def add_documents(
        self,
        collection_name: Optional[str] = None,
        ids: Optional[List[str]] = None,
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> None:
        """
        Index documents into ChromaDB collection.
        Supports both ChromaClient API (collection_name, ids, documents, metadatas)
        and ChromaVectorStore API (documents as list of dicts).
        """
        c_name = collection_name or kwargs.get("collection") or COLLECTION_NAME
        store = self.get_store(c_name)

        if ids is not None and documents is not None:
            records = [
                {"id": cid, "text": doc, "metadata": meta}
                for cid, doc, meta in zip(ids, documents, metadatas or [{}] * len(ids))
            ]
            store.add_documents(records)
        elif documents is not None and len(documents) > 0 and isinstance(documents[0], dict):
            store.add_documents(documents)
        elif "records" in kwargs:
            store.add_documents(kwargs["records"])
        else:
            logger.warning("add_documents called with no valid documents or ids")
