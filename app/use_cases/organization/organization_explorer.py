from typing import Callable

from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine
from app.domain.services.organization_errors import ForbiddenError

DESCRIPTION_MAX_LENGTH = 500


class OrganizationExplorerService:
    """Read-only, authorization-scoped view of the organization hierarchy.

    All visibility decisions are delegated to the single AuthorizationEngine:
      - Only projects in the principal's strict access scope are listed.
      - Only documents the principal may read are listed (per document).
      - Project member rosters are exposed only where the principal already
        holds project-management scope (mirroring the existing members API).
    Nothing is revealed merely because it exists in the database.
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

    @staticmethod
    def _person(uow, uid):
        if not uid:
            return None
        user = uow.users.get_by_uid(uid)
        return {"uid": uid, "name": user.name if user else None}

    @staticmethod
    def _description(document):
        if not document.description:
            return None
        return document.description[:DESCRIPTION_MAX_LENGTH]

    def get_organization(self, principal: AuthenticatedPrincipal):
        with self.unit_of_work_factory() as uow:
            actor = self._require_active(uow, principal.uid)
            principal = AuthenticatedPrincipal(actor.uid)

            roles = list(self.authorization.roles_for_user(actor.uid))
            role_ids = [role.role_id for role in roles]
            grant_document_ids = set(uow.document_grants.document_ids_for_principal(actor.uid, role_ids))

            accessible = set(self.authorization.accessible_project_ids(principal))
            active_projects = sorted(
                (project for project in uow.projects.list_active() if project.project_id in accessible),
                key=lambda project: project.project_name.casefold(),
            )
            visible_project_ids = {project.project_id for project in active_projects}

            readable = [
                document
                for document in uow.documents.list()
                if self.authorization.can_read_document(principal, document.document_id)
            ]

            departments = {item.department_id: item for item in uow.departments.list()}
            department_names = {key: item.department_name for key, item in departments.items()}

            people = [
                {
                    "uid": user.uid,
                    "name": user.name,
                    "employee_id": user.employee_id,
                    "role": user.role,
                    "department_id": user.department_id,
                    "department_name": department_names.get(user.department_id, user.department_id or None),
                }
                for user in uow.users.list()
                if user.status == "active"
            ]
            people.sort(key=lambda person: (person["name"] or person["uid"]).casefold())

            project_documents = {}
            unassigned = []
            additional = []
            for document in readable:
                if document.project_id is None:
                    unassigned.append(document)
                elif document.project_id in visible_project_ids:
                    project_documents.setdefault(document.project_id, []).append(document)
                else:
                    additional.append(document)

            groups = {}
            for project in active_projects:
                dept = departments.get(project.department_id)
                member_rows = (
                    list(uow.memberships.list_for_project(project.project_id))
                    if self.authorization.can_manage_project(principal, project.project_id)
                    else None
                )
                groups.setdefault(
                    project.department_id,
                    {"department_id": project.department_id, "department_name": dept.department_name if dept else project.department_id, "projects": []},
                )
                groups[project.department_id]["projects"].append(
                    {
                        "project_id": project.project_id,
                        "project_name": project.project_name,
                        "description": project.description,
                        "department_id": project.department_id,
                        "department_name": dept.department_name if dept else project.department_id,
                        "status": project.status,
                        "manager": self._person(uow, project.manager_uid),
                        "members_visible": member_rows is not None,
                        "members": [
                            {
                                "uid": member.uid,
                                "name": (uow.users.get_by_uid(member.uid).name if uow.users.get_by_uid(member.uid) else None),
                                "membership_role": member.membership_role,
                                "status": member.status,
                                "joined_at": member.assigned_at,
                            }
                            for member in (member_rows or [])
                        ],
                        "documents": [
                            self._document(uow, document, grant_document_ids, role_ids, actor.uid)
                            for document in project_documents.get(project.project_id, [])
                        ],
                    }
                )

            departments_list = [
                {
                    "department_id": key,
                    "department_name": value["department_name"],
                    "projects": value["projects"],
                }
                for key, value in sorted(groups.items(), key=lambda item: item[1]["department_name"].casefold())
            ]

            return {
                "people": people,
                "departments": departments_list,
                "unassigned_documents": [
                    self._document(uow, document, grant_document_ids, role_ids, actor.uid)
                    for document in sorted(unassigned, key=lambda item: item.document_name.casefold())
                ],
                "additional_documents": [
                    self._document(uow, document, grant_document_ids, role_ids, actor.uid)
                    for document in sorted(additional, key=lambda item: item.document_name.casefold())
                ],
            }

    def _document(self, uow, document, grant_document_ids, role_ids, actor_uid):
        if document.document_id in grant_document_ids:
            access = "document_grant"
        elif document.project_id is None:
            access = "org_wide"
        else:
            access = "project_access"

        granted_by = None
        granted_at = None
        if access == "document_grant":
            grant = self._active_grant_for_principal(uow, document.document_id, actor_uid, role_ids)
            if grant is not None:
                granted_by = self._person(uow, grant.granted_by_uid)
                granted_at = grant.granted_at

        return {
            "document_id": document.document_id,
            "document_name": document.document_name,
            "file_type": document.file_type,
            "version": document.version,
            "status": document.status,
            "uploaded_by": self._person(uow, document.uploaded_by),
            "uploaded_at": document.uploaded_at,
            "description": self._description(document),
            "access": access,
            "granted_by": granted_by,
            "granted_at": granted_at,
        }

    @staticmethod
    def _active_grant_for_principal(uow, document_id, actor_uid, role_ids):
        for grant in uow.document_grants.for_document(document_id):
            if grant.status != "active":
                continue
            if grant.principal_type == "user" and grant.user_id == actor_uid:
                return grant
            if grant.principal_type == "role" and grant.role_id in set(role_ids):
                return grant
        return None