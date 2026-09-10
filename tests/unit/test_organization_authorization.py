from app.domain.entities.organization_models import Department, Project, User, UserProject
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_service import OrganizationAuthorizationService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_manager_can_manage_same_department_project():
    manager = User("m1", "Manager", "m@example.com", "Manager", "d1")
    project = Project("p1", "Project A", "d1")
    service = OrganizationAuthorizationService(
        InMemoryUnitOfWork([manager], [Department("d1", "Engineering")], [project])
    )
    assert service.can_manage_project(AuthenticatedPrincipal("m1"), "p1") is True


def test_manager_cannot_manage_other_department_project():
    manager = User("m1", "Manager", "m@example.com", "Manager", "d1")
    project = Project("p2", "Project B", "d2")
    service = OrganizationAuthorizationService(
        InMemoryUnitOfWork([manager], [Department("d1", "Engineering"), Department("d2", "QA")], [project])
    )
    assert service.can_manage_project(AuthenticatedPrincipal("m1"), "p2") is False


def test_admin_can_access_all_active_projects():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    projects = [Project("p1", "Project A", "d1"), Project("p2", "Project B", "d2")]
    service = OrganizationAuthorizationService(InMemoryUnitOfWork([admin], projects=projects))
    assert service.authorized_project_ids(AuthenticatedPrincipal("a1")) == ["p1", "p2"]
