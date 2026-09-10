from datetime import datetime, timezone
from typing import Callable

from app.domain.entities.organization_models import Department, User
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError


def utc_now():
    return datetime.now(timezone.utc)


class UserManagementService:
    def __init__(self, unit_of_work_factory: Callable):
        self.unit_of_work_factory = unit_of_work_factory

    def create_department(self, actor_uid: str, department_id: str, department_name: str):
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            if actor is None or actor.status != "active" or actor.role.casefold() != "admin":
                raise ForbiddenError("Admin access required")
            if uow.departments.get(department_id):
                raise ConflictError("Department already exists")
            department = Department(department_id, department_name)
            uow.departments.save(department)
            uow.commit()
            return department

    def list_departments(self):
        with self.unit_of_work_factory() as uow:
            return list(uow.departments.list())

    def create_user(self, actor_uid, uid, name, email, role, department_id):
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            if actor is None or actor.status != "active":
                raise ForbiddenError("Active authenticated user required")
            if uow.users.get_by_uid(uid) or uow.users.get_by_email(email):
                raise ConflictError("User UID or email already exists")
            if not uow.departments.get(department_id):
                raise NotFoundError("Department not found")
            if actor.role.casefold() != "admin" and actor.department_id != department_id:
                raise ForbiddenError("User is outside manager scope")
            now = utc_now()
            user = User(uid, name, email, role, department_id, created_at=now, updated_at=now)
            uow.users.save(user)
            uow.commit()
            return user

    def get_user(self, uid, actor_uid=None):
        with self.unit_of_work_factory() as uow:
            user = uow.users.get_by_uid(uid)
            if user is None:
                raise NotFoundError("User not found")
            if actor_uid is not None:
                actor = uow.users.get_by_uid(actor_uid)
                if actor is None or actor.status != "active":
                    raise ForbiddenError("Active authenticated user required")
                if actor.role.casefold() != "admin" and actor.department_id != user.department_id and actor.uid != user.uid:
                    raise ForbiddenError("User is outside manager scope")
            return user

    def list_users(self):
        with self.unit_of_work_factory() as uow:
            return list(uow.users.list())

    def update_user(self, actor_uid, uid, changes):
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            if actor is None or actor.status != "active":
                raise ForbiddenError("Active authenticated user required")
            user = uow.users.get_by_uid(uid)
            if user is None:
                raise NotFoundError("User not found")
            target_department_id = changes.get("department_id") or user.department_id
            if actor.role.casefold() != "admin" and actor.department_id != user.department_id:
                raise ForbiddenError("User is outside manager scope")
            if actor.role.casefold() != "admin" and actor.department_id != target_department_id:
                raise ForbiddenError("User cannot move outside manager scope")
            if changes.get("department_id") and not uow.departments.get(changes["department_id"]):
                raise NotFoundError("Department not found")
            if changes.get("email"):
                existing = uow.users.get_by_email(changes["email"])
                if existing and existing.uid != uid:
                    raise ConflictError("Email already exists")
            for field, value in changes.items():
                if value is not None:
                    setattr(user, field, value)
            user.updated_at = utc_now()
            uow.users.save(user)
            uow.commit()
            return user

    def deactivate_user(self, actor_uid, uid):
        return self.update_user(actor_uid, uid, {"status": "inactive"})
