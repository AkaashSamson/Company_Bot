from pathlib import Path

from app.domain.entities.organization_models import Department
from app.domain.services.authentication_service import AuthenticationServiceImpl
from app.infrastructure.authentication.bootstrap import bootstrap_admin
from app.infrastructure.authentication.password_hasher import PasswordHasher
from app.use_cases.organization.user_management import UserManagementService
from tests.fixtures.organization_repositories import InMemoryUnitOfWork
from app.infrastructure.persistence.sqlalchemy.session import create_engine_and_session_factory, initialize_database
from app.infrastructure.persistence.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork


def test_bootstrap_admin_manager_and_employee_onboarding():
    database_path = Path("instance") / "test-authentication.db"
    database_path.unlink(missing_ok=True)
    engine, session_factory = create_engine_and_session_factory(f"sqlite:///{database_path}")
    initialize_database(engine)
    unit_of_work = SqlAlchemyUnitOfWork(session_factory)
    hasher = PasswordHasher()
    assert bootstrap_admin(lambda: SqlAlchemyUnitOfWork(session_factory), hasher, "admin", "default-password")
    assert not bootstrap_admin(lambda: SqlAlchemyUnitOfWork(session_factory), hasher, "admin", "default-password")

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.departments.save(Department("d1", "Engineering"))
        uow.commit()

    auth = AuthenticationServiceImpl(lambda: SqlAlchemyUnitOfWork(session_factory), hasher, "a" * 32)
    admin = auth.authenticate("admin", "default-password")
    auth.change_password(admin, "default-password", "changed-password")

    user_service = UserManagementService(lambda: SqlAlchemyUnitOfWork(session_factory), hasher)
    manager = user_service.create_user(admin.uid, "manager", "Manager", "manager@example.com", "Manager", "d1", "manager", "manager-password")
    manager_principal = auth.authenticate("manager", "manager-password")
    employee = user_service.create_user(manager_principal.uid, "employee", "Employee", "employee@example.com", "Developer", "d1", "employee", "employee-password")

    assert employee.username == "employee"
    assert auth.authenticate("employee", "employee-password").uid == "employee"
    engine.dispose()