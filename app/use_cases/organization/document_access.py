from datetime import datetime, timezone
from typing import Callable

from app.domain.entities.organization_models import DocumentGrant
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine, PRINCIPAL_TYPES
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError


def utc_now():
    return datetime.now(timezone.utc)


DOCUMENT_DEFAULT_PERMISSION = "read"


class DocumentAccessService:
    """Grant/revoke read access to a document for a role or a specific user.

    Only users who may manage the document itself (and hold the
    DOCUMENT_MANAGE_ACCESS permission) can change access.
    """

    def __init__(self, unit_of_work_factory: Callable, authorization_engine: AuthorizationEngine | None = None):
        self.unit_of_work_factory = unit_of_work_factory
        self.authorization = authorization_engine or AuthorizationEngine(unit_of_work_factory)

    @staticmethod
    def _require_active(uow, actor_uid):
        actor = uow.users.get_by_uid(actor_uid)
        if actor is None or actor.status != "active":
            raise ForbiddenError("Active authenticated user required")
        return actor

    @staticmethod
    def _check_principal_target(uow, principal_type, role_id, user_id):
        if principal_type not in PRINCIPAL_TYPES:
            raise ValueError("principal_type must be 'role' or 'user'")
        if principal_type == "role":
            if role_id is None or user_id is not None:
                raise ValueError("A role grant requires role_id and no user_id")
            if uow.roles.get(role_id) is None:
                raise NotFoundError("Role not found")
        else:
            if user_id is None or role_id is not None:
                raise ValueError("A user grant requires user_id and no role_id")
            if uow.users.get_by_uid(user_id) is None:
                raise NotFoundError("User not found")

    @staticmethod
    def _require_document_manager(authorization, actor_principal, uow, document_id):
        if not authorization.can(actor_principal, "manage_document_access"):
            raise ForbiddenError("Missing required permission: DOCUMENT_MANAGE_ACCESS")
        if not authorization.can_manage_document(actor_principal, document_id):
            raise ForbiddenError("Document access is outside manager scope")

    def grant(self, actor_principal, document_id, principal_type, role_id=None, user_id=None, permission=DOCUMENT_DEFAULT_PERMISSION):
        with self.unit_of_work_factory() as uow:
            self._require_active(uow, actor_principal.uid)
            document = uow.documents.get(document_id)
            if document is None:
                raise NotFoundError("Document not found")
            self._require_document_manager(self.authorization, actor_principal, uow, document_id)
            self._check_principal_target(uow, principal_type, role_id, user_id)
            if hasattr(uow, "document_grants"):
                existing = [
                    g for g in uow.document_grants.for_document(document_id)
                    if g.principal_type == principal_type and g.role_id == role_id and g.user_id == user_id
                ]
                if existing:
                    raise ConflictError("Grant already exists")
                grant = DocumentGrant(
                    document_id,
                    principal_type,
                    permission=permission or DOCUMENT_DEFAULT_PERMISSION,
                    role_id=role_id,
                    user_id=user_id,
                    granted_by_uid=actor_principal.uid,
                    status="active",
                    granted_at=utc_now(),
                )
                grant = uow.document_grants.save(grant)
            else:
                grant = DocumentGrant(
                    document_id,
                    principal_type,
                    permission=permission or DOCUMENT_DEFAULT_PERMISSION,
                    role_id=role_id,
                    user_id=user_id,
                    granted_by_uid=actor_principal.uid,
                    status="active",
                    granted_at=utc_now(),
                )
            uow.commit()
            return grant

    def list(self, actor_principal, document_id):
        with self.unit_of_work_factory() as uow:
            self._require_active(uow, actor_principal.uid)
            document = uow.documents.get(document_id)
            if document is None:
                raise NotFoundError("Document not found")
            self._require_document_manager(self.authorization, actor_principal, uow, document_id)
            if hasattr(uow, "document_grants"):
                return list(uow.document_grants.for_document(document_id))
            return []

    def revoke(self, actor_principal, grant_id):
        with self.unit_of_work_factory() as uow:
            self._require_active(uow, actor_principal.uid)
            if hasattr(uow, "document_grants"):
                grant = uow.document_grants.get(grant_id)
                if grant is None:
                    raise NotFoundError("Document grant not found")
                self._require_document_manager(self.authorization, actor_principal, uow, grant.document_id)
                uow.document_grants.delete(grant_id)
                uow.commit()