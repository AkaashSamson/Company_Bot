from itertools import cycle
from typing import Any, Optional, Sequence
from app.domain.services.employee_id_provider import EmployeeIdProvider


class MockEmployeeIdProvider(EmployeeIdProvider):
    """
    Temporary mock employee-ID provider for development.

    Encapsulates mock employee IDs (MSS001, MSS002, MSS003) and provides
    test identities without requiring database or authentication integration.
    Does NOT trust arbitrary employee_id values passed in user_context.
    """

    DEFAULT_MOCK_IDS: tuple[str, ...] = ("MSS001", "MSS002", "MSS003")

    def __init__(self, mock_ids: Sequence[str] = DEFAULT_MOCK_IDS) -> None:
        if not mock_ids:
            raise ValueError("mock_ids must contain at least one employee ID.")
        self._mock_ids: tuple[str, ...] = tuple(mock_ids)
        self._cycle = cycle(self._mock_ids)

    def get_employee_id(self, user_context: Optional[Any] = None) -> str:
        """
        Return a mock employee ID from the encapsulated test ID set.

        Arbitrary employee_id values supplied via user_context are untrusted
        and rejected. Only recognized identities that match the encapsulated
        mock ID set may be returned; otherwise the next ID in the rotation
        is returned.
        """
        if isinstance(user_context, dict):
            candidate = user_context.get("employee_id")
            if candidate in self._mock_ids:
                return candidate
        elif isinstance(user_context, str) and user_context in self._mock_ids:
            return user_context

        return next(self._cycle)
