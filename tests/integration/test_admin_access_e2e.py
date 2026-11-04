from app.domain.entities.organization_models import Department, Project, User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_service import OrganizationAuthorizationService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_admin_bypasses_explicit_project_membership():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    projects = [Project("p1", "Project A", "d1"), Project("p2", "Project B", "d2")]
    service = OrganizationAuthorizationService(
        InMemoryUnitOfWork(
            users=[admin],
            departments=[Department("d1", "Engineering"), Department("d2", "QA")],
            projects=projects,
        )
    )
    assert service.authorized_project_ids(AuthenticatedPrincipal("a1")) == ["p1", "p2"]
    assert service.authorized_project_ids(AuthenticatedPrincipal("a1"), "p2") == ["p2"]
