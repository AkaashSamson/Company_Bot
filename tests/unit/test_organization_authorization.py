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


def test_project_access_contact_exposes_only_project_and_manager():
    manager = User("m1", "Sara Blake", "m@example.com", "Manager", "d1")
    project = Project("p1", "Project Atlas", "d1", manager_uid="m1")
    service = OrganizationAuthorizationService(
        InMemoryUnitOfWork([manager], [Department("d1", "Engineering")], [project])
    )
    assert service.project_access_contact("p1") == {
        "project_id": "p1",
        "project_name": "Project Atlas",
        "manager_name": "Sara Blake",
    }


def test_project_access_contact_unknown_project_is_none():
    service = OrganizationAuthorizationService(
        InMemoryUnitOfWork([User("m1", "Sara", "m@example.com", "Manager", "d1")])
    )
    assert service.project_access_contact("nope") is None
