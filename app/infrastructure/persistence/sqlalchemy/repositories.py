from datetime import datetime, timezone

from sqlalchemy import select, update

from app.domain.entities.organization_models import (
    Department,
    DepartmentMember,
    Document,
    DocumentGrant,
    Permission,
    Project,
    ProjectGrant,
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

DepartmentMemberRecord = None
DocumentPermissionRecord = None
ProjectGrantRecord = None
BusinessIdSequenceRecord = None


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
    )


def _membership(record: UserProjectRecord) -> UserProject:
    return UserProject(
        record.uid, record.project_id, record.assigned_by_uid, record.status,
        record.assigned_at, record.membership_role, record.left_at,
        role_id=getattr(record, "role_id", None),
    )


def _department_member(record: DepartmentMemberRecord) -> DepartmentMember:
    return DepartmentMember(
        record.user_id, record.department_id, record.membership_role,
        record.billable_status, record.assigned_by_uid, record.status,
        record.assigned_at, record.left_at, record.created_at, record.updated_at,
    )


def _permission(record: PermissionRecord) -> Permission:
    return Permission(record.id, record.name, record.description, record.created_at, record.updated_at)


def _role(record: RoleRecord) -> Role:
    return Role(
        record.id, record.name, record.description, record.scope,
        record.department_id, record.status, record.created_by_uid,
        record.created_at, record.updated_at,
    )


def _project_grant(record: ProjectGrantRecord) -> ProjectGrant:
    return ProjectGrant(
        record.project_id, record.principal_type,
        role_id=record.role_id, user_id=record.user_id,
        granted_by_uid=record.granted_by_uid, status=record.status,
        granted_at=record.granted_at, internal_id=record.id,
    )


def _document_grant(record: DocumentPermissionRecord) -> DocumentGrant:
    return DocumentGrant(
        record.document_id, record.principal_type,
        permission=record.permission,
        role_id=record.role_id, user_id=record.user_id,
        granted_by_uid=record.granted_by_uid, status=record.status,
        granted_at=record.created_at, internal_id=record.id,
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
        self.session.flush()
        return _document(record)

    def delete(self, document_id):
        record = self.session.scalar(select(DocumentRecord).where(DocumentRecord.document_id == document_id))
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


class SqlAlchemyDepartmentMemberRepository:
    def __init__(self, session):
        self.session = session

    def get(self, user_id, department_id):
        record = self.session.get(DepartmentMemberRecord, (user_id, department_id))
        return _department_member(record) if record else None

    def list_for_user(self, user_id):
        records = self.session.scalars(
            select(DepartmentMemberRecord).where(DepartmentMemberRecord.user_id == user_id)
        ).all()
        return [_department_member(record) for record in records]

    def list_for_department(self, department_id):
        records = self.session.scalars(
            select(DepartmentMemberRecord).where(DepartmentMemberRecord.department_id == department_id)
        ).all()
        return [_department_member(record) for record in records]

    def save(self, member):
        record = self.session.get(DepartmentMemberRecord, (member.user_id, member.department_id))
        if record is None:
            record = DepartmentMemberRecord(user_id=member.user_id, department_id=member.department_id)
            self.session.add(record)
        record.membership_role = member.membership_role
        record.billable_status = member.billable_status
        record.assigned_by_uid = member.assigned_by_uid
        record.status = member.status
        record.assigned_at = member.assigned_at
        record.left_at = member.left_at
        record.created_at = member.created_at
        record.updated_at = member.updated_at
        self.session.flush()
        return _department_member(record)


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


class SqlAlchemyProjectGrantRepository:
    def __init__(self, session):
        self.session = session

    def get(self, project_id, principal_type, role_id=None, user_id=None):
        record = self.session.scalar(
            select(ProjectGrantRecord).where(
                ProjectGrantRecord.project_id == project_id,
                ProjectGrantRecord.principal_type == principal_type,
                ProjectGrantRecord.role_id == role_id,
                ProjectGrantRecord.user_id == user_id,
            )
        )
        return _project_grant(record) if record else None

    def get_by_id(self, grant_id):
        record = self.session.get(ProjectGrantRecord, grant_id)
        return _project_grant(record) if record else None

    def list_for_project(self, project_id):
        records = self.session.scalars(
            select(ProjectGrantRecord)
            .where(ProjectGrantRecord.project_id == project_id, ProjectGrantRecord.status == "active")
            .order_by(ProjectGrantRecord.id)
        ).all()
        return [_project_grant(record) for record in records]

    def project_ids_for_principal(self, user_id, role_ids):
        conditions = [
            (ProjectGrantRecord.principal_type == "user") & (ProjectGrantRecord.user_id == user_id),
        ]
        if role_ids:
            conditions.append(
                (ProjectGrantRecord.principal_type == "role") & ProjectGrantRecord.role_id.in_(role_ids)
            )
        records = self.session.scalars(
            select(ProjectGrantRecord)
            .where(ProjectGrantRecord.status == "active", *conditions)
        ).all()
        return list({record.project_id for record in records})

    def list(self):
        records = self.session.scalars(select(ProjectGrantRecord).order_by(ProjectGrantRecord.id)).all()
        return [_project_grant(record) for record in records]

    def save(self, grant):
        record = self.session.scalar(
            select(ProjectGrantRecord).where(
                ProjectGrantRecord.project_id == grant.project_id,
                ProjectGrantRecord.principal_type == grant.principal_type,
                ProjectGrantRecord.role_id == grant.role_id,
                ProjectGrantRecord.user_id == grant.user_id,
            )
        )
        if record is None:
            record = ProjectGrantRecord(
                project_id=grant.project_id,
                principal_type=grant.principal_type,
                role_id=grant.role_id,
                user_id=grant.user_id,
            )
            self.session.add(record)
        record.granted_by_uid = grant.granted_by_uid
        record.status = grant.status
        record.granted_at = grant.granted_at
        self.session.flush()
        return _project_grant(record)

    def delete(self, grant_id):
        record = self.session.get(ProjectGrantRecord, grant_id)
        if record:
            record.status = "revoked"
            self.session.flush()


class SqlAlchemyDocumentGrantRepository:
    def __init__(self, session):
        self.session = session

    def get(self, grant_id):
        record = self.session.get(DocumentPermissionRecord, grant_id)
        return _document_grant(record) if record else None

    def for_document(self, document_id):
        records = self.session.scalars(
            select(DocumentPermissionRecord)
            .where(DocumentPermissionRecord.document_id == document_id, DocumentPermissionRecord.status == "active")
            .order_by(DocumentPermissionRecord.id)
        ).all()
        return [_document_grant(record) for record in records]

    def document_ids_for_principal(self, user_id, role_ids):
        conditions = [
            (DocumentPermissionRecord.principal_type == "user") & (DocumentPermissionRecord.user_id == user_id),
        ]
        if role_ids:
            conditions.append(
                (DocumentPermissionRecord.principal_type == "role") & DocumentPermissionRecord.role_id.in_(role_ids)
            )
        records = self.session.scalars(
            select(DocumentPermissionRecord)
            .where(DocumentPermissionRecord.status == "active", DocumentPermissionRecord.permission == "read", *conditions)
        ).all()
        return list({record.document_id for record in records})

    def list(self):
        records = self.session.scalars(select(DocumentPermissionRecord).order_by(DocumentPermissionRecord.id)).all()
        return [_document_grant(record) for record in records]

    def save(self, grant):
        record = self.session.scalar(
            select(DocumentPermissionRecord).where(
                DocumentPermissionRecord.document_id == grant.document_id,
                DocumentPermissionRecord.principal_type == grant.principal_type,
                DocumentPermissionRecord.role_id == grant.role_id,
                DocumentPermissionRecord.user_id == grant.user_id,
                DocumentPermissionRecord.permission == grant.permission,
            )
        )
        if record is None:
            record = DocumentPermissionRecord(
                document_id=grant.document_id,
                principal_type=grant.principal_type,
                role_id=grant.role_id,
                user_id=grant.user_id,
                permission=grant.permission,
            )
            self.session.add(record)
        record.granted_by_uid = grant.granted_by_uid
        record.status = grant.status
        record.updated_at = grant.granted_at
        self.session.flush()
        return _document_grant(record)

    def delete(self, grant_id):
        record = self.session.get(DocumentPermissionRecord, grant_id)
        if record:
            record.status = "revoked"
            self.session.flush()


class SqlAlchemySequenceRepository:
    """Atomic, persistent business-ID counters.

    ``allocate`` is a single ``UPDATE ... RETURNING`` statement so concurrent
    transactions always receive distinct values: each writer atomically bumps
    ``last_value`` regardless of any stale reads. The ``INSERT ... ON CONFLICT
    DO NOTHING`` before it merely guarantees the counter row exists on first
    use without failing under concurrent first allocation.
    """

    def __init__(self, session):
        self.session = session

    @staticmethod
    def _insert_ignore(dialect_name, values):
        """Dialect-aware INSERT ... ON CONFLICT DO NOTHING."""
        if dialect_name.startswith("postgresql"):
            from sqlalchemy.dialects.postgresql import insert as postgres_insert

            statement = postgres_insert(BusinessIdSequenceRecord).values(**values)
            return statement.on_conflict_do_nothing(index_elements=[BusinessIdSequenceRecord.sequence_key])
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        statement = sqlite_insert(BusinessIdSequenceRecord).values(**values)
        return statement.on_conflict_do_nothing(index_elements=[BusinessIdSequenceRecord.sequence_key])

    def get(self, sequence_key):
        record = self.session.get(BusinessIdSequenceRecord, sequence_key)
        return record.last_value if record else None

    def initialize(self, sequence_key, prefix, last_value):
        statement = self._insert_ignore(
            self.session.get_bind().dialect.name,
            {
                "sequence_key": sequence_key,
                "prefix": prefix,
                "last_value": last_value,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        self.session.execute(statement)
        self.session.flush()

    def allocate(self, sequence_key, by=1):
        ensure = self._insert_ignore(
            self.session.get_bind().dialect.name,
            {
                "sequence_key": sequence_key,
                "prefix": "",
                "last_value": 0,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        self.session.execute(ensure)
        value = self.session.scalar(
            update(BusinessIdSequenceRecord)
            .where(BusinessIdSequenceRecord.sequence_key == sequence_key)
            .values(
                last_value=BusinessIdSequenceRecord.last_value + by,
                updated_at=datetime.now(timezone.utc),
            )
            .returning(BusinessIdSequenceRecord.last_value)
        )
        self.session.flush()
        if value is None:
            raise RuntimeError(f"Failed to allocate business ID for sequence {sequence_key!r}")
        return value
