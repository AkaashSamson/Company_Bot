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
            if uow.users.get_by_uid(uid) or uow.users.get_by_email(email):
                raise ConflictError("User UID or email already exists")
            if not uow.departments.get(department_id):
                raise NotFoundError("Department not found")
            now = utc_now()
            user = User(uid, name, email, role, department_id, created_at=now, updated_at=now)
            uow.users.save(user)
            uow.commit()
            return user

    def get_user(self, uid):
        with self.unit_of_work_factory() as uow:
            user = uow.users.get_by_uid(uid)
            if user is None:
                raise NotFoundError("User not found")
            return user

    def list_users(self):
        with self.unit_of_work_factory() as uow:
            return list(uow.users.list())

    def update_user(self, actor_uid, uid, changes):
        with self.unit_of_work_factory() as uow:
            user = uow.users.get_by_uid(uid)
            if user is None:
                raise NotFoundError("User not found")
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
