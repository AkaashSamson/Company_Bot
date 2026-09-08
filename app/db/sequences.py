"""Atomic, restart-safe sequence generation backed by a ``counters`` collection.

The counter is incremented with ``find_one_and_update`` (``$inc``) so concurrent
or restarted processes never hand out the same value twice, and IDs are never
recomputed from the number of rows (which would break if users are deactivated
or deleted).

Prefixes, zero-padding and counter names are configurable via environment
settings, so formats such as ``MSS001`` or ``DOC009`` can change later without
touching callers.
"""

from typing import Optional

from pymongo import ReturnDocument

from app.core import mongo_settings
from app.db.mongodb import MongoDBClient

EMPLOYEE_ID_COUNTER = "employee_id"
DOCUMENT_ID_COUNTER = "document_id"


def next_sequence(counter_name: str, database=None) -> int:
    """Return the next integer value for ``counter_name`` (1-based)."""
    db = database if database is not None else MongoDBClient.get_db()
    counters = db[mongo_settings.COUNTERS_COLLECTION]
    result = counters.find_one_and_update(
        {"_id": counter_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(result["seq"])


def prefix_number(prefix: str, sequence: int, min_digits: int) -> str:
    return f"{prefix}{sequence:0{min_digits}d}"


def next_employee_id(database=None) -> str:
    sequence = next_sequence(EMPLOYEE_ID_COUNTER, database)
    return prefix_number(
        mongo_settings.EMPLOYEE_ID_PREFIX,
        sequence,
        mongo_settings.EMPLOYEE_ID_MIN_DIGITS,
    )


def next_document_id(database=None) -> str:
    sequence = next_sequence(DOCUMENT_ID_COUNTER, database)
    return prefix_number(
        mongo_settings.DOCUMENT_ID_PREFIX,
        sequence,
        mongo_settings.DOCUMENT_ID_MIN_DIGITS,
    )


def advance_sequences_past_existing(database=None) -> None:
    """Advance counters past any rows that predate this feature.

    If existing rows were created with fixed IDs (for example ``MSS001``),
    ``next_employee_id`` would otherwise collide with them. This helper moves
    each counter forward past the largest matching id already present.
    """
    db = database if database is not None else MongoDBClient.get_db()
    counters = db[mongo_settings.COUNTERS_COLLECTION]

    users = db[mongo_settings.USERS_COLLECTION]
    _skip_past(
        counters,
        users,
        EMPLOYEE_ID_COUNTER,
        mongo_settings.EMPLOYEE_ID_PREFIX,
    )

    documents = db[mongo_settings.DOCUMENTS_COLLECTION]
    _skip_past(
        counters,
        documents,
        DOCUMENT_ID_COUNTER,
        mongo_settings.DOCUMENT_ID_PREFIX,
    )


def _skip_past(counters, collection, counter_name: str, prefix: str) -> None:
    import re

    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    max_seq = 0
    for doc in collection.find({}, {counter_name: 1, "employee_id": 1, "document_id": 1}):
        value = doc.get("employee_id") or doc.get("document_id")
        match = pattern.match(value or "")
        if match:
            max_seq = max(max_seq, int(match.group(1)))
    if max_seq:
        counters.update_one(
            {"_id": counter_name},
            {"$max": {"seq": max_seq}},
            upsert=True,
        )