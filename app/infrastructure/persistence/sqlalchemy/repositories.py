from datetime import datetime, timezone

from sqlalchemy import select, update

from app.domain.entities.organization_models import (
    Department,
    Document,
    Permission,
    Project,
    Role,
    User,
    UserProject,
)
from app.infrastructure.persistence.sqlalchemy.models import (
    DepartmentRecord,
    DocumentRecord,
    PermissionRecord,
    ProjectRecord,
    RolePermissionRecord,
    RoleRecord,
    UserProjectRecord,
    UserRecord,
)


def _user(record: UserRecord) -> User:
    pwd = getattr(record, "password_hash", None) or getattr(record, "password_representation", "")
    return User(
        record.uid, record.name, record.email, record.role, record.department_id,
        record.status, record.created_at, record.updated_at,
        record.username or record.uid, pwd,
        record.password_changed_at, record.must_change_password,
        record.employee_id, record.first_name, record.last_name,
        role_id=getattr(record, "role_id", None),
        job_title=getattr(record, "job_title", None),
        password_hash=pwd,
    )


def _department(record: DepartmentRecord) -> Department:
    return Department(
        record.department_id, record.department_name, record.status,
        record.created_at, record.updated_at,
        record.description, record.default_billable,
    )


def _project(record: ProjectRecord) -> Project:
    return Project(
        record.project_id, record.project_name, record.department_id, record.status,
        record.created_at, record.updated_at,
        record.description, record.manager_uid, record.start_date, record.end_date,
        record.created_by_uid, internal_id=record.id,
    )


def _document(record: DocumentRecord) -> Document:
    return Document(
        record.document_id, record.document_name, record.project_id, record.status,
        record.created_at, record.updated_at,
        internal_id=record.id,
        original_filename=record.original_filename,
        file_type=record.file_type,
        description=record.description,
        version=record.version,
        storage_location=record.storage_location,
        uploaded_by=record.uploaded_by,
        uploaded_at=record.uploaded_at,
        file_hash=getattr(record, 'file_hash', None),
    )


def _membership(record: UserProjectRecord) -> UserProject:
    return UserProject(
        record.uid, record.project_id, record.assigned_by_uid, record.status,
        record.assigned_at, record.membership_role, record.left_at,
        role_id=getattr(record, "role_id", None),
    )


def _permission(record: PermissionRecord) -> Permission:
    return Permission(record.id, record.name, record.description, record.created_at, record.updated_at)


def _role(record: RoleRecord) -> Role:
    return Role(
        record.id, record.name, record.description, record.scope,
        record.department_id, record.status, record.created_by_uid,
        record.created_at, record.updated_at,
    )


class SqlAlchemyUserRepository:
    def __init__(self, session):
        self.session = session

    def get_by_uid(self, uid):
        record = self.session.get(UserRecord, uid)
        return _user(record) if record else None

    def get_by_email(self, email):
        record = self.session.scalar(select(UserRecord).where(UserRecord.email == email))
        return _user(record) if record else None

    def get_by_username(self, username):
        record = self.session.scalar(select(UserRecord).where(UserRecord.username == username))
        return _user(record) if record else None

    def get_by_employee_id(self, employee_id):
        record = self.session.scalar(select(UserRecord).where(UserRecord.employee_id == employee_id))
        return _user(record) if record else None

    def list(self):
        return [_user(record) for record in self.session.scalars(select(UserRecord)).all()]

    def save(self, user):
        record = self.session.get(UserRecord, user.uid)
        if record is None:
            record = UserRecord(uid=user.uid)
            self.session.add(record)
        record.name = user.name
        record.username = user.username or user.uid
        record.email = user.email
        record.role = user.role
        record.department_id = user.department_id
        record.status = user.status
        record.created_at = user.created_at
        record.updated_at = user.updated_at
        pwd = getattr(user, "password_hash", None) or getattr(user, "password_representation", "")
        record.password_hash = pwd
        record.password_representation = pwd
        record.password_changed_at = user.password_changed_at
        record.must_change_password = user.must_change_password
        record.employee_id = user.employee_id
        record.first_name = user.first_name
        record.last_name = user.last_name
        record.role_id = getattr(user, "role_id", None)
        record.job_title = getattr(user, "job_title", None)
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
        record.description = department.description
        record.default_billable = department.default_billable
        self.session.flush()
        return _department(record)


class SqlAlchemyProjectRepository:
    def __init__(self, session):
        self.session = session

    def get(self, project_id):
        record = self.session.scalar(select(ProjectRecord).where(ProjectRecord.project_id == project_id))
        return _project(record) if record else None

    def get_by_internal_id(self, internal_id):
        record = self.session.get(ProjectRecord, internal_id)
        return _project(record) if record else None

    def list(self):
        return [_project(record) for record in self.session.scalars(select(ProjectRecord).order_by(ProjectRecord.project_id)).all()]

    def list_active(self):
        records = self.session.scalars(select(ProjectRecord).where(ProjectRecord.status == "active")).all()
        return [_project(record) for record in records]

    def save(self, project):
        record = self.session.scalar(select(ProjectRecord).where(ProjectRecord.project_id == project.project_id))
        if record is None:
            record = ProjectRecord(project_id=project.project_id)
            self.session.add(record)
        record.project_name = project.project_name
        record.department_id = project.department_id
        record.status = project.status
        record.created_at = project.created_at
        record.updated_at = project.updated_at
        record.description = project.description
        record.manager_uid = project.manager_uid
        record.start_date = project.start_date
        record.end_date = project.end_date
        record.created_by_uid = project.created_by_uid
        self.session.flush()
        return _project(record)


class SqlAlchemyDocumentRepository:
    def __init__(self, session):
        self.session = session

    def get(self, document_id):
        record = self.session.scalar(select(DocumentRecord).where(DocumentRecord.document_id == document_id))
        return _document(record) if record else None

    def get_by_internal_id(self, internal_id):
        record = self.session.get(DocumentRecord, internal_id)
        return _document(record) if record else None

    def list(self):
        return [_document(record) for record in self.session.scalars(select(DocumentRecord).order_by(DocumentRecord.document_id)).all()]

    def save(self, document):
        record = self.session.scalar(select(DocumentRecord).where(DocumentRecord.document_id == document.document_id))
        if record is None:
            record = DocumentRecord(document_id=document.document_id)
            self.session.add(record)
        record.document_name = document.document_name
        record.project_id = document.project_id
        record.status = document.status
        record.created_at = document.created_at
        record.updated_at = document.updated_at
        record.original_filename = document.original_filename
        record.file_type = document.file_type
        record.description = document.description
        record.version = document.version
        record.storage_location = document.storage_location
        record.uploaded_by = document.uploaded_by
        record.uploaded_at = document.uploaded_at
        record.file_hash = getattr(document, 'file_hash', None)
        self.session.flush()
        return _document(record)

    def delete(self, document_id, **kwargs):
        record = self.session.scalar(select(DocumentRecord).where(DocumentRecord.document_id == document_id))
        if record:
            self.session.delete(record)

    def purge(self, document_id):
        self.delete(document_id)


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
        record.membership_role = membership.membership_role
        record.left_at = membership.left_at
        record.role_id = getattr(membership, "role_id", None)
        self.session.flush()
        return _membership(record)

    def revoke(self, uid, project_id):
        record = self.session.get(UserProjectRecord, (uid, project_id))
        if record:
            record.status = "revoked"
            self.session.flush()


class SqlAlchemyPermissionRepository:
    def __init__(self, session):
        self.session = session

    def get(self, permission_id):
        record = self.session.get(PermissionRecord, permission_id)
        return _permission(record) if record else None

    def get_by_name(self, name):
        record = self.session.scalar(select(PermissionRecord).where(PermissionRecord.name == name))
        return _permission(record) if record else None

    def list(self):
        return [_permission(record) for record in self.session.scalars(select(PermissionRecord).order_by(PermissionRecord.name)).all()]

    def save(self, permission):
        record = self.session.get(PermissionRecord, permission.permission_id) if permission.permission_id else None
        if record is None:
            record = PermissionRecord()
            self.session.add(record)
        record.name = permission.name
        record.description = permission.description
        record.created_at = permission.created_at
        record.updated_at = permission.updated_at
        self.session.flush()
        return _permission(record)


class SqlAlchemyRoleRepository:
    def __init__(self, session):
        self.session = session

    def get(self, role_id):
        record = self.session.get(RoleRecord, role_id)
        return _role(record) if record else None

    def get_by_name(self, name):
        record = self.session.scalar(select(RoleRecord).where(RoleRecord.name == name))
        return _role(record) if record else None

    def list(self):
        return [_role(record) for record in self.session.scalars(select(RoleRecord).order_by(RoleRecord.name)).all()]

    def save(self, role):
        record = self.session.get(RoleRecord, role.role_id) if role.role_id else None
        if record is None:
            record = RoleRecord()
            self.session.add(record)
        record.name = role.name
        record.description = role.description
        record.scope = role.scope
        record.department_id = role.department_id
        record.status = role.status
        record.created_by_uid = role.created_by_uid
        record.created_at = role.created_at
        record.updated_at = role.updated_at
        self.session.flush()
        return _role(record)

    def delete(self, role_id):
        record = self.session.get(RoleRecord, role_id)
        if record:
            self.session.delete(record)
            self.session.flush()

    def permissions_for_role(self, role_id):
        records = self.session.scalars(
            select(PermissionRecord)
            .join(RolePermissionRecord, RolePermissionRecord.permission_id == PermissionRecord.id)
            .where(RolePermissionRecord.role_id == role_id)
            .order_by(PermissionRecord.name)
        ).all()
        return [_permission(record) for record in records]

    def set_permissions(self, role_id, permission_ids, granted_by_uid=None):
        current = self.session.scalars(
            select(RolePermissionRecord).where(RolePermissionRecord.role_id == role_id)
        ).all()
        for record in current:
            self.session.delete(record)
        self.session.flush()
        for permission_id in sorted(set(permission_ids)):
            self.session.add(RolePermissionRecord(role_id=role_id, permission_id=permission_id, granted_by_uid=granted_by_uid))
        self.session.flush()
