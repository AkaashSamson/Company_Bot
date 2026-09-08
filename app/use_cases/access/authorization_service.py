from typing import List, Optional

from app.db.documents_repository import DocumentsRepository
from app.db.users_repository import UsersRepository


class AuthorizationError(Exception):
    """Raised when the subject of an authorization inquiry is invalid."""


class AuthorizationService:
    """Resolves which documents an employee is allowed to read.

    This service is the single entry point for document authorization. It
    performs no LLM calls, no chunking and no Streamlit logic: given an
    employee id it returns a deduplicated list of accessible document ids.
    """

    def __init__(
        self,
        users: UsersRepository | None = None,
        documents: DocumentsRepository | None = None,
    ):
        self.users = users or UsersRepository()
        self.documents = documents or DocumentsRepository()

    def get_accessible_document_ids(self, employee_id: str) -> List[str]:
        """Return the deduplicated document ids readable by ``employee_id``.

        Raises ``AuthorizationError`` when the user does not exist or is
        inactive; the caller is expected to treat that as access denied.
        """
        user = self.users.get_by_employee_id(employee_id)
        if user is None:
            raise AuthorizationError(f"User '{employee_id}' does not exist")
        if not user.is_active:
            raise AuthorizationError(f"User '{employee_id}' is deactivated")

        documents = self.documents.list_accessible(
            employee_id=employee_id,
            role_code=user.role_code,
        )
        return list(dict.fromkeys(doc.document_id for doc in documents if doc.document_id))

    def document_ids_authorized(self, employee_id: str, document_ids: List[str]) -> List[str]:
        """Return the subset of ``document_ids`` the employee may read.

        Used as a fail-closed re-check after retrieval so that an authorized
        chunk can never leak an unauthorized document into the LLM context.
        """
        if not document_ids:
            return []
        try:
            accessible = set(self.get_accessible_document_ids(employee_id))
        except AuthorizationError:
            return []
        return [doc_id for doc_id in document_ids if doc_id in accessible]