from app.domain.entities.organization_models import Role
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.ports.unit_of_work import UnitOfWork
from app.domain.services.authorization_engine import AuthorizationEngine, AuthorizationScope


class OrganizationAuthorizationService:
    """Thin facade over the AuthorizationEngine.

    Kept so that all existing call sites and dependency wiring stay the same;
    every decision is delegated to the single AuthorizationEngine.
    """

    def __init__(self, unit_of_work: UnitOfWork):
        self.unit_of_work = unit_of_work
        self.engine = AuthorizationEngine(lambda: self.unit_of_work)

    def authorized_project_ids(self, principal: AuthenticatedPrincipal, selected_project_id=None):
        return self.engine.authorized_project_ids(principal, selected_project_id)

    def is_admin(self, principal: AuthenticatedPrincipal) -> bool:
        return self.engine.is_admin(principal)

    def can_manage_department(self, principal, department_id):
        return self.engine.can_manage_department(principal, department_id)

    def can_manage_project(self, principal, project_id):
        return self.engine.can_manage_project(principal, project_id)

    def can_manage_role(self, principal, role: Role) -> bool:
        return self.engine.can_manage_role(principal, role)

    def roles_for_user(self, uid):
        return self.engine.roles_for_user(uid)

    def permissions_for_user(self, uid):
        return self.engine.permissions_for_user(uid)

    def has_permission(self, principal: AuthenticatedPrincipal, permission: str) -> bool:
        return self.engine.has_permission(principal, permission)

    def authorization_scope(self, principal: AuthenticatedPrincipal, selected_project_id=None) -> AuthorizationScope:
        return self.engine.authorization_scope(principal, selected_project_id)

    def project_access_contact(self, project_id):
        return self.engine.project_access_contact(project_id)