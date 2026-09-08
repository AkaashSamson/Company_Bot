from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError
from pymongo.collection import Collection

from app.core import mongo_settings


class MongoConnectionError(Exception):
    """Raised when MongoDB cannot be reached or initialized."""


class MongoDBClient:
    """Singleton wrapper around a pymongo client.

    The client is created lazily on first use and reused for the lifetime of
    the process. Repositories depend on this class (or directly on a
    ``pymongo.database.Database``) so that the connection details live in a
    single place and are easy to replace or mock in tests.
    """

    _client: Optional[MongoClient] = None
    _db: Optional[Database] = None

    @classmethod
    def get_client(cls) -> MongoClient:
        if cls._client is None:
            try:
                cls._client = MongoClient(
                    mongo_settings.MONGODB_URI,
                    serverSelectionTimeoutMS=5000,
                )
            except PyMongoError as exc:
                raise MongoConnectionError(
                    f"Failed to create MongoDB client: {exc}"
                ) from exc
        return cls._client

    @classmethod
    def get_db(cls) -> Database:
        if cls._db is None:
            try:
                cls._db = cls.get_client()[mongo_settings.MONGODB_DB_NAME]
            except PyMongoError as exc:
                raise MongoConnectionError(
                    f"Failed to access database '{mongo_settings.MONGODB_DB_NAME}': {exc}"
                ) from exc
        return cls._db

    @classmethod
    def get_collection(cls, name: str) -> Collection:
        return cls.get_db()[name]

    @classmethod
    def ping(cls) -> bool:
        """Return True if MongoDB is reachable."""
        try:
            cls.get_client().admin.command("ping")
            return True
        except PyMongoError:
            return False

    @classmethod
    def close(cls) -> None:
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            cls._db = None
