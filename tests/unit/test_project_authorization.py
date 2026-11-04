from app.domain.entities.organization_models import Department, Project, User, UserProject
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_service import OrganizationAuthorizationService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_missing_project_selection_returns_all_authorized_projects():
    user = User("u1", "User", "u@example.com", "Developer", "d1")
    projects = [Project("p1", "Project A", "d1"), Project("p2", "Project B", "d1")]
    memberships = [UserProject("u1", "p1"), UserProject("u1", "p2")]
    service = OrganizationAuthorizationService(
        InMemoryUnitOfWork([user], [Department("d1", "Engineering")], projects, memberships)
    )
    assert service.authorized_project_ids(AuthenticatedPrincipal("u1")) == ["p1", "p2"]


def test_selected_project_is_intersected_with_authorized_projects():
    user = User("u1", "User", "u@example.com", "Developer", "d1")
    projects = [Project("p1", "Project A", "d1"), Project("p2", "Project B", "d1")]
    memberships = [UserProject("u1", "p1")]
    service = OrganizationAuthorizationService(
        InMemoryUnitOfWork([user], [Department("d1", "Engineering")], projects, memberships)
    )
    assert service.authorized_project_ids(AuthenticatedPrincipal("u1"), "p1") == ["p1"]
    assert service.authorized_project_ids(AuthenticatedPrincipal("u1"), "p2") == []
