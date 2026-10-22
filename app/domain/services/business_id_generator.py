"""Centralized, configurable, concurrency-safe in-memory business ID generation.

Business IDs follow the predictable format ``<prefix>-<NNN>`` with a
zero-padded three-digit suffix, e.g. ``MSS-001``, ``DEPT-001``, ``PROJ-001``,
``DOC-001`` and ``NEX-PROJ-001``.

Suffixes are allocated from a thread-safe in-memory counter initialized lazily
from the highest existing numeric suffix across existing records. Suffixes are
monotonically increasing and never reused after entity deletion. No database
table locking or persistent sequence rows are required.
"""

import threading
from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass(frozen=True)
class BusinessIdSequence:
    """Configuration for one business ID family."""

    key: str
    prefix: str
    existing_ids: Callable[[object], Sequence[str]]


def highest_existing_suffix(existing_ids: Sequence[str], prefix: str) -> int:
    """Highest numeric suffix already issued for ``prefix``, or 0 if none."""
    highest = 0
    separator = f"{prefix}-"
    for raw in existing_ids:
        if not raw or not raw.startswith(separator):
            continue
        suffix = raw[len(separator):]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return highest


class BusinessIdGenerator:
    """Registry of per-family sequence configuration with thread-safe counters."""

    def __init__(self):
        self._sequences: dict[str, BusinessIdSequence] = {}
        self._counters: dict[str, int] = {}
        self._lock = threading.Lock()

    def register(self, sequence: BusinessIdSequence) -> "BusinessIdGenerator":
        with self._lock:
            self._sequences[sequence.key] = sequence
        return self

    def keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._sequences))

    def next(self, uow, key: str) -> str:
        with self._lock:
            sequence = self._sequences[key]
            counters = getattr(uow, "_sequence_counters", None)
            if counters is None:
                try:
                    setattr(uow, "_sequence_counters", {})
                    counters = getattr(uow, "_sequence_counters")
                except Exception:
                    counters = self._counters
            existing_highest = highest_existing_suffix(sequence.existing_ids(uow), sequence.prefix)
            current = max(counters.get(sequence.key, 0), self._counters.get(sequence.key, 0), existing_highest) + 1
            counters[sequence.key] = current
            self._counters[sequence.key] = current
            return f"{sequence.prefix}-{current:03d}"


def build_business_id_generator(
    *,
    user_prefix: str,
    department_prefix: str,
    project_prefix: str,
    document_prefix: str,
) -> BusinessIdGenerator:
    """Build a generator that covers all four business-ID families."""
    return (
        BusinessIdGenerator()
        .register(BusinessIdSequence("user", user_prefix, lambda uow: [u.employee_id for u in uow.users.list()]))
        .register(BusinessIdSequence("department", department_prefix, lambda uow: [d.department_id for d in uow.departments.list()]))
        .register(BusinessIdSequence("project", project_prefix, lambda uow: [p.project_id for p in uow.projects.list()]))
        .register(BusinessIdSequence("document", document_prefix, lambda uow: [d.document_id for d in uow.documents.list()]))
    )
