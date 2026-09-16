from datetime import datetime, timezone
from typing import Callable

from app.core.settings import DEPARTMENT_ID_PREFIX, DOCUMENT_ID_PREFIX, EMPLOYEE_ID_PREFIX, PROJECT_ID_PREFIX
from app.domain.entities.organization_models import Project
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine
from app.domain.services.business_id_generator import build_business_id_generator
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError


def utc_now():
    return datetime.now(timezone.utc)


class ProjectManagementService:
    def __init__(self, unit_of_work_factory: Callable, business_id_generator=None, project_id_prefix: str = PROJECT_ID_PREFIX):
        self.unit_of_work_factory = unit_of_work_factory
        self.business_id_generator = business_id_generator or build_business_id_generator(
            user_prefix=EMPLOYEE_ID_PREFIX,
            department_prefix=DEPARTMENT_ID_PREFIX,
            project_prefix=project_id_prefix,
            document_prefix=DOCUMENT_ID_PREFIX,
        )
        self.authorization = AuthorizationEngine(unit_of_work_factory)

    def _check_manage(self, actor, project):
        if actor is None or actor.status != "active":
            raise ForbiddenError("Active authenticated user required")
        if project is None:
            raise NotFoundError("Project not found")
        if not self.authorization.can_manage_project(AuthenticatedPrincipal(actor.uid), project.project_id):
            raise ForbiddenError("Project is outside manager scope")

    def _check_view(self, actor, project):
        if actor is None or actor.status != "active":
            raise ForbiddenError("Active authenticated user required")
        if project is None:
            raise NotFoundError("Project not found")
        if not self.authorization.can_access_project(AuthenticatedPrincipal(actor.uid), project.project_id):
            raise ForbiddenError("Project is outside viewer scope")

    def _actor_and_project(self, uow, actor_uid, project_id):
        actor = uow.users.get_by_uid(actor_uid)
        project = uow.projects.get(project_id)
        self._check_manage(actor, project)
        return actor, project

    def create_project(
        self,
        actor_uid,
        project_id=None,
        project_name=None,
        department_id=None,
        description=None,
        manager_uid=None,
        start_date=None,
        end_date=None,
    ):
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            if actor is None or actor.status != "active" or not self.authorization.is_admin(AuthenticatedPrincipal(actor_uid)):
                raise ForbiddenError("Admin access required")
            if not uow.departments.get(department_id):
                raise NotFoundError("Department not found")
            if manager_uid:
                manager = uow.users.get_by_uid(manager_uid)
                if manager is None or manager.status != "active":
                    raise NotFoundError("Project manager not found")
                if manager.department_id != department_id:
                    raise ForbiddenError("Project manager must belong to the project department")
            project_id = project_id or self.business_id_generator.next(uow, "project")
            if uow.projects.get(project_id):
                raise ConflictError("Project already exists")
            now = utc_now()
            project = Project(
                project_id,
                project_name,
                department_id,
                created_at=now,
                updated_at=now,
                description=description,
                manager_uid=manager_uid,
                start_date=start_date,
                end_date=end_date,
                created_by_uid=actor_uid,
            )
            project = uow.projects.save(project)
            uow.commit()
            return project

    def get_project(self, actor_uid, project_key):
        with self.unit_of_work_factory() as uow:
            project = uow.projects.get(project_key)
            if project is None and project_key.isdigit():
                project = uow.projects.get_by_internal_id(int(project_key))
            actor = uow.users.get_by_uid(actor_uid)
            self._check_view(actor, project)
            return project

    def update_project(self, actor_uid, project_id, changes):
        with self.unit_of_work_factory() as uow:
            actor, project = self._actor_and_project(uow, actor_uid, project_id)
            if "department_id" in changes and changes["department_id"]:
                if not uow.departments.get(changes["department_id"]):
                    raise NotFoundError("Department not found")
                if actor.role.casefold() != "admin":
                    raise ForbiddenError("Only admins can move a project to another department")
            if "manager_uid" in changes:
                if actor.role.casefold() != "admin":
                    raise ForbiddenError("Only admins can change the project manager")
                manager_uid = changes["manager_uid"]
                if manager_uid is not None:
                    manager = uow.users.get_by_uid(manager_uid)
                    if manager is None or manager.status != "active":
                        raise NotFoundError("Project manager not found")
                    target_department_id = changes.get("department_id") or project.department_id
                    if manager.department_id != target_department_id:
                        raise ForbiddenError("Project manager must belong to the project department")
            for field, value in changes.items():
                if value is None and field not in ("description", "manager_uid", "start_date", "end_date"):
                    continue
                setattr(project, field, value)
            project.updated_at = utc_now()
            uow.projects.save(project)
            uow.commit()
            return project

    def list_projects(self, actor_uid):
        with self.unit_of_work_factory() as uow:
            actor = uow.users.get_by_uid(actor_uid)
            if actor is None or actor.status != "active":
                raise ForbiddenError("Active authenticated user required")
            accessible = set(self.authorization.accessible_project_ids(AuthenticatedPrincipal(actor_uid)))
            return [project for project in uow.projects.list_active() if project.project_id in accessible]