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


@dataclass(slots=True)
class Department:
    department_id: str
    department_name: str
    status: str = "active"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Project:
    project_id: str
    project_name: str
    department_id: str
    status: str = "active"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Document:
    document_id: str
    document_name: str
    project_id: Optional[str] = None
    status: str = "active"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class UserProject:
    uid: str
    project_id: str
    assigned_by_uid: Optional[str] = None
    status: str = "active"
    assigned_at: datetime = field(default_factory=utc_now)
