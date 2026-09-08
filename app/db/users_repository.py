from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core import mongo_settings
from app.db.mongodb import MongoDBClient
from app.db.roles_repository import RolesRepository
from app.domain.entities.access_models import UserModel


def user_to_doc(user: UserModel) -> Dict[str, Any]:
    return {
        "employee_id": user.employee_id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "password_hash": user.password_hash,
        "role_code": user.role_code,
        "is_active": user.is_active,
        "extra": user.extra,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def doc_to_user(doc: Dict[str, Any]) -> UserModel:
    return UserModel(
        employee_id=doc.get("employee_id", ""),
        first_name=doc.get("first_name", ""),
        last_name=doc.get("last_name", ""),
        email=doc.get("email", ""),
        password_hash=doc.get("password_hash", ""),
        role_code=doc.get("role_code", ""),
        is_active=bool(doc.get("is_active", True)),
        extra=doc.get("extra", {}) or {},
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


class UserNotFoundError(Exception):
    """Raised when a requested user does not exist."""


class UsersRepository:
    """Data access layer for the ``users`` collection."""

    def __init__(self, database=None, collection_name: str | None = None):
        self._db = database if database is not None else MongoDBClient.get_db()
        self.collection = self._db[
            collection_name or mongo_settings.USERS_COLLECTION
        ]
        self._roles = RolesRepository(database=self._db)
        self._ensure_indexes()

    @property
    def database(self):
        return self._db

    def _ensure_indexes(self) -> None:
        self.collection.create_index([("employee_id", ASCENDING)], unique=True)
        self.collection.create_index([("email", ASCENDING)], unique=True)
        self.collection.create_index([("role_code", ASCENDING)])

    def create(self, user: UserModel) -> str:
        if not self._roles.exists(user.role_code):
            raise ValueError(f"Role '{user.role_code}' does not exist")
        try:
            self.collection.insert_one(user_to_doc(user))
            return user.employee_id
        except DuplicateKeyError:
            raise ValueError(
                f"User with employee id '{user.employee_id}' or email "
                f"'{user.email}' already exists"
            )
        except PyMongoError as exc:
            raise

    def get_by_employee_id(self, employee_id: str) -> Optional[UserModel]:
        doc = self.collection.find_one({"employee_id": employee_id})
        return doc_to_user(doc) if doc else None

    def get_by_email(self, email: str) -> Optional[UserModel]:
        doc = self.collection.find_one({"email": email})
        return doc_to_user(doc) if doc else None

    def get_by_id(self, user_id: str) -> Optional[UserModel]:
        try:
            doc = self.collection.find_one({"_id": ObjectId(user_id)})
        except (InvalidId, PyMongoError):
            return None
        return doc_to_user(doc) if doc else None

    def list_users(self, role_code: str | None = None) -> List[UserModel]:
        query = {"role_code": role_code} if role_code else {}
        docs = self.collection.find(query).sort("employee_id", ASCENDING)
        return [doc_to_user(doc) for doc in docs]

    def role_of(self, employee_id: str) -> Optional[str]:
        user = self.get_by_employee_id(employee_id)
        return user.role_code if user else None

    def update(self, employee_id: str, updates: Dict[str, Any]) -> bool:
        updates["updated_at"] = datetime.utcnow()
        try:
            result = self.collection.update_one(
                {"employee_id": employee_id},
                {"$set": updates},
            )
            return result.modified_count > 0
        except (InvalidId, PyMongoError):
            return False

    def set_active(self, employee_id: str, is_active: bool) -> bool:
        return self.update(employee_id, {"is_active": is_active})