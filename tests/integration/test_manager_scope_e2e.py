from app.domain.entities.organization_models import Department, User
from app.domain.services.organization_errors import ForbiddenError
from app.use_cases.organization.user_management import UserManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_denied_manager_update_does_not_change_user():
    manager = User("m1", "Manager", "m@example.com", "Manager", "d1")
    target = User("u2", "User", "u@example.com", "Developer", "d2")
    uow = InMemoryUnitOfWork(
        users=[manager, target],
        departments=[Department("d1", "Engineering"), Department("d2", "QA")],
    )
    service = UserManagementService(lambda: uow)
    try:
        service.update_user("m1", "u2", {"name": "Changed"})
    except ForbiddenError:
        pass
    assert uow.users.get_by_uid("u2").name == "User"
