import logging
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core import mongo_settings
from app.db.mongodb import MongoDBClient
from app.domain.entities.access_models import RoleModel

logger = logging.getLogger(__name__)


def role_to_doc(role: RoleModel) -> Dict[str, Any]:
    return {
        "name": role.name,
        "code": role.code,
        "description": role.description,
        "is_system": role.is_system,
        "created_at": role.created_at,
    }


def doc_to_role(doc: Dict[str, Any]) -> RoleModel:
    return RoleModel(
        name=doc.get("name", doc.get("code", "")),
        code=doc.get("code", ""),
        description=doc.get("description"),
        is_system=bool(doc.get("is_system", False)),
        created_at=doc.get("created_at"),
    )


class RolesRepository:
    """Data access layer for the ``roles`` collection."""

    def __init__(self, database=None, collection_name: str | None = None):
        self._db = database if database is not None else MongoDBClient.get_db()
        self.collection = self._db[
            collection_name or mongo_settings.ROLES_COLLECTION
        ]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self.collection.create_index([("code", ASCENDING)], unique=True)

    def create(self, role: RoleModel) -> str:
        try:
            result = self.collection.insert_one(role_to_doc(role))
            return str(result.inserted_id)
        except DuplicateKeyError:
            raise ValueError(f"Role with code '{role.code}' already exists")
        except PyMongoError as exc:
            logger.exception("Failed to create role '%s'", role.code)
            raise

    def get_by_code(self, code: str) -> Optional[RoleModel]:
        doc = self.collection.find_one({"code": code})
        return doc_to_role(doc) if doc else None

    def get_by_id(self, role_id: str) -> Optional[RoleModel]:
        try:
            doc = self.collection.find_one({"_id": ObjectId(role_id)})
        except (InvalidId, PyMongoError):
            return None
        return doc_to_role(doc) if doc else None

    def list_all(self) -> List[RoleModel]:
        docs = self.collection.find().sort("code", ASCENDING)
        return [doc_to_role(doc) for doc in docs]

    def exists(self, code: str) -> bool:
        return self.collection.count_documents({"code": code}) > 0

    def update(self, role_id: str, updates: Dict[str, Any]) -> bool:
        try:
            result = self.collection.update_one(
                {"_id": ObjectId(role_id)},
                {"$set": updates},
            )
            return result.modified_count > 0
        except (InvalidId, PyMongoError):
            return False

    def delete(self, role_id: str) -> bool:
        try:
            result = self.collection.delete_one({"_id": ObjectId(role_id)})
            return result.deleted_count > 0
        except (InvalidId, PyMongoError):
            return False


def seed_default_roles(repository: RolesRepository | None = None) -> List[str]:
    """Insert the four standard roles if they are missing.

    Returns the list of role codes ensured to exist.
    """
    repo = repository or RolesRepository()
    ensured: List[str] = []
    for code, display_name in mongo_settings.DEFAULT_ROLES.items():
        if not repo.exists(code):
            repo.create(
                RoleModel(
                    code=code,
                    name=display_name,
                    is_system=True,
                )
            )
        ensured.append(code)
    return ensured