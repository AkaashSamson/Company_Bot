from datetime import datetime, timezone

from app.domain.entities.organization_models import Department, Project, User, UserProject
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def test_repository_contract_supports_user_department_project_and_membership_lifecycle():
    now = datetime.now(timezone.utc)
    user = User("u1", "Asha", "asha@example.com", "Developer", "d1", created_at=now, updated_at=now)
    department = Department("d1", "Engineering", created_at=now, updated_at=now)
    project = Project("p1", "Project A", "d1", created_at=now, updated_at=now)
    membership = UserProject("u1", "p1", assigned_at=now)
    unit_of_work = InMemoryUnitOfWork([user], [department], [project], [membership])

    with unit_of_work as current:
        assert current.users.get_by_uid("u1").email == "asha@example.com"
        assert current.departments.get("d1").department_name == "Engineering"
        assert current.projects.list_active()[0].project_id == "p1"
        assert current.memberships.list_for_user("u1")[0].project_id == "p1"
