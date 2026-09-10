from abc import ABC, abstractmethod
from typing import Any, Optional


class EmployeeIdProvider(ABC):
    """
    Replaceable abstraction for resolving employee identity.

    This interface serves as the replacement boundary between the temporary
    mock identity provider and future trusted database or authentication-backed
    employee identity providers.
    """

    @abstractmethod
    def get_employee_id(self, user_context: Optional[Any] = None) -> str:
        """
        Return the employee ID associated with the authenticated user context.

        Args:
            user_context: Optional user or authentication context used by
                trusted providers to look up employee identity.

        Returns:
            The resolved employee ID string.
        """
        pass
