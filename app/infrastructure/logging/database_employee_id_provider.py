import logging
from typing import Any, Callable, Optional

from app.domain.services.employee_id_provider import EmployeeIdProvider

logger = logging.getLogger(__name__)


class DatabaseEmployeeIdProvider(EmployeeIdProvider):
    """
    Resolves real employee or user identifiers from the database persistence layer.
    Falls back gracefully when unauthenticated, when lookup fails, or in tests.
    """

    DEFAULT_FALLBACK: str = "anonymous"

    def __init__(
        self,
        unit_of_work_factory: Optional[Callable] = None,
        fallback_id: str = DEFAULT_FALLBACK,
    ) -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self.fallback_id = fallback_id

    def get_employee_id(self, user_context: Optional[Any] = None) -> str:
        if not user_context:
            return self.fallback_id

        # 1. Direct attribute or dictionary extraction
        if isinstance(user_context, dict):
            emp_id = user_context.get("employee_id")
            if emp_id:
                return str(emp_id)
            candidate_uid = user_context.get("uid")
        else:
            emp_id = getattr(user_context, "employee_id", None)
            if emp_id:
                return str(emp_id)
            candidate_uid = getattr(user_context, "uid", None)

        if candidate_uid is None and isinstance(user_context, str):
            candidate_uid = user_context

        # 2. Database lookup via Unit of Work
        if candidate_uid and self.unit_of_work_factory is not None:
            try:
                with self.unit_of_work_factory() as uow:
                    user = uow.users.get_by_uid(str(candidate_uid))
                    if user is None and hasattr(uow.users, "get_by_employee_id"):
                        user = uow.users.get_by_employee_id(str(candidate_uid))

                    if user is not None:
                        resolved = user.employee_id or user.uid
                        if resolved:
                            return str(resolved)
            except Exception as exc:
                logger.warning(
                    "DatabaseEmployeeIdProvider failed to lookup user %r: %s",
                    candidate_uid,
                    exc,
                )

        # 3. Fallback to candidate uid string if provided, else fallback_id
        if candidate_uid:
            return str(candidate_uid)

        return self.fallback_id
