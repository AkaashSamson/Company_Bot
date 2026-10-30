from app.domain.entities.organization_models import Department, Project, UserProject
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_engine import AuthorizationEngine
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
    auth = AuthorizationEngine(lambda: SqlAlchemyUnitOfWork(session_factory))

    # 1. Create departments and project
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.departments.save(Department("d1", "Engineering", default_billable="billable"))
        uow.departments.save(Department("d2", "Product", default_billable="non-billable"))
        uow.projects.save(Project("p1", "Titan", "d1", status="active", manager_uid="admin"))
        uow.commit()

    # 2. Create users in d1
    first = users.create_user("admin", "u1", "Asha Rao", "asha@example.com", "Developer", "d1", first_name="Asha", last_name="Rao")
    second = users.create_user("admin", "u2", "Bob Rao", "bob@example.com", "Developer", "d1", first_name="Bob", last_name="Rao")
    assert first.employee_id == "MSS-001"
    assert second.employee_id == "MSS-002"

    # 3. Assign u1 to project p1 (Engineering Project)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.memberships.save(UserProject("u1", "p1", status="active", assigned_by_uid="admin", membership_role="Developer"))
        uow.commit()

    # 4. Verify d1 users via list_department_users
    d1_users = users.list_department_users("admin", "d1")
    assert len(d1_users) == 2
    uids = {u.uid for u in d1_users}
    assert "u1" in uids and "u2" in uids

    # 5. Verify d1 members via DepartmentMembershipService adapter
    d1_members = memberships.list_for_department("admin", "d1")
    assert len(d1_members) == 2
    by_uid = {m.user_id: m for m in d1_members}
    assert by_uid["u1"].billable_status == "billable"
    assert by_uid["u2"].billable_status == "billable"

    # 6. Move user u1 from Engineering (d1) to Product (d2)
    users.update_user("admin", "u1", {"department_id": "d2"})

    d1_after_move = users.list_department_users("admin", "d1")
    d2_after_move = users.list_department_users("admin", "d2")
    assert [u.uid for u in d1_after_move] == ["u2"]
    assert [u.uid for u in d2_after_move] == ["u1"]

    # 7. Crucial check: User u1 retains project p1 membership and access even though department changed!
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        p1_mem = uow.memberships.get("u1", "p1")
        assert p1_mem is not None
        assert p1_mem.status == "active"

    assert auth.can_access_project(AuthenticatedPrincipal("u1"), "p1") is True

    # 8. User u2 leaves department d1
    memberships.leave("admin", "u2", "d1")
    assert users.get_user("u2").status == "inactive"
    assert len(users.list_department_users("admin", "d1")) == 0

    engine.dispose()
