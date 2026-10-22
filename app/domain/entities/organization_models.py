from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class User:
    uid: str
    name: str
    email: str
    role: str
    department_id: str
    status: str = "active"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    username: str = ""
    password_representation: str = ""
    password_changed_at: Optional[datetime] = None
    must_change_password: bool = False
    employee_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role_id: Optional[int] = None
    job_title: Optional[str] = None
    password_hash: str = ""

    def __post_init__(self):
        if not self.username:
            self.username = self.uid
        if not self.password_hash and self.password_representation:
            self.password_hash = self.password_representation
        elif not self.password_representation and self.password_hash:
            self.password_representation = self.password_hash


@dataclass(slots=True)
class Department:
    department_id: str
    department_name: str
    status: str = "active"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    description: Optional[str] = None
    default_billable: str = "billable"


@dataclass(slots=True)
class Project:
    project_id: str
    project_name: str
    department_id: str
    status: str = "active"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    description: Optional[str] = None
    manager_uid: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    created_by_uid: Optional[str] = None
    internal_id: Optional[int] = None


@dataclass(slots=True)
class Document:
    document_id: str
    document_name: str
    project_id: Optional[str] = None
    status: str = "active"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    internal_id: Optional[int] = None
    original_filename: Optional[str] = None
    file_type: Optional[str] = None
    description: Optional[str] = None
    version: str = "1.0"
    storage_location: Optional[str] = None
    uploaded_by: Optional[str] = None
    uploaded_at: Optional[datetime] = None


@dataclass(slots=True)
class UserProject:
    uid: str
    project_id: str
    assigned_by_uid: Optional[str] = None
    status: str = "active"
    assigned_at: datetime = field(default_factory=utc_now)
    membership_role: str = "Member"
    left_at: Optional[datetime] = None
    role_id: Optional[int] = None


@dataclass(slots=True)
class DepartmentMember:
    user_id: str
    department_id: str
    membership_role: str = "Member"
    billable_status: Optional[str] = None
    assigned_by_uid: Optional[str] = None
    status: str = "active"
    assigned_at: datetime = field(default_factory=utc_now)
    left_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Permission:
    permission_id: Optional[int]
    name: str
    description: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Role:
    role_id: Optional[int]
    name: str
    description: Optional[str] = None
    scope: str = "global"
    department_id: Optional[str] = None
    status: str = "active"
    created_by_uid: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class ProjectGrant:
    project_id: str
    principal_type: str
    role_id: Optional[int] = None
    user_id: Optional[str] = None
    granted_by_uid: Optional[str] = None
    status: str = "active"
    granted_at: datetime = field(default_factory=utc_now)
    internal_id: Optional[int] = None


@dataclass(slots=True)
class DocumentGrant:
    document_id: str
    principal_type: str
    permission: str = "read"
    role_id: Optional[int] = None
    user_id: Optional[str] = None
    granted_by_uid: Optional[str] = None
    status: str = "active"
    granted_at: datetime = field(default_factory=utc_now)
    internal_id: Optional[int] = None
