from datetime import datetime, timezone
from typing import Callable

from app.domain.entities.organization_models import ProjectGrant
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine, PRINCIPAL_TYPES
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError


def utc_now():
    return datetime.now(timezone.utc)


class ProjectAccessService:
    """Grant/revoke access to a project for a role or a specific user.

    Project access is an alternative to being an active member: the grants
    are resolved by the authorization engine whenever project/document scope
    is computed. Only users who may manage the project itself can change
    access grants.
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
    def _require_project_manager(authorization, actor_principal, uow, project_id):
        if not authorization.can_manage_project(actor_principal, project_id):
            raise ForbiddenError("Project is outside manager scope")

    def grant(self, actor_principal, project_id, principal_type, role_id=None, user_id=None):
        with self.unit_of_work_factory() as uow:
            self._require_active(uow, actor_principal.uid)
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("Project not found")
            self._require_project_manager(self.authorization, actor_principal, uow, project_id)
            self._check_principal_target(uow, principal_type, role_id, user_id)
            if uow.project_grants.get(project_id, principal_type, role_id=role_id, user_id=user_id) is not None:
                raise ConflictError("Grant already exists")
            grant = ProjectGrant(
                project_id,
                principal_type,
                role_id=role_id,
                user_id=user_id,
                granted_by_uid=actor_principal.uid,
                status="active",
                granted_at=utc_now(),
            )
            grant = uow.project_grants.save(grant)
            uow.commit()
            return grant

    def list(self, actor_principal, project_id):
        with self.unit_of_work_factory() as uow:
            self._require_active(uow, actor_principal.uid)
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("Project not found")
            self._require_project_manager(self.authorization, actor_principal, uow, project_id)
            return list(uow.project_grants.list_for_project(project_id))

    def revoke(self, actor_principal, grant_id):
        with self.unit_of_work_factory() as uow:
            self._require_active(uow, actor_principal.uid)
            grant = uow.project_grants.get_by_id(grant_id)
            if grant is None:
                raise NotFoundError("Project grant not found")
            self._require_project_manager(self.authorization, actor_principal, uow, grant.project_id)
            uow.project_grants.delete(grant_id)
            uow.commit()