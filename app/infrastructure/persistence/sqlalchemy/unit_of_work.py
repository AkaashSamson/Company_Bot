from app.infrastructure.persistence.sqlalchemy.repositories import (
    SqlAlchemyDepartmentRepository,
    SqlAlchemyDocumentRepository,
    SqlAlchemyMembershipRepository,
    SqlAlchemyProjectRepository,
    SqlAlchemyUserRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.session = None

    def __enter__(self):
        self.session = self.session_factory()
        self.users = SqlAlchemyUserRepository(self.session)
        self.departments = SqlAlchemyDepartmentRepository(self.session)
        self.projects = SqlAlchemyProjectRepository(self.session)
        self.documents = SqlAlchemyDocumentRepository(self.session)
        self.memberships = SqlAlchemyMembershipRepository(self.session)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.session is None:
            return
        if exc_type is not None:
            self.rollback()
        self.session.close()

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()
