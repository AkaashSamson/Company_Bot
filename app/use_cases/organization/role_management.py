import re
from datetime import datetime, timezone
from typing import Callable

from app.domain.entities.organization_models import Permission, Role
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_service import OrganizationAuthorizationService
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError


def utc_now():
    return datetime.now(timezone.utc)


ROLE_SCOPES = {"global", "department"}
ROLE_STATUSES = {"active", "inactive"}
PERMISSION_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


class RoleManagementService:
    def __init__(self, unit_of_work_factory: Callable, authorization_service=None):
        self.unit_of_work_factory = unit_of_work_factory
        self.authorization_service = authorization_service or OrganizationAuthorizationService(unit_of_work_factory())

    def _require(self, actor_uid, permission):
        if not self.authorization_service.has_permission(AuthenticatedPrincipal(actor_uid), permission):
            raise ForbiddenError(f"Missing required permission: {permission}")

    @staticmethod
    def _require_active(unit_of_work, actor_uid):
        actor = unit_of_work.users.get_by_uid(actor_uid)
        if actor is None or actor.status != "active":
            raise ForbiddenError("Active authenticated user required")
        return actor

    @staticmethod
    def _validate_permission_name(name):
        if not name or not PERMISSION_NAME_PATTERN.match(name):
            raise ValueError("Permission name must be an uppercase identifier such as DOCUMENT_VIEW")

    @staticmethod
    def _validate_scope(scope):
        if scope not in ROLE_SCOPES:
            raise ValueError(f"Invalid role scope: {scope!r}. Expected one of {sorted(ROLE_SCOPES)}")

    @staticmethod
    def _resolve_permissions(unit_of_work, permission_ids):
        permissions = []
        for permission_id in permission_ids or []:
            permission = unit_of_work.permissions.get(permission_id)
            if permission is None:
                raise NotFoundError(f"Permission {permission_id} not found")
            permissions.append(permission)
        return permissions

    @staticmethod
    def _ensure_visible(actor, role):
        if actor.role.casefold() == "admin":
            return
        if role.scope == "global" or role.department_id == actor.department_id:
            return
        raise ForbiddenError("Role is outside manager scope")

    @staticmethod
    def _ensure_manage(actor, role):
        if actor.role.casefold() == "admin":
            return
        if role.scope == "department" and role.department_id == actor.department_id:
            return
        raise ForbiddenError("Only administrators can manage global roles")

    def list_permissions(self, actor_uid):
        self._require(actor_uid, "ROLE_VIEW")
        with self.unit_of_work_factory() as unit_of_work:
            self._require_active(unit_of_work, actor_uid)
            return list(unit_of_work.permissions.list())

    def create_permission(self, actor_uid, name, description=None):
        self._validate_permission_name(name)
        self._require(actor_uid, "PERMISSION_MANAGE")
        with self.unit_of_work_factory() as unit_of_work:
            self._require_active(unit_of_work, actor_uid)
            if unit_of_work.permissions.get_by_name(name) is not None:
                raise ConflictError("Permission already exists")
            permission = Permission(None, name, description)
            permission = unit_of_work.permissions.save(permission)
            unit_of_work.commit()
            return permission

    def list_roles(self, actor_uid):
        self._require(actor_uid, "ROLE_VIEW")
        with self.unit_of_work_factory() as unit_of_work:
            actor = self._require_active(unit_of_work, actor_uid)
            if actor.role.casefold() == "admin":
                return list(unit_of_work.roles.list())
            return [
                role
                for role in unit_of_work.roles.list()
                if role.scope == "global" or role.department_id == actor.department_id
            ]

    def get_role(self, actor_uid, role_id):
        self._require(actor_uid, "ROLE_VIEW")
        with self.unit_of_work_factory() as unit_of_work:
            actor = self._require_active(unit_of_work, actor_uid)
            role = unit_of_work.roles.get(role_id)
            if role is None:
                raise NotFoundError("Role not found")
            self._ensure_visible(actor, role)
            return role

    def list_role_permissions(self, actor_uid, role_id):
        self._require(actor_uid, "ROLE_VIEW")
        with self.unit_of_work_factory() as unit_of_work:
            actor = self._require_active(unit_of_work, actor_uid)
            role = unit_of_work.roles.get(role_id)
            if role is None:
                raise NotFoundError("Role not found")
            self._ensure_visible(actor, role)
            return list(unit_of_work.roles.permissions_for_role(role_id))

    def create_role(self, actor_uid, name, description=None, scope="global", department_id=None, permission_ids=None):
        self._validate_scope(scope)
        self._require(actor_uid, "ROLE_CREATE")
        with self.unit_of_work_factory() as unit_of_work:
            actor = self._require_active(unit_of_work, actor_uid)
            if unit_of_work.roles.get_by_name(name) is not None:
                raise ConflictError("Role already exists")
            if scope == "department":
                if not department_id:
                    raise ValueError("department_id is required for department-scoped roles")
                if unit_of_work.departments.get(department_id) is None:
                    raise NotFoundError("Department not found")
                if actor.role.casefold() != "admin" and actor.department_id != department_id:
                    raise ForbiddenError("Role is outside manager scope")
            else:
                if actor.role.casefold() != "admin":
                    raise ForbiddenError("Only administrators can create global roles")
                department_id = None
            role = Role(
                None, name, description,
                scope=scope, department_id=department_id,
                status="active", created_by_uid=actor_uid,
            )
            role = unit_of_work.roles.save(role)
            if permission_ids is not None:
                self._resolve_permissions(unit_of_work, permission_ids)
                unit_of_work.roles.set_permissions(role.role_id, permission_ids, actor_uid)
            unit_of_work.commit()
            return role

    def update_role(self, actor_uid, role_id, changes):
        self._require(actor_uid, "ROLE_UPDATE")
        with self.unit_of_work_factory() as unit_of_work:
            actor = self._require_active(unit_of_work, actor_uid)
            role = unit_of_work.roles.get(role_id)
            if role is None:
                raise NotFoundError("Role not found")
            self._ensure_manage(actor, role)
            if changes.get("scope") is not None:
                self._validate_scope(changes["scope"])
                if changes["scope"] == "global" and actor.role.casefold() != "admin":
                    raise ForbiddenError("Only administrators can manage global roles")
            if changes.get("status") is not None and changes["status"] not in ROLE_STATUSES:
                raise ValueError(f"Invalid role status: {changes['status']!r}")
            if changes.get("name"):
                existing = unit_of_work.roles.get_by_name(changes["name"])
                if existing is not None and existing.role_id != role_id:
                    raise ConflictError("Role already exists")
            if changes.get("department_id"):
                if unit_of_work.departments.get(changes["department_id"]) is None:
                    raise NotFoundError("Department not found")
            for field in ("name", "description", "scope", "department_id", "status"):
                if field in changes and changes[field] is not None:
                    setattr(role, field, changes[field])
            role.updated_at = utc_now()
            unit_of_work.roles.save(role)
            unit_of_work.commit()
            return role

    def set_role_permissions(self, actor_uid, role_id, permission_ids):
        self._require(actor_uid, "PERMISSION_MANAGE")
        with self.unit_of_work_factory() as unit_of_work:
            actor = self._require_active(unit_of_work, actor_uid)
            role = unit_of_work.roles.get(role_id)
            if role is None:
                raise NotFoundError("Role not found")
            self._ensure_manage(actor, role)
            self._resolve_permissions(unit_of_work, permission_ids)
            unit_of_work.roles.set_permissions(role.role_id, permission_ids, actor_uid)
            role.updated_at = utc_now()
            unit_of_work.roles.save(role)
            unit_of_work.commit()
            return role

    def delete_role(self, actor_uid, role_id):
        self._require(actor_uid, "ROLE_DELETE")
        with self.unit_of_work_factory() as unit_of_work:
            actor = self._require_active(unit_of_work, actor_uid)
            role = unit_of_work.roles.get(role_id)
            if role is None:
                raise NotFoundError("Role not found")
            self._ensure_manage(actor, role)
            if any(user.role == role.name for user in unit_of_work.users.list()):
                raise ConflictError("Role is assigned to users and cannot be deleted")
            unit_of_work.roles.delete(role_id)
            unit_of_work.commit()

    def effective_permissions(self, actor_uid, uid):
        if actor_uid != uid:
            self._require(actor_uid, "ROLE_VIEW")
        return sorted(self.authorization_service.permissions_for_user(uid))

    def roles_for_user(self, actor_uid, uid):
        if actor_uid != uid:
            self._require(actor_uid, "ROLE_VIEW")
        return list(self.authorization_service.roles_for_user(uid))
