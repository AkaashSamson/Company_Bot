from app.domain.entities.organization_models import Project
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.ports.unit_of_work import UnitOfWork


class OrganizationAuthorizationService:
    def __init__(self, unit_of_work: UnitOfWork):
        self.unit_of_work = unit_of_work

    def authorized_project_ids(self, principal: AuthenticatedPrincipal, selected_project_id=None):
        with self.unit_of_work as unit_of_work:
            user = unit_of_work.users.get_by_uid(principal.uid)
            if user is None or user.status != "active":
                return []

            if user.role.casefold() == "admin":
                project_ids = [project.project_id for project in unit_of_work.projects.list_active()]
            else:
                project_ids = [
                    membership.project_id
                    for membership in unit_of_work.memberships.list_for_user(user.uid)
                    if membership.status == "active"
                ]

            if selected_project_id is not None:
                return [selected_project_id] if selected_project_id in project_ids else []
            return project_ids

    def can_manage_department(self, principal, department_id):
        with self.unit_of_work as unit_of_work:
            user = unit_of_work.users.get_by_uid(principal.uid)
            return bool(
                user
                and user.status == "active"
                and (user.role.casefold() == "admin" or user.department_id == department_id)
            )

    def can_manage_project(self, principal, project_id):
        with self.unit_of_work as unit_of_work:
            user = unit_of_work.users.get_by_uid(principal.uid)
            project = unit_of_work.projects.get(project_id)
            return bool(
                user
                and project
                and user.status == "active"
                and (user.role.casefold() == "admin" or user.department_id == project.department_id)
            )
