from typing import Callable

from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine
from app.domain.services.organization_errors import ForbiddenError


class ProfileService:
    """Read-only assembly of the current user's own profile.

    Every authorization decision (which projects are visible, which documents
    are readable, which roles/permissions apply) is delegated to the single
    AuthorizationEngine. This service only shapes the result for display; it
    never re-implements a permission check.
    """

    def __init__(self, unit_of_work_factory: Callable):
        self.unit_of_work_factory = unit_of_work_factory
        self.authorization = AuthorizationEngine(unit_of_work_factory)

    @staticmethod
    def _require_active(uow, actor_uid):
        actor = uow.users.get_by_uid(actor_uid)
        if actor is None or actor.status != "active":
            raise ForbiddenError("Active authenticated user required")
        return actor

    def get_profile(self, principal: AuthenticatedPrincipal):
        with self.unit_of_work_factory() as uow:
            actor = self._require_active(uow, principal.uid)
            principal = AuthenticatedPrincipal(actor.uid)

            roles = list(self.authorization.roles_for_user(actor.uid))
            role_ids = [role.role_id for role in roles]
            permissions = sorted(self.authorization.permissions_for_user(actor.uid))

            department = uow.departments.get(actor.department_id) if actor.department_id else None
            department_member = (
                uow.department_members.get(actor.uid, actor.department_id) if actor.department_id else None
            )
            billable_status = (
                department_member.billable_status
                if department_member is not None and department_member.status == "active"
                else None
            )

            grant_project_ids = set(uow.project_grants.project_ids_for_principal(actor.uid, role_ids))
            grant_document_ids = set(uow.document_grants.document_ids_for_principal(actor.uid, role_ids))

            projects = [
                self._project(uow, actor, project, grant_project_ids, principal)
                for project in uow.projects.list_active()
                if self.authorization.can_access_project(principal, project.project_id)
            ]
            projects.sort(key=lambda item: item["project_name"].casefold())

            documents = [
                self._document(uow, document, grant_document_ids)
                for document in uow.documents.list()
                if self.authorization.can_read_document(principal, document.document_id)
            ]
            documents.sort(key=lambda item: (item["project_id"] or "", item["document_name"].casefold()))

            return {
                "user": {
                    "uid": actor.uid,
                    "name": actor.name,
                    "email": actor.email,
                    "employee_id": actor.employee_id,
                    "role": actor.role,
                    "status": actor.status,
                },
                "department": (
                    {"department_id": department.department_id, "department_name": department.department_name}
                    if department is not None
                    else None
                ),
                "billable_status": billable_status,
                "projects": projects,
                "documents": documents,
                "roles": [
                    {
                        "role_id": role.role_id,
                        "name": role.name,
                        "scope": role.scope,
                        "department_id": role.department_id,
                        "description": role.description,
                    }
                    for role in roles
                ],
                "permissions": permissions,
            }

    def _project(self, uow, actor, project, grant_project_ids, principal):
        membership = uow.memberships.get(actor.uid, project.project_id)
        is_member = membership is not None and membership.status == "active"

        manager = None
        if project.manager_uid:
            manager_user = uow.users.get_by_uid(project.manager_uid)
            manager = {"uid": project.manager_uid, "name": manager_user.name if manager_user else None}

        if self.authorization.can_manage_project(principal, project.project_id):
            access_source = "lead_or_manager"
        elif actor.department_id and actor.department_id == project.department_id:
            access_source = "department"
        elif is_member:
            access_source = "member"
        elif project.project_id in grant_project_ids:
            access_source = "grant"
        else:
            access_source = "member"

        return {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "project_status": project.status,
            "manager": manager,
            "is_member": is_member,
            "membership": (
                {
                    "membership_role": membership.membership_role,
                    "status": membership.status,
                    "joined_at": membership.assigned_at,
                }
                if membership is not None
                else None
            ),
            "access_source": access_source,
        }

    @staticmethod
    def _document(uow, document, grant_document_ids):
        if document.document_id in grant_document_ids:
            access_source = "document_grant"
        elif document.project_id is None:
            access_source = "manager_scope"
        else:
            access_source = "project_access"

        project_name = None
        if document.project_id:
            project = uow.projects.get(document.project_id)
            project_name = project.project_name if project is not None else None

        return {
            "document_id": document.document_id,
            "document_name": document.document_name,
            "project_id": document.project_id,
            "project_name": project_name,
            "file_type": document.file_type,
            "version": document.version,
            "status": document.status,
            "uploaded_at": document.uploaded_at,
            "access_source": access_source,
        }