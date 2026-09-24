from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from app.domain.entities.organization_models import Department, User
from app.domain.services.business_id_generator import build_business_id_generator
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError
from app.core.settings import (
    DEFAULT_USER_PASSWORD,
    DEPARTMENT_ID_PREFIX,
    DOCUMENT_ID_PREFIX,
    EMPLOYEE_ID_PREFIX,
    PROJECT_ID_PREFIX,
)
from app.infrastructure.authentication.password_hasher import PasswordHasher


def utc_now():
    return datetime.now(timezone.utc)


DEPARTMENT_BILLABLE_POLICIES = {"billable", "non-billable", "both"}


class UserManagementService:
    def __init__(self, unit_of_work_factory: Callable, password_hasher=None, business_id_generator=None, employee_id_prefix: str = EMPLOYEE_ID_PREFIX):
        self.unit_of_work_factory = unit_of_work_factory
        self.password_hasher = password_hasher or PasswordHasher()
        self.business_id_generator = business_id_generator or build_business_id_generator(
            user_prefix=employee_id_prefix,
            department_prefix=DEPARTMENT_ID_PREFIX,
            project_prefix=PROJECT_ID_PREFIX,
            document_prefix=DOCUMENT_ID_PREFIX,
        )

    @staticmethod
    def _validate_billable_policy(value):
        if value not in DEPARTMENT_BILLABLE_POLICIES:
            raise ValueError(f"Invalid billable policy: {value!r}. Expected one of {sorted(DEPARTMENT_BILLABLE_POLICIES)}")

    def create_department(self, actor_uid: str, department_id: str | None = None, department_name: str = None, description=None, default_billable="billable"):
        self._validate_billable_policy(default_billable)
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            if actor is None or actor.status != "active" or actor.role.casefold() != "admin":
                raise ForbiddenError("Admin access required")
            if department_id is None:
                department_id = self.business_id_generator.next(uow, "department")
            if uow.departments.get(department_id):
                raise ConflictError("Department already exists")
            if any(item.department_name == department_name for item in uow.departments.list()):
                raise ConflictError("Department name already exists")
            department = Department(department_id, department_name, description=description, default_billable=default_billable)
            uow.departments.save(department)
            uow.commit()
            return department

    def list_departments(self):
        with self.unit_of_work_factory() as uow:
            return list(uow.departments.list())

    def get_department(self, department_id):
        with self.unit_of_work_factory() as uow:
            department = uow.departments.get(department_id)
            if department is None:
                raise NotFoundError("Department not found")
            return department

    def update_department(self, actor_uid: str, department_id: str, changes):
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            if actor is None or actor.status != "active" or actor.role.casefold() != "admin":
                raise ForbiddenError("Admin access required")
            department = uow.departments.get(department_id)
            if department is None:
                raise NotFoundError("Department not found")
            if "default_billable" in changes and changes["default_billable"]:
                self._validate_billable_policy(changes["default_billable"])
            if "department_name" in changes and changes["department_name"]:
                if changes["department_name"] != department.department_name and any(
                    item.department_name == changes["department_name"] and item.department_id != department_id
                    for item in uow.departments.list()
                ):
                    raise ConflictError("Department name already exists")
            for field, value in changes.items():
                if value is not None:
                    setattr(department, field, value)
            department.updated_at = utc_now()
            uow.departments.save(department)
            uow.commit()
            return department

    def create_user(self, actor_uid, uid=None, name=None, email=None, role=None, department_id=None, username=None, initial_password=None,
                    employee_id=None, first_name=None, last_name=None):
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            if actor is None or actor.status != "active":
                raise ForbiddenError("Active authenticated user required")
            if uid is None:
                uid = uuid4().hex
            username = username or uid
            if uow.users.get_by_uid(uid) or uow.users.get_by_email(email) or uow.users.get_by_username(username):
                raise ConflictError("User UID or email already exists")
            if not uow.departments.get(department_id):
                raise NotFoundError("Department not found")
            if actor.role.casefold() != "admin" and actor.department_id != department_id:
                raise ForbiddenError("User is outside manager scope")
            if role and role.casefold() == "admin" and actor.role.casefold() != "admin":
                raise ForbiddenError("Only administrators can create admin users")
            if employee_id:
                if uow.users.get_by_employee_id(employee_id):
                    raise ConflictError("Employee ID already exists")
            else:
                employee_id = self.business_id_generator.next(uow, "user")
            now = utc_now()
            user = User(
                uid, name, email, role, department_id, created_at=now, updated_at=now,
                username=username,
                password_representation=self.password_hasher.hash(initial_password or DEFAULT_USER_PASSWORD),
                must_change_password=True,
                employee_id=employee_id, first_name=first_name, last_name=last_name,
            )
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
                if actor.role.casefold() == "admin":
                    raise NotFoundError("User not found")
                raise ForbiddenError("User is outside manager scope")
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
            if changes.get("employee_id"):
                existing = uow.users.get_by_employee_id(changes["employee_id"])
                if existing and existing.uid != uid:
                    raise ConflictError("Employee ID already exists")
            if changes.get("role") is not None and actor.role.casefold() != "admin":
                raise ForbiddenError("Only administrators can change user roles")
            for field, value in changes.items():
                if value is not None:
                    setattr(user, field, value)
            user.updated_at = utc_now()
            uow.users.save(user)
            uow.commit()
            return user

    def deactivate_user(self, actor_uid, uid):
        return self.update_user(actor_uid, uid, {"status": "inactive"})