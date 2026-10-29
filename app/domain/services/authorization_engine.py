"""Centralized authorization engine.

Every authorization decision in the platform is resolved here and only here.
The engine derives a user's identity, active status, resolved roles, effective
permissions and then answers questions about project/document access and the
retrieval scope that may be handed to Chroma.

System-level roles ("Admin", "Manager", ...) are department-aware: a manager
only acts on projects/documents that belong to the manager's own department.
Custom RBAC roles (created through the role management API) grant *what* a
user may do (permissions); the engine decides *where* they may do it via
project membership, being the designated project lead, or an explicit
ProjectGrant / DocumentGrant assigned to a role or a specific user.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from app.domain.entities.organization_models import Role, User
from app.domain.ports.authorization_service import AuthenticatedPrincipal

ACTION_PERMISSIONS = {
    "view_users": "USER_VIEW",
    "create_user": "USER_CREATE",
    "update_user": "USER_UPDATE",
    "deactivate_user": "USER_DELETE",
    "view_departments": "DEPARTMENT_VIEW",
    "create_department": "DEPARTMENT_CREATE",
    "update_department": "DEPARTMENT_UPDATE",
    "assign_department_users": "DEPARTMENT_ASSIGN_USERS",
    "view_projects": "PROJECT_VIEW",
    "create_project": "PROJECT_CREATE",
    "update_project": "PROJECT_UPDATE",
    "delete_project": "PROJECT_DELETE",
    "manage_project_members": "PROJECT_MANAGE_MEMBERS",
    "leave_project": "PROJECT_LEAVE",
    "view_documents": "DOCUMENT_VIEW",
    "upload_document": "DOCUMENT_UPLOAD",
    "update_document": "DOCUMENT_UPDATE",
    "delete_document": "DOCUMENT_DELETE",
    "query_documents": "DOCUMENT_QUERY",
    "manage_document_access": "DOCUMENT_MANAGE_ACCESS",
    "create_role": "ROLE_CREATE",
    "update_role": "ROLE_UPDATE",
    "delete_role": "ROLE_DELETE",
    "view_roles": "ROLE_VIEW",
    "manage_permissions": "PERMISSION_MANAGE",
}

PRINCIPAL_TYPES = ("role", "user")


@dataclass(frozen=True, slots=True)
class AuthorizationScope:
    """The exact set of documents a principal may retrieve.

    - ``project_ids=None`` means unrestricted (only used for admins).
    - ``project_ids=[]`` means the principal may not retrieve anything.
    - ``document_ids`` are explicit per-document grants that go beyond the
      project membership scope.
    - ``include_unassigned`` authorizes organization-wide (unassigned)
      documents.
    """

    is_admin: bool = False
    project_ids: Optional[list[str]] = None
    document_ids: Optional[list[str]] = None
    include_unassigned: bool = False


class AuthorizationEngine:
    def __init__(self, unit_of_work_factory: Callable):
        self.unit_of_work_factory = unit_of_work_factory

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _active_user(uow, uid: str) -> Optional[User]:
        user = uow.users.get_by_uid(uid)
        if user is None or user.status != "active":
            return None
        return user

    @staticmethod
    def _roles_for_user(uow, uid: str) -> list[Role]:
        user = uow.users.get_by_uid(uid)
        if user is None or user.status != "active":
            return []
        candidates = []
        if user.role:
            named = uow.roles.get_by_name(user.role)
            if named is not None:
                candidates.append((named, user.department_id))
        for member in uow.department_members.list_for_user(uid):
            if member.status != "active" or not member.membership_role:
                continue
            role = uow.roles.get_by_name(member.membership_role)
            if role is not None:
                candidates.append((role, member.department_id))

        roles = []
        seen = set()
        for role, department_id in candidates:
            if role.status != "active" or role.role_id in seen:
                continue
            if role.scope == "department" and role.department_id not in (department_id, user.department_id):
                continue
            seen.add(role.role_id)
            roles.append(role)
        return roles

    def _permission_names(self, uow, user: User) -> set[str]:
        if user.role.casefold() == "admin":
            return {permission.name for permission in uow.permissions.list()}
        names = set()
        for role in self._roles_for_user(uow, user.uid):
            names.update(permission.name for permission in uow.roles.permissions_for_role(role.role_id))
        return names

    def _role_ids(self, uow, user: User) -> list[int]:
        return [role.role_id for role in self._roles_for_user(uow, user.uid)]

    def _has_project_grant(self, uow, user: User, project_id: str) -> bool:
        return project_id in uow.project_grants.project_ids_for_principal(user.uid, self._role_ids(uow, user))

    def _has_document_grant(self, uow, user: User, document_id: str) -> bool:
        return document_id in uow.document_grants.document_ids_for_principal(user.uid, self._role_ids(uow, user))

    @staticmethod
    def _can_manage_project(uow, user: User, project) -> bool:
        if user.role.casefold() == "admin":
            return True
        if user.role.casefold() == "manager" and user.department_id == project.department_id:
            return True
        return project.manager_uid == user.uid

    @staticmethod
    def _membership_project_ids(uow, user: User) -> list[str]:
        if user.role.casefold() == "admin":
            return [project.project_id for project in uow.projects.list_active()]
        return [
            membership.project_id
            for membership in uow.memberships.list_for_user(user.uid)
            if membership.status == "active"
        ]

    def _project_access_scope(self, uow, user: User) -> set[str]:
        """Strict retrieval scope: memberships, leads, grants.

        Deliberately does not grant every project in the user's department;
        a Developer may only see projects they were actually assigned to or
        explicitly granted.
        """
        project_ids = {
            membership.project_id
            for membership in uow.memberships.list_for_user(user.uid)
            if membership.status == "active"
        }
        for project in uow.projects.list_active():
            if self._can_manage_project(uow, user, project):
                project_ids.add(project.project_id)
        project_ids.update(uow.project_grants.project_ids_for_principal(user.uid, self._role_ids(uow, user)))
        return project_ids

    # --------------------------------------------------------------- permissions

    def is_admin(self, principal: AuthenticatedPrincipal) -> bool:
        if principal is None:
            return False
        with self.unit_of_work_factory() as uow:
            user = self._active_user(uow, principal.uid)
            return bool(user and user.role.casefold() == "admin")

    def roles_for_user(self, uid: str) -> Sequence[Role]:
        with self.unit_of_work_factory() as uow:
            return self._roles_for_user(uow, uid)

    def permissions_for_user(self, uid: str) -> set[str]:
        with self.unit_of_work_factory() as uow:
            user = uow.users.get_by_uid(uid)
            if user is None or user.status != "active":
                return set()
            return self._permission_names(uow, user)

    def has_permission(self, principal: AuthenticatedPrincipal, permission: str) -> bool:
        if principal is None:
            return False
        with self.unit_of_work_factory() as uow:
            user = self._active_user(uow, principal.uid)
            if user is None:
                return False
            if user.role.casefold() == "admin":
                return True
            return permission in self._permission_names(uow, user)

    def can(self, principal: AuthenticatedPrincipal, action: str) -> bool:
        permission = ACTION_PERMISSIONS.get(action)
        if permission is None:
            return False
        return self.has_permission(principal, permission)

    def can_manage_department(self, principal: AuthenticatedPrincipal, department_id: str) -> bool:
        if principal is None:
            return False
        with self.unit_of_work_factory() as uow:
            user = self._active_user(uow, principal.uid)
            if user is None:
                return False
            return user.role.casefold() == "admin" or user.department_id == department_id

    def can_manage_role(self, principal: AuthenticatedPrincipal, role: Role) -> bool:
        if principal is None or role is None:
            return False
        with self.unit_of_work_factory() as uow:
            user = self._active_user(uow, principal.uid)
            if user is None:
                return False
            if user.role.casefold() == "admin":
                return True
            return role.scope == "department" and role.department_id == user.department_id

    def project_access_contact(self, project_id: str) -> Optional[dict]:
        """Contact details used to build the safe access-request response.

        Exposes only the non-sensitive project name and manager name — never
        document content or document metadata.
        """
        with self.unit_of_work_factory() as uow:
            project = uow.projects.get(project_id)
            if project is None:
                return None
            manager_name = None
            if project.manager_uid:
                manager = uow.users.get_by_uid(project.manager_uid)
                if manager is not None:
                    manager_name = manager.name
            return {
                "project_id": project.project_id,
                "project_name": project.project_name,
                "manager_name": manager_name or "the project manager",
            }

    # ------------------------------------------------------------------ projects

    def can_manage_project(self, principal: AuthenticatedPrincipal, project_id: str) -> bool:
        if principal is None:
            return False
        with self.unit_of_work_factory() as uow:
            user = self._active_user(uow, principal.uid)
            project = uow.projects.get(project_id)
            if user is None or project is None:
                return False
            return self._can_manage_project(uow, user, project)

    def can_manage_project_members(self, principal: AuthenticatedPrincipal, project_id: str) -> bool:
        return self.can_manage_project(principal, project_id)

    def can_access_project(self, principal: AuthenticatedPrincipal, project_id: str) -> bool:
        """Management/detail scope: admin, same department, lead, member or grant."""
        if principal is None:
            return False
        with self.unit_of_work_factory() as uow:
            user = self._active_user(uow, principal.uid)
            project = uow.projects.get(project_id)
            if user is None or project is None or project.status != "active":
                return False
            if self._can_manage_project(uow, user, project):
                return True
            if user.department_id == project.department_id:
                return True
            membership = uow.memberships.get(user.uid, project_id)
            if membership is not None and membership.status == "active":
                return True
            return self._has_project_grant(uow, user, project_id)

    def can_view_project_documents(self, principal: AuthenticatedPrincipal, project_id: str) -> bool:
        """Strict project-document scope: lead/manager, active member or grant."""
        if principal is None:
            return False
        with self.unit_of_work_factory() as uow:
            user = self._active_user(uow, principal.uid)
            project = uow.projects.get(project_id)
            if user is None or project is None:
                return False
            if self._can_manage_project(uow, user, project):
                return True
            membership = uow.memberships.get(user.uid, project_id)
            if membership is not None and membership.status == "active":
                return True
            return self._has_project_grant(uow, user, project_id)

    def accessible_project_ids(self, principal: AuthenticatedPrincipal) -> list[str]:
        if principal is None:
            return []
        with self.unit_of_work_factory() as uow:
            user = self._active_user(uow, principal.uid)
            if user is None:
                return []
            if user.role.casefold() == "admin":
                return [project.project_id for project in uow.projects.list_active()]
            scope = self._project_access_scope(uow, user)
            return sorted(scope)

    def authorized_project_ids(self, principal: AuthenticatedPrincipal, selected_project_id: str | None = None) -> list[str]:
        """Backwards-compatible membership scope (admin: every active project)."""
        if principal is None:
            return []
        with self.unit_of_work_factory() as uow:
            user = self._active_user(uow, principal.uid)
            if user is None:
                return []
            project_ids = self._membership_project_ids(uow, user)
            if selected_project_id is not None:
                return [selected_project_id] if selected_project_id in project_ids else []
            return project_ids

    # --------------------------------------------------------------- documents

    def can_upload_document(self, principal: AuthenticatedPrincipal, project_id: str | None) -> bool:
        if principal is None:
            return False
        with self.unit_of_work_factory() as uow:
            user = self._active_user(uow, principal.uid)
            if user is None:
                return False
            if user.role.casefold() == "admin":
                return True
            if project_id is None:
                return user.role.casefold() == "manager"
            project = uow.projects.get(project_id)
            if project is None:
                return False
            return self._can_manage_project(uow, user, project)

    def can_read_document(self, principal: AuthenticatedPrincipal, document_id: str) -> bool:
        """Whether the principal may see/read a document (explicit grants included)."""
        if principal is None:
            return False
        with self.unit_of_work_factory() as uow:
            user = self._active_user(uow, principal.uid)
            document = uow.documents.get(document_id)
            if user is None or document is None or document.status != "active":
                return False
            if user.role.casefold() == "admin":
                return True
            if self._has_document_grant(uow, user, document.document_id):
                return True
            if document.project_id is None:
                return True
            project = uow.projects.get(document.project_id)
            if project is None:
                return False
            if self._can_manage_project(uow, user, project):
                return True
            membership = uow.memberships.get(user.uid, document.project_id)
            if membership is not None and membership.status == "active":
                return True
            return self._has_project_grant(uow, user, document.project_id)

    def can_manage_document(self, principal: AuthenticatedPrincipal, document_id: str, allow_archived: bool = True) -> bool:
        """Update/delete scope: admin, department manager of the owning project or lead."""
        if principal is None:
            return False
        with self.unit_of_work_factory() as uow:
            user = self._active_user(uow, principal.uid)
            document = uow.documents.get(document_id)
            if user is None or document is None:
                return False
            if not allow_archived and document.status != "active":
                return False
            if user.role.casefold() == "admin":
                return True
            if document.project_id is None:
                return user.role.casefold() == "manager"
            project = uow.projects.get(document.project_id)
            if project is None:
                return False
            return self._can_manage_project(uow, user, project)

    # --------------------------------------------------------------- scope

    def authorization_scope(self, principal: AuthenticatedPrincipal, selected_project_id: str | None = None) -> AuthorizationScope:
        empty = AuthorizationScope(is_admin=False, project_ids=[], document_ids=None, include_unassigned=False)
        if principal is None:
            return empty
        with self.unit_of_work_factory() as uow:
            user = self._active_user(uow, principal.uid)
            if user is None:
                return empty

            if user.role.casefold() == "admin":
                return AuthorizationScope(
                    is_admin=True,
                    project_ids=None,
                    document_ids=None,
                    include_unassigned=True,
                )

            scoped_projects = self._project_access_scope(uow, user)
            document_ids = uow.document_grants.document_ids_for_principal(user.uid, self._role_ids(uow, user))
            active_document_ids = [
                document_id
                for document_id in document_ids
                if _document_active(uow, document_id)
            ]

            if selected_project_id is not None:
                if selected_project_id in scoped_projects:
                    return AuthorizationScope(
                        is_admin=False,
                        project_ids=[selected_project_id],
                        document_ids=active_document_ids or None,
                        include_unassigned=True,
                    )
                selected_project_doc_grants = [
                    document_id
                    for document_id in active_document_ids
                    if _document_project(uow, document_id) == selected_project_id
                ]
                if selected_project_doc_grants:
                    return AuthorizationScope(
                        is_admin=False,
                        project_ids=[],
                        document_ids=selected_project_doc_grants,
                        include_unassigned=True,
                    )
                return empty

            return AuthorizationScope(
                is_admin=False,
                project_ids=sorted(scoped_projects),
                document_ids=active_document_ids or None,
                include_unassigned=True,
            )


def _document_active(uow, document_id: str) -> bool:
    document = uow.documents.get(document_id)
    return document is not None and document.status == "active"


def _document_project(uow, document_id: str) -> Optional[str]:
    document = uow.documents.get(document_id)
    return document.project_id if document is not None else None