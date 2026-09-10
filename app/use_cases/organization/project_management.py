from datetime import datetime, timezone
from typing import Callable

from app.domain.entities.organization_models import Project
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError


def utc_now():
    return datetime.now(timezone.utc)


class ProjectManagementService:
    def __init__(self, unit_of_work_factory: Callable):
        self.unit_of_work_factory = unit_of_work_factory

    def _actor_and_project(self, uow, actor_uid, project_id):
        actor = uow.users.get_by_uid(actor_uid)
        project = uow.projects.get(project_id)
        if actor is None or actor.status != "active":
            raise ForbiddenError("Active authenticated user required")
        if project is None:
            raise NotFoundError("Project not found")
        if actor.role.casefold() != "admin" and actor.department_id != project.department_id:
            raise ForbiddenError("Project is outside manager scope")
        return actor, project

    def create_project(self, actor_uid, project_id, project_name, department_id):
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            if actor is None or actor.status != "active" or actor.role.casefold() != "admin":
                raise ForbiddenError("Admin access required")
            if not uow.departments.get(department_id):
                raise NotFoundError("Department not found")
            if uow.projects.get(project_id):
                raise ConflictError("Project already exists")
            project = Project(project_id, project_name, department_id)
            uow.projects.save(project)
            uow.commit()
            return project

    def list_projects(self, actor_uid):
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            if actor is None or actor.status != "active":
                raise ForbiddenError("Active authenticated user required")
            projects = list(uow.projects.list_active())
            if actor.role.casefold() == "admin":
                return projects
            memberships = {
                membership.project_id
                for membership in uow.memberships.list_for_user(actor.uid)
                if membership.status == "active"
            }
            return [project for project in projects if project.project_id in memberships]
