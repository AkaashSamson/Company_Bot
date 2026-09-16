from app.domain.entities.organization_models import Department
from app.infrastructure.authentication.bootstrap import bootstrap_admin
from app.infrastructure.authentication.password_hasher import PasswordHasher
from app.infrastructure.persistence.sqlalchemy.session import create_engine_and_session_factory, initialize_database
from app.infrastructure.persistence.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
from app.use_cases.organization.department_membership import DepartmentMembershipService
from app.use_cases.organization.user_management import UserManagementService


def test_department_membership_lifecycle_end_to_end(tmp_path):
    database_path = tmp_path / "department-membership.db"
    engine, session_factory = create_engine_and_session_factory(f"sqlite:///{database_path}")
    initialize_database(engine)
    hasher = PasswordHasher()
    assert bootstrap_admin(lambda: SqlAlchemyUnitOfWork(session_factory), hasher, "admin", "seed-password")

    users = UserManagementService(lambda: SqlAlchemyUnitOfWork(session_factory), hasher)
    memberships = DepartmentMembershipService(lambda: SqlAlchemyUnitOfWork(session_factory))

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.departments.save(Department("d1", "Engineering", default_billable="billable"))
        uow.commit()

    first = users.create_user("admin", "u1", "Asha Rao", "asha@example.com", "Developer", "d1", first_name="Asha", last_name="Rao")
    second = users.create_user("admin", "u2", "Bob Rao", "bob@example.com", "Developer", "d1", first_name="Bob", last_name="Rao")
    assert first.employee_id == "MSS-001"
    assert second.employee_id == "MSS-002"
    assert first.first_name == "Asha"

    default_member = memberships.assign("admin", "u1", "d1")
    override_member = memberships.assign("admin", "u2", "d1", billable_status="non-billable")
    assert default_member.billable_status is None
    assert override_member.billable_status == "non-billable"

    users.update_department("admin", "d1", {"default_billable": "non-billable"})

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        department = uow.departments.get("d1")
        current = {member.user_id: member for member in uow.department_members.list_for_department("d1")}

    assert department.default_billable == "non-billable"
    assert current["u1"].billable_status is None
    assert current["u1"].billable_status or department.default_billable == "non-billable"
    assert current["u2"].billable_status == "non-billable"

    left = memberships.leave("admin", "u1", "d1")
    assert left.status == "inactive"
    assert left.left_at is not None

    members = memberships.list_for_department("admin", "d1")
    assert len(members) == 2
    assert any(member.user_id == "u1" and member.status == "inactive" for member in members)

    for_user = memberships.list_for_user("admin", "u2")
    assert len(for_user) == 1
    assert for_user[0].user_id == "u2"

    engine.dispose()