from app.domain.entities.organization_models import ProjectGrant, UserProject, utc_now
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError


class ProjectAccessService:
    def __init__(self, unit_of_work_factory, authorization):
        self.unit_of_work_factory = unit_of_work_factory
        self.authorization = authorization

    @staticmethod
    def _require_active(uow, uid):
        user = uow.users.get_by_uid(uid)
        if user is None or user.status != "active":
            raise ForbiddenError("Actor is inactive or not found")
        return user

    @staticmethod
    def _check_principal_target(uow, principal_type, role_id, user_id):
        if principal_type not in ("role", "user"):
            raise ValueError(f"Unknown principal_type: {principal_type}")
        if principal_type == "role":
            if role_id is None or user_id is not None:
                raise ValueError("A role grant requires role_id and no user_id")
            if uow.roles.get(role_id) is None:
                raise NotFoundError("Role not found")
        else:
            if user_id is None or role_id is not None:
                raise ValueError("A user grant requires user_id and no role_id")
            if uow.users.get_by_uid(user_id) is None:
                raise NotFoundError("User not found")

    @staticmethod
    def _require_project_manager(authorization, actor_principal, uow, project_id):
        if not authorization.can_manage_project(actor_principal, project_id):
            raise ForbiddenError("Project is outside manager scope")

    def grant(self, actor_principal, project_id, principal_type, role_id=None, user_id=None):
        with self.unit_of_work_factory() as uow:
            self._require_active(uow, actor_principal.uid)
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("Project not found")
            self._require_project_manager(self.authorization, actor_principal, uow, project_id)
            self._check_principal_target(uow, principal_type, role_id, user_id)

            if principal_type == "user":
                uow.memberships.save(
                    UserProject(
                        uid=user_id,
                        project_id=project_id,
                        assigned_by_uid=actor_principal.uid,
                        role_id=role_id,
                        status="active",
                        assigned_at=utc_now(),
                    )
                )
            elif principal_type == "role":
                role = uow.roles.get(role_id)
                users = [u for u in uow.users.list() if u.role_id == role_id or (role and u.role == role.name)]
                for u in users:
                    uow.memberships.save(
                        UserProject(
                            uid=u.uid,
                            project_id=project_id,
                            assigned_by_uid=actor_principal.uid,
                            role_id=role_id,
                            status="active",
                            assigned_at=utc_now(),
                        )
                    )

            if hasattr(uow, "project_grants"):
                if uow.project_grants.get(project_id, principal_type, role_id=role_id, user_id=user_id) is not None:
                    raise ConflictError("Grant already exists")
                grant = ProjectGrant(
                    project_id,
                    principal_type,
                    role_id=role_id,
                    user_id=user_id,
                    granted_by_uid=actor_principal.uid,
                    status="active",
                    granted_at=utc_now(),
                )
                grant = uow.project_grants.save(grant)
            else:
                grant = ProjectGrant(
                    project_id,
                    principal_type,
                    role_id=role_id,
                    user_id=user_id,
                    granted_by_uid=actor_principal.uid,
                    status="active",
                    granted_at=utc_now(),
                )
            uow.commit()
            return grant

    def list(self, actor_principal, project_id):
        with self.unit_of_work_factory() as uow:
            self._require_active(uow, actor_principal.uid)
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("Project not found")
            self._require_project_manager(self.authorization, actor_principal, uow, project_id)
            if hasattr(uow, "project_grants"):
                return list(uow.project_grants.list_for_project(project_id))
            return list(uow.memberships.list_for_project(project_id))

    def revoke(self, actor_principal, grant_id):
        with self.unit_of_work_factory() as uow:
            self._require_active(uow, actor_principal.uid)
            if hasattr(uow, "project_grants"):
                grant = uow.project_grants.get_by_id(grant_id)
                if grant is None:
                    raise NotFoundError("Grant not found")
                self._require_project_manager(self.authorization, actor_principal, uow, grant.project_id)
                uow.project_grants.delete(grant_id)
                if grant.principal_type == "user" and grant.user_id:
                    uow.memberships.revoke(grant.user_id, grant.project_id)
            uow.commit()
