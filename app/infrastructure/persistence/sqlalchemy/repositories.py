from sqlalchemy import select

from app.domain.entities.organization_models import (
    Department,
    Document,
    Project,
    User,
    UserProject,
)
from app.infrastructure.persistence.sqlalchemy.models import (
    DepartmentRecord,
    DocumentRecord,
    ProjectRecord,
    UserProjectRecord,
    UserRecord,
)


def _user(record: UserRecord) -> User:
    return User(record.uid, record.name, record.email, record.role, record.department_id, record.status, record.created_at, record.updated_at)


def _department(record: DepartmentRecord) -> Department:
    return Department(record.department_id, record.department_name, record.status, record.created_at, record.updated_at)


def _project(record: ProjectRecord) -> Project:
    return Project(record.project_id, record.project_name, record.department_id, record.status, record.created_at, record.updated_at)


def _document(record: DocumentRecord) -> Document:
    return Document(record.document_id, record.document_name, record.project_id, record.status, record.created_at, record.updated_at)


def _membership(record: UserProjectRecord) -> UserProject:
    return UserProject(record.uid, record.project_id, record.assigned_by_uid, record.status, record.assigned_at)


class SqlAlchemyUserRepository:
    def __init__(self, session):
        self.session = session

    def get_by_uid(self, uid):
        record = self.session.get(UserRecord, uid)
        return _user(record) if record else None

    def get_by_email(self, email):
        record = self.session.scalar(select(UserRecord).where(UserRecord.email == email))
        return _user(record) if record else None

    def list(self):
        return [_user(record) for record in self.session.scalars(select(UserRecord)).all()]

    def save(self, user):
        record = self.session.get(UserRecord, user.uid)
        if record is None:
            record = UserRecord(uid=user.uid)
            self.session.add(record)
        record.name = user.name
        record.email = user.email
        record.role = user.role
        record.department_id = user.department_id
        record.status = user.status
        record.created_at = user.created_at
        record.updated_at = user.updated_at
        self.session.flush()
        return _user(record)

    def delete(self, uid):
        record = self.session.get(UserRecord, uid)
        if record:
            self.session.delete(record)


class SqlAlchemyDepartmentRepository:
    def __init__(self, session):
        self.session = session

    def get(self, department_id):
        record = self.session.get(DepartmentRecord, department_id)
        return _department(record) if record else None

    def list(self):
        return [_department(record) for record in self.session.scalars(select(DepartmentRecord)).all()]

    def save(self, department):
        record = self.session.get(DepartmentRecord, department.department_id)
        if record is None:
            record = DepartmentRecord(department_id=department.department_id)
            self.session.add(record)
        record.department_name = department.department_name
        record.status = department.status
        record.created_at = department.created_at
        record.updated_at = department.updated_at
        self.session.flush()
        return _department(record)


class SqlAlchemyProjectRepository:
    def __init__(self, session):
        self.session = session

    def get(self, project_id):
        record = self.session.get(ProjectRecord, project_id)
        return _project(record) if record else None

    def list_active(self):
        records = self.session.scalars(select(ProjectRecord).where(ProjectRecord.status == "active")).all()
        return [_project(record) for record in records]

    def save(self, project):
        record = self.session.get(ProjectRecord, project.project_id)
        if record is None:
            record = ProjectRecord(project_id=project.project_id)
            self.session.add(record)
        record.project_name = project.project_name
        record.department_id = project.department_id
        record.status = project.status
        record.created_at = project.created_at
        record.updated_at = project.updated_at
        self.session.flush()
        return _project(record)


class SqlAlchemyDocumentRepository:
    def __init__(self, session):
        self.session = session

    def get(self, document_id):
        record = self.session.get(DocumentRecord, document_id)
        return _document(record) if record else None

    def list(self):
        return [_document(record) for record in self.session.scalars(select(DocumentRecord)).all()]

    def save(self, document):
        record = self.session.get(DocumentRecord, document.document_id)
        if record is None:
            record = DocumentRecord(document_id=document.document_id)
            self.session.add(record)
        record.document_name = document.document_name
        record.project_id = document.project_id
        record.status = document.status
        record.created_at = document.created_at
        record.updated_at = document.updated_at
        self.session.flush()
        return _document(record)

    def delete(self, document_id):
        record = self.session.get(DocumentRecord, document_id)
        if record:
            self.session.delete(record)


class SqlAlchemyMembershipRepository:
    def __init__(self, session):
        self.session = session

    def get(self, uid, project_id):
        record = self.session.get(UserProjectRecord, (uid, project_id))
        return _membership(record) if record else None

    def list_for_user(self, uid):
        records = self.session.scalars(select(UserProjectRecord).where(UserProjectRecord.uid == uid)).all()
        return [_membership(record) for record in records]

    def list_for_project(self, project_id):
        records = self.session.scalars(select(UserProjectRecord).where(UserProjectRecord.project_id == project_id)).all()
        return [_membership(record) for record in records]

    def save(self, membership):
        record = self.session.get(UserProjectRecord, (membership.uid, membership.project_id))
        if record is None:
            record = UserProjectRecord(uid=membership.uid, project_id=membership.project_id)
            self.session.add(record)
        record.assigned_by_uid = membership.assigned_by_uid
        record.status = membership.status
        record.assigned_at = membership.assigned_at
        self.session.flush()
        return _membership(record)

    def revoke(self, uid, project_id):
        record = self.session.get(UserProjectRecord, (uid, project_id))
        if record:
            record.status = "revoked"
            self.session.flush()
