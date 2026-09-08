from typing import Any, Dict, List, Optional


class AccessControlService:
    """Pure business logic for document access.

    The service knows nothing about MongoDB or ChromaDB. Access is decided from
    an ``AccessPolicy`` (loaded from the ``documents`` collection) and an
    employee identity (``employee_id`` + ``role_code``).

    Access rules (MVP):
      1. The document owner can always read their own document.
      2. An employee whose ``employee_id`` is in ``allowed_user_ids`` can read it.
      3. A user whose role code is in ``allowed_role_codes`` can read it.
      4. Documents with no explicit allow-list remain owner-only.
    """

    @staticmethod
    def can_access(
        policy,
        employee_id: Optional[str],
        role_code: Optional[str],
    ) -> bool:
        if not employee_id:
            return False
        if policy.owner_user_id == employee_id:
            return True
        if employee_id in (policy.allowed_user_ids or []):
            return True
        if role_code and role_code in (policy.allowed_role_codes or []):
            return True
        return False

    @staticmethod
    def build_chroma_where(
        document_ids: Optional[List[str]],
    ) -> Optional[Dict[str, Any]]:
        """Build a Chroma ``where`` filter covering exactly ``document_ids``.

        Returns ``None`` when there is nothing to query and callers must not
        fall back to an unfiltered search.
        """
        if not document_ids:
            return None
        unique_ids = list(dict.fromkeys(document_ids))
        return {"document_id": {"$in": unique_ids}}

    @staticmethod
    def normalize_allow_lists(
        allowed_role_codes: Optional[List[str]],
        allowed_user_ids: Optional[List[str]],
    ) -> Dict[str, List[str]]:
        return {
            "allowed_role_codes": list(
                dict.fromkeys(allowed_role_codes or [])
            ),
            "allowed_user_ids": list(
                dict.fromkeys(allowed_user_ids or [])
            ),
        }