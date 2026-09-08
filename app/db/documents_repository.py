from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core import mongo_settings
from app.db.mongodb import MongoDBClient
from app.db.sequences import next_document_id
from app.domain.entities.access_models import (
    AccessPolicy,
    DocumentModel,
)


def document_to_doc(doc_model: DocumentModel) -> Dict[str, Any]:
    return {
        "document_id": doc_model.document_id,
        "filename": doc_model.filename,
        "owner_user_id": doc_model.owner_user_id,
        "status": doc_model.status,
        "allowed_role_codes": doc_model.allowed_role_codes,
        "allowed_user_ids": doc_model.allowed_user_ids,
        "metadata": doc_model.metadata,
        "created_at": doc_model.created_at,
        "updated_at": doc_model.updated_at,
    }


def doc_to_document(doc: Dict[str, Any]) -> DocumentModel:
    return DocumentModel(
        document_id=doc.get("document_id", ""),
        filename=doc.get("filename", ""),
        owner_user_id=str(doc.get("owner_user_id", "")),
        status=doc.get("status", "active"),
        allowed_role_codes=doc.get("allowed_role_codes", []) or [],
        allowed_user_ids=doc.get("allowed_user_ids", []) or [],
        metadata=doc.get("metadata", {}) or {},
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


class DocumentNotFoundError(Exception):
    """Raised when a requested document does not exist."""


class DocumentsRepository:
    """Data access layer for the ``documents`` collection.

    Each document record stores its own access policy (owner, permitted role
    codes, and permitted employee ids). This keeps access decisions local to
    the document and avoids a separate join collection for the MVP.
    """

    def __init__(self, database=None, collection_name: str | None = None):
        self._db = database if database is not None else MongoDBClient.get_db()
        self.collection = self._db[
            collection_name or mongo_settings.DOCUMENTS_COLLECTION
        ]
        self._ensure_indexes()

    @property
    def database(self):
        return self._db

    def _ensure_indexes(self) -> None:
        self.collection.create_index([("document_id", ASCENDING)], unique=True)
        self.collection.create_index([("filename", ASCENDING)], unique=True)
        self.collection.create_index([("owner_user_id", ASCENDING)])
        self.collection.create_index([("allowed_role_codes", ASCENDING)])
        self.collection.create_index([("allowed_user_ids", ASCENDING)])
        self.collection.create_index([("status", ASCENDING)])

    def create(self, doc_model: DocumentModel) -> str:
        if not doc_model.document_id:
            doc_model.document_id = next_document_id(self._db)
        try:
            self.collection.insert_one(document_to_doc(doc_model))
            return doc_model.document_id
        except DuplicateKeyError:
            raise ValueError(
                f"A document with id '{doc_model.document_id}' or "
                f"filename '{doc_model.filename}' already exists"
            )

    def get_by_document_id(self, document_id: str) -> Optional[DocumentModel]:
        doc = self.collection.find_one({"document_id": document_id})
        return doc_to_document(doc) if doc else None

    def get_by_id(self, internal_id: str) -> Optional[DocumentModel]:
        try:
            doc = self.collection.find_one({"_id": ObjectId(internal_id)})
        except (InvalidId, PyMongoError):
            return None
        return doc_to_document(doc) if doc else None

    def get_by_filename(self, filename: str) -> Optional[DocumentModel]:
        doc = self.collection.find_one({"filename": filename})
        return doc_to_document(doc) if doc else None

    def exists(self, filename: str) -> bool:
        return self.collection.count_documents({"filename": filename}) > 0

    def list_documents(
        self,
        owner_user_id: str | None = None,
        allowed_user_ids: List[str] | None = None,
        allowed_role_codes: List[str] | None = None,
        status: str = "active",
    ) -> List[DocumentModel]:
        query: Dict[str, Any] = {"status": status}
        if owner_user_id:
            query["owner_user_id"] = owner_user_id
        if allowed_role_codes:
            query["allowed_role_codes"] = {"$in": allowed_role_codes}
        if allowed_user_ids:
            query["allowed_user_ids"] = {
                "$in": allowed_user_ids,
            }
        docs = self.collection.find(query).sort("created_at", DESCENDING)
        return [doc_to_document(doc) for doc in docs]

    def list_accessible(
        self,
        employee_id: str,
        role_code: Optional[str],
        status: str = "active",
    ) -> List[DocumentModel]:
        """Return documents this employee may read.

        Access rule (MVP): the owner, an employee explicitly listed in
        ``allowed_user_ids``, or a user whose ``role_code`` is listed in
        ``allowed_role_codes`` can access the document.
        """
        clauses: List[Dict[str, Any]] = [
            {"owner_user_id": employee_id},
            {"allowed_user_ids": employee_id},
        ]
        if role_code:
            clauses.append({"allowed_role_codes": role_code})
        query: Dict[str, Any] = {"$or": clauses}
        if status:
            query["status"] = status
        docs = self.collection.find(query).sort("created_at", DESCENDING)
        return [doc_to_document(doc) for doc in docs]

    def update_access(
        self,
        document_id: str,
        allowed_role_codes: List[str],
        allowed_user_ids: List[str],
    ) -> bool:
        try:
            result = self.collection.update_one(
                {"document_id": document_id},
                {
                    "$set": {
                        "allowed_role_codes": allowed_role_codes,
                        "allowed_user_ids": allowed_user_ids,
                        "updated_at": datetime.utcnow(),
                    }
                },
            )
            return result.modified_count > 0
        except (InvalidId, PyMongoError):
            return False

    def get_access_policy(self, document_id: str) -> Optional[AccessPolicy]:
        doc = self.collection.find_one({"document_id": document_id})
        if not doc:
            return None
        return AccessPolicy(
            document_id=document_id,
            owner_user_id=str(doc.get("owner_user_id", "")),
            allowed_role_codes=doc.get("allowed_role_codes", []) or [],
            allowed_user_ids=doc.get("allowed_user_ids", []) or [],
        )

    def delete(self, document_id: str) -> bool:
        try:
            result = self.collection.delete_one({"document_id": document_id})
            return result.deleted_count > 0
        except (InvalidId, PyMongoError):
            return False