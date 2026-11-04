from typing import Protocol


class SequenceRepository(Protocol):
    """Persistent, atomic per-key numeric counters for business IDs.

    Each counter is keyed by a stable sequence name (``user``, ``department``,
    ``project``, ``document``). ``allocate`` must be safe to call from
    concurrent transactions and must never return the same value twice.
    """

    def get(self, sequence_key: str) -> int | None:
        """Return the current last allocated value, or None if the sequence has no counter row."""
        ...

    def initialize(self, sequence_key: str, prefix: str, last_value: int) -> None:
        """Create the counter row if missing (used to capture legacy data)."""
        ...

    def allocate(self, sequence_key: str, by: int = 1) -> int:
        """Atomically reserve the next value and return it."""
        ...