import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.settings import (
    FAQ_COLLECTION_NAME,
    FAQ_DATABASE_NAME,
    MONGODB_URI,
    MONGODB_SERVER_SELECTION_TIMEOUT_MS,
)

logger = logging.getLogger(__name__)


class MongoFAQStore:
    """Persist grounded question-and-answer pairs in MongoDB when configured."""

    def __init__(
        self,
        uri: str = MONGODB_URI,
        database_name: str = FAQ_DATABASE_NAME,
        collection_name: str = FAQ_COLLECTION_NAME,
        server_selection_timeout_ms: int = MONGODB_SERVER_SELECTION_TIMEOUT_MS,
        client: Optional[Any] = None,
    ):
        self.enabled = bool(uri) or client is not None
        self.collection = None
        if not self.enabled:
            return

        if client is None:
            from pymongo import MongoClient

            client = MongoClient(
                uri,
                serverSelectionTimeoutMS=server_selection_timeout_ms,
            )

        self.collection = client[database_name][collection_name]
        self.collection.create_index("question_key", unique=True)

    @staticmethod
    def _question_key(question: str) -> str:
        return re.sub(r"\s+", " ", question.strip()).casefold()

    def save(
        self,
        question: str,
        answer: str,
        citations: List[Dict[str, Any]],
    ) -> None:
        if not self.enabled or self.collection is None:
            return

        now = datetime.now(timezone.utc)
        document = {
            "question": question.strip(),
            "question_key": self._question_key(question),
            "answer": answer,
            "citations": citations,
            "updated_at": now,
        }

        try:
            self.collection.update_one(
                {"question_key": document["question_key"]},
                {
                    "$set": document,
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
        except Exception as error:
            logger.warning("Could not persist FAQ response: %s", error)