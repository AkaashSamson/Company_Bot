from sqlalchemy import inspect

from app.domain.entities.organization_models import Department, DepartmentMember, User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_service import OrganizationAuthorizationService
from app.infrastructure.authentication.bootstrap import bootstrap_admin
from app.infrastructure.authentication.password_hasher import PasswordHasher
from app.infrastructure.persistence.rbac_seed import seed_rbac
from app.infrastructure.persistence.sqlalchemy.session import create_engine_and_session_factory, initialize_database
from app.infrastructure.persistence.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
from app.use_cases.organization.role_management import RoleManagementService


def test_rbac_end_to_end(tmp_path):
    database_path = tmp_path / "rbac.db"
    engine, session_factory = create_engine_and_session_factory(f"sqlite:///{database_path}")
    initialize_database(engine)
    hasher = PasswordHasher()
    assert bootstrap_admin(lambda: SqlAlchemyUnitOfWork(session_factory), hasher, "admin", "seed-password")

    first = seed_rbac(lambda: SqlAlchemyUnitOfWork(session_factory))
    assert first == {"permissions_created": 25, "roles_created": 5}

    second = seed_rbac(lambda: SqlAlchemyUnitOfWork(session_factory))
    assert second == {"permissions_created": 0, "roles_created": 0}

    role_columns = {column["name"] for column in inspect(engine).get_columns("roles")}
    assert {"scope", "department_id", "created_by_uid"} <= role_columns

    with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        unit_of_work.departments.save(Department("d1", "Engineering"))
        unit_of_work.users.save(User("dev", "Dev", "dev@example.com", "Developer", "d1"))
        permission_id = unit_of_work.permissions.get_by_name("USER_CREATE").permission_id
        unit_of_work.commit()

    authorization = OrganizationAuthorizationService(SqlAlchemyUnitOfWork(session_factory))
    service = RoleManagementService(lambda: SqlAlchemyUnitOfWork(session_factory), authorization)

    assert len(authorization.permissions_for_user("admin")) == 25
    assert authorization.has_permission(AuthenticatedPrincipal("dev"), "DOCUMENT_VIEW") is True
    assert authorization.has_permission(AuthenticatedPrincipal("dev"), "USER_CREATE") is False

    role = service.create_role(
        "admin", "Engineering Lead", "Engineering lead",
        scope="department", department_id="d1", permission_ids=[permission_id],
    )
    assert role.scope == "department"
    assert role.department_id == "d1"

    with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        unit_of_work.department_members.save(DepartmentMember("dev", "d1", membership_role="Engineering Lead"))
        unit_of_work.commit()

    assert authorization.has_permission(AuthenticatedPrincipal("dev"), "USER_CREATE") is True

    with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        view_id = unit_of_work.permissions.get_by_name("USER_VIEW").permission_id
    service.set_role_permissions("admin", role.role_id, [view_id])

    assert authorization.has_permission(AuthenticatedPrincipal("dev"), "USER_CREATE") is False

    with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        persisted = unit_of_work.roles.get(role.role_id)
        granted = {permission.name for permission in unit_of_work.roles.permissions_for_role(role.role_id)}
    assert persisted.scope == "department"
    assert persisted.department_id == "d1"
    assert granted == {"USER_VIEW"}

    service.create_permission("admin", "REPORT_EXPORT", "Export reports")
    with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        assert unit_of_work.permissions.get_by_name("REPORT_EXPORT") is not None

    engine.dispose()
