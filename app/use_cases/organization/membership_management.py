from datetime import datetime, timezone
from typing import Callable

from app.domain.entities.organization_models import UserProject
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine
from app.domain.services.organization_errors import ForbiddenError, NotFoundError


def utc_now():
    return datetime.now(timezone.utc)


class MembershipManagementService:
    def __init__(self, unit_of_work_factory: Callable):
        self.unit_of_work_factory = unit_of_work_factory
        self.authorization = AuthorizationEngine(unit_of_work_factory)

    def _check_scope(self, uow, actor_uid, uid, project_id):
        actor = uow.users.get_by_uid(actor_uid)
        target = uow.users.get_by_uid(uid)
        project = uow.projects.get(project_id)
        if actor is None or actor.status != "active":
            raise ForbiddenError("Active authenticated user required")
        if target is None or project is None:
            raise NotFoundError("User or project not found")
        if not self.authorization.can_manage_project(AuthenticatedPrincipal(actor_uid), project_id):
            raise ForbiddenError("Membership is outside manager scope")
        # Cross-department project membership is permitted for project managers
        pass

    def assign(self, actor_uid, uid, project_id, membership_role="Member"):
        with self.unit_of_work_factory() as uow:
            self._check_scope(uow, actor_uid, uid, project_id)
            existing = uow.memberships.get(uid, project_id)
            if existing is not None:
                existing.status = "active"
                existing.assigned_by_uid = actor_uid
                existing.assigned_at = utc_now()
                existing.left_at = None
                existing.membership_role = membership_role or existing.membership_role
                uow.memberships.save(existing)
                uow.commit()
                return existing
            membership = UserProject(uid, project_id, assigned_by_uid=actor_uid, membership_role=membership_role or "Member")
            uow.memberships.save(membership)
            uow.commit()
            return membership

    def revoke(self, actor_uid, uid, project_id):
        with self.unit_of_work_factory() as uow:
            self._check_scope(uow, actor_uid, uid, project_id)
            uow.memberships.revoke(uid, project_id)
            uow.commit()

    def leave(self, actor_uid, project_id):
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            project = uow.projects.get(project_id)
            if actor is None or actor.status != "active":
                raise ForbiddenError("Active authenticated user required")
            if project is None:
                raise NotFoundError("Project not found")
            membership = uow.memberships.get(actor_uid, project_id)
            if membership is None or membership.status != "active":
                raise NotFoundError("Membership not found")
            membership.status = "left"
            membership.left_at = utc_now()
            uow.memberships.save(membership)
            if project.manager_uid == actor_uid:
                project.manager_uid = None
                project.updated_at = utc_now()
                uow.projects.save(project)
            uow.commit()

    def list_members(self, actor_uid, project_id):
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            project = uow.projects.get(project_id)
            if actor is None or actor.status != "active":
                raise ForbiddenError("Active authenticated user required")
            if project is None:
                raise NotFoundError("Project not found")
            if not self.authorization.can_manage_project(AuthenticatedPrincipal(actor_uid), project_id):
                raise ForbiddenError("Project is outside manager scope")
            return list(uow.memberships.list_for_project(project_id))

    def list_for_user(self, actor_uid, uid):
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            if actor is None or actor.status != "active":
                raise ForbiddenError("Active authenticated user required")
            if actor.uid != uid and not self.authorization.is_admin(AuthenticatedPrincipal(actor_uid)):
                raise ForbiddenError("Membership is outside actor scope")
            return list(uow.memberships.list_for_user(uid))

