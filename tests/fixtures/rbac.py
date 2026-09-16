from app.domain.entities.organization_models import Department, User
from app.domain.services.authorization_service import OrganizationAuthorizationService
from app.infrastructure.persistence.rbac_seed import seed_rbac
from app.use_cases.organization.role_management import RoleManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def build_rbac_context(users=None, departments=None):
    admin = User("admin", "Admin", "admin@example.com", "Admin", "d1")
    manager = User("mgr", "Manager", "mgr@example.com", "Manager", "d1")
    all_departments = [Department("d1", "Engineering"), Department("d2", "QA")]
    all_departments.extend(departments or [])
    unit_of_work = InMemoryUnitOfWork([admin, manager, *(users or [])], all_departments)
    seed_rbac(lambda: unit_of_work)
    authorization = OrganizationAuthorizationService(unit_of_work)
    service = RoleManagementService(lambda: unit_of_work, authorization)
    return service, unit_of_work
