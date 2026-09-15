from datetime import datetime, timezone

import pytest

from app.domain.entities.organization_models import Department, Project, User
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError
from app.use_cases.organization.project_management import ProjectManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork


def _service(uow, prefix="PROJ"):
    return ProjectManagementService(lambda: uow, project_id_prefix=prefix)


def _uow(users, departments, projects=None):
    return InMemoryUnitOfWork(users, departments, projects)


def test_create_project_autogenerates_human_readable_id():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    uow = _uow([admin], [Department("d1", "Engineering")])
    project = _service(uow).create_project("a1", project_name="Project A", department_id="d1")
    assert project.project_id == "PROJ-001"
    assert project.internal_id == 1
    assert project.created_by_uid == "a1"


def test_create_project_computes_next_sequential_id():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    uow = _uow([admin], [Department("d1", "Engineering")], [Project("PROJ-003", "Existing", "d1")])
    project = _service(uow).create_project("a1", project_name="Project B", department_id="d1")
    assert project.project_id == "PROJ-004"


def test_create_project_respects_custom_prefix():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    uow = _uow([admin], [Department("d1", "Engineering")])
    project = _service(uow, prefix="NEX-PROJ").create_project("a1", project_name="Project C", department_id="d1")
    assert project.project_id == "NEX-PROJ-001"


def test_create_project_with_explicit_id_and_details():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    manager = User("m1", "Manager", "m@example.com", "Manager", "d1")
    uow = _uow([admin, manager], [Department("d1", "Engineering")])
    project = _service(uow).create_project(
        "a1",
        project_id="p-custom",
        project_name="Project D",
        department_id="d1",
        description="A team",
        manager_uid="m1",
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )
    assert project.project_id == "p-custom"
    assert project.description == "A team"
    assert project.manager_uid == "m1"
    assert project.created_by_uid == "a1"


def test_create_project_requires_active_admin():
    manager = User("m1", "Manager", "m@example.com", "Manager", "d1")
    uow = _uow([manager], [Department("d1", "Engineering")])
    with pytest.raises(ForbiddenError):
        _service(uow).create_project("m1", project_name="X", department_id="d1")


def test_create_project_rejects_duplicate_id():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    uow = _uow([admin], [Department("d1", "Engineering")], [Project("p1", "Existing", "d1")])
    with pytest.raises(ConflictError):
        _service(uow).create_project("a1", project_id="p1", project_name="Y", department_id="d1")


def test_create_project_requires_existing_department():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    uow = _uow([admin], [])
    with pytest.raises(NotFoundError):
        _service(uow).create_project("a1", project_id="p1", project_name="Y", department_id="ghost")


def test_create_project_rejects_manager_from_other_department():
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    other = User("m1", "Manager", "m@example.com", "Manager", "d2")
    uow = _uow([admin, other], [Department("d1", "Engineering"), Department("d2", "QA")])
    with pytest.raises(ForbiddenError):
        _service(uow).create_project("a1", project_id="p1", project_name="Y", department_id="d1", manager_uid="m1")


def test_get_project_by_human_readable_id():
    user = User("u1", "User", "u@example.com", "Developer", "d1")
    project = Project("p1", "Project A", "d1")
    uow = _uow([user], [Department("d1", "Engineering")], [project], )
    assert _service(uow).get_project("u1", "p1").project_id == "p1"


def test_same_department_user_cannot_get_out_of_scope_project():
    user = User("u1", "User", "u@example.com", "Developer", "d1")
    uow = _uow([user], [Department("d1", "Engineering"), Department("d2", "QA")], [Project("p2", "Project B", "d2")])
    with pytest.raises(ForbiddenError):
        _service(uow).get_project("u1", "p2")


def test_update_project_by_same_department_manager():
    manager = User("m1", "Manager", "m@example.com", "Manager", "d1")
    project = Project("p1", "Project A", "d1")
    uow = _uow([manager], [Department("d1", "Engineering")], [project])
    updated = _service(uow).update_project("m1", "p1", {"description": "updated"})
    assert updated.description == "updated"


def test_designated_project_manager_updates_own_project():
    manager = User("m1", "Manager", "m@example.com", "Developer", "d2")
    project = Project("p1", "Project A", "d1", manager_uid="m1")
    uow = _uow([manager], [Department("d1", "Engineering"), Department("d2", "QA")], [project])
    updated = _service(uow).update_project("m1", "p1", {"description": "my project"})
    assert updated.description == "my project"


def test_project_manager_cannot_update_other_project():
    manager = User("m1", "Manager", "m@example.com", "Developer", "d2")
    projects = [Project("p1", "Project A", "d1", manager_uid="m1"), Project("p2", "Project B", "d1")]
    uow = _uow([manager], [Department("d1", "Engineering"), Department("d2", "QA")], projects)
    with pytest.raises(ForbiddenError):
        _service(uow).update_project("m1", "p2", {"description": "nope"})


def test_only_admin_can_change_project_manager():
    manager = User("m1", "Manager", "m@example.com", "Developer", "d2")
    replacement = User("r1", "Replacement", "r@example.com", "Developer", "d1")
    project = Project("p1", "Project A", "d1", manager_uid="m1")
    uow = _uow([manager, replacement], [Department("d1", "Engineering"), Department("d2", "QA")], [project])
    with pytest.raises(ForbiddenError):
        _service(uow).update_project("m1", "p1", {"manager_uid": "r1"})
    admin = User("a1", "Admin", "a@example.com", "Admin", "d1")
    uow.users.save(admin)
    updated = _service(uow).update_project("a1", "p1", {"manager_uid": "r1"})
    assert updated.manager_uid == "r1"


def test_non_admin_cannot_move_project_between_departments():
    manager = User("m1", "Manager", "m@example.com", "Manager", "d1")
    project = Project("p1", "Project A", "d1")
    uow = _uow([manager], [Department("d1", "Engineering"), Department("d2", "QA")], [project])
    with pytest.raises(ForbiddenError):
        _service(uow).update_project("m1", "p1", {"department_id": "d2"})