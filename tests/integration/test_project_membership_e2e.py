from datetime import datetime, timezone

from app.domain.entities.organization_models import Department, Project, User
from app.infrastructure.persistence.sqlalchemy.session import create_engine_and_session_factory, initialize_database
from app.infrastructure.persistence.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
from app.use_cases.organization.membership_management import MembershipManagementService


def test_sqlite_membership_is_bidirectional_and_idempotent():
    engine, session_factory = create_engine_and_session_factory("sqlite:///:memory:")
    initialize_database(engine)
    now = datetime.now(timezone.utc)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.departments.save(Department("d1", "Engineering", created_at=now, updated_at=now))
        uow.users.save(User("a1", "Admin", "a@example.com", "Admin", "d1", created_at=now, updated_at=now))
        uow.users.save(User("u1", "User", "u@example.com", "Developer", "d1", created_at=now, updated_at=now))
        uow.projects.save(Project("p1", "Project A", "d1", created_at=now, updated_at=now))
        uow.commit()

    service = MembershipManagementService(lambda: SqlAlchemyUnitOfWork(session_factory))
    service.assign("a1", "u1", "p1")
    service.assign("a1", "u1", "p1")

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert len(uow.memberships.list_for_user("u1")) == 1
        assert len(uow.memberships.list_for_project("p1")) == 1
