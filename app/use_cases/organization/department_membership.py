from datetime import datetime, timezone
from typing import Callable

from app.domain.entities.organization_models import DepartmentMember
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine
from app.domain.services.organization_errors import ForbiddenError, NotFoundError


def utc_now():
    return datetime.now(timezone.utc)


MEMBER_BILLABLE_STATUSES = {"billable", "non-billable"}


class DepartmentMembershipService:
    def __init__(self, unit_of_work_factory: Callable):
        self.unit_of_work_factory = unit_of_work_factory
        self.authorization = AuthorizationEngine(unit_of_work_factory)

    def _scope(self, uow, actor_uid, department_id):
        actor = uow.users.get_by_uid(actor_uid)
        if actor is None or actor.status != "active":
            raise ForbiddenError("Active authenticated user required")
        department = uow.departments.get(department_id)
        if department is None:
            raise NotFoundError("Department not found")
        if not self.authorization.can_manage_department(AuthenticatedPrincipal(actor_uid), department_id):
            raise ForbiddenError("Membership is outside manager scope")

    @staticmethod
    def _validate_billable_status(value):
        if value is not None and value not in MEMBER_BILLABLE_STATUSES:
            raise ValueError(f"Invalid billable status: {value!r}. Expected one of {sorted(MEMBER_BILLABLE_STATUSES)}")

    def assign(self, actor_uid, user_id, department_id, billable_status=None, membership_role="Member"):
        self._validate_billable_status(billable_status)
        with self.unit_of_work_factory() as uow:
            self._scope(uow, actor_uid, department_id)
            if uow.users.get_by_uid(user_id) is None:
                raise NotFoundError("User not found")
            existing = uow.department_members.get(user_id, department_id)
            now = utc_now()
            if existing is not None:
                existing.status = "active"
                existing.left_at = None
                existing.membership_role = membership_role
                if billable_status is not None:
                    existing.billable_status = billable_status
                existing.updated_at = now
                uow.department_members.save(existing)
                uow.commit()
                return existing
            member = DepartmentMember(
                user_id, department_id,
                membership_role=membership_role,
                billable_status=billable_status,
                assigned_by_uid=actor_uid,
                status="active",
                assigned_at=now,
            )
            uow.department_members.save(member)
            uow.commit()
            return member

    def list_for_department(self, actor_uid, department_id):
        with self.unit_of_work_factory() as uow:
            self._scope(uow, actor_uid, department_id)
            return list(uow.department_members.list_for_department(department_id))

    def list_for_user(self, actor_uid, user_id):
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            if actor is None or actor.status != "active":
                raise ForbiddenError("Active authenticated user required")
            if actor.uid != user_id and actor.role.casefold() != "admin":
                raise ForbiddenError("Membership is outside actor scope")
            return list(uow.department_members.list_for_user(user_id))

    def update(self, actor_uid, user_id, department_id, changes):
        with self.unit_of_work_factory() as uow:
            self._scope(uow, actor_uid, department_id)
            member = uow.department_members.get(user_id, department_id)
            if member is None:
                raise NotFoundError("Membership not found")
            if "billable_status" in changes:
                value = changes["billable_status"]
                self._validate_billable_status(value)
                member.billable_status = value
            if "membership_role" in changes and changes["membership_role"] is not None:
                member.membership_role = changes["membership_role"]
            if "status" in changes and changes["status"] is not None:
                member.status = changes["status"]
                if member.status == "inactive":
                    if member.left_at is None:
                        member.left_at = utc_now()
                elif member.status == "active":
                    member.left_at = None
            member.updated_at = utc_now()
            uow.department_members.save(member)
            uow.commit()
            return member

    def leave(self, actor_uid, user_id, department_id):
        return self.update(actor_uid, user_id, department_id, {"status": "inactive"})