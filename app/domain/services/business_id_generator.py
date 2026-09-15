"""Centralized, configurable, concurrency-safe business ID generation.

Business IDs follow the predictable format ``<prefix>-<NNN>`` with a
zero-padded three-digit suffix, e.g. ``MSS-001``, ``DEPT-001``, ``PROJ-001``,
``DOC-001`` and ``NEX-PROJ-001``.

Suffixes are allocated from a persistent, monotonic per-key counter stored in
the ``business_id_sequences`` table (see ``SequenceRepository``). Allocation is
a single atomic ``UPDATE ... RETURNING`` statement, so concurrent writers can
never observe the same value. The counter is only ever increased and is
independent of the rows an ID refers to, so numbers are never reused after the
underlying entity is deleted.

Legacy bootstrap: when no counter row exists for a sequence key, the generator
seeds the counter from the highest existing numeric suffix before the first
allocation. Once a counter row exists it is authoritative and is never
recomputed from the data tables, which is what guarantees continue-after-delete
behaviour.
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
    """Registry of per-family sequence configuration.

    Spread prefixes or counter keys across families, then call ``next`` inside
    a unit of work to produce the next human-readable ID.
    """

    def __init__(self):
        self._sequences: dict[str, BusinessIdSequence] = {}
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
        if uow.sequences.get(sequence.key) is None:
            uow.sequences.initialize(
                sequence.key,
                sequence.prefix,
                highest_existing_suffix(sequence.existing_ids(uow), sequence.prefix),
            )
        value = uow.sequences.allocate(sequence.key)
        return f"{sequence.prefix}-{value:03d}"


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