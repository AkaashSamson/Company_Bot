from datetime import datetime, timezone
from typing import Callable

from app.domain.entities.organization_models import UserProject
from app.domain.services.organization_errors import ForbiddenError, NotFoundError


def utc_now():
    return datetime.now(timezone.utc)


class MembershipManagementService:
    def __init__(self, unit_of_work_factory: Callable):
        self.unit_of_work_factory = unit_of_work_factory

    def _check_scope(self, uow, actor_uid, uid, project_id):
        actor = uow.users.get_by_uid(actor_uid)
        target = uow.users.get_by_uid(uid)
        project = uow.projects.get(project_id)
        if actor is None or actor.status != "active":
            raise ForbiddenError("Active authenticated user required")
        if target is None or project is None:
            raise NotFoundError("User or project not found")
        if actor.role.casefold() == "admin":
            return
        if actor.role.casefold() != "manager" or actor.department_id != target.department_id or actor.department_id != project.department_id:
            raise ForbiddenError("Membership is outside manager scope")

    def assign(self, actor_uid, uid, project_id):
        with self.unit_of_work_factory() as uow:
            self._check_scope(uow, actor_uid, uid, project_id)
            existing = uow.memberships.get(uid, project_id)
            if existing is not None:
                if existing.status != "active":
                    existing.status = "active"
                    existing.assigned_by_uid = actor_uid
                    existing.assigned_at = utc_now()
                    uow.memberships.save(existing)
                    uow.commit()
                return existing
            membership = UserProject(uid, project_id, assigned_by_uid=actor_uid)
            uow.memberships.save(membership)
            uow.commit()
            return membership

    def revoke(self, actor_uid, uid, project_id):
        with self.unit_of_work_factory() as uow:
            self._check_scope(uow, actor_uid, uid, project_id)
            uow.memberships.revoke(uid, project_id)
            uow.commit()
