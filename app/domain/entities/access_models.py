from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class RoleModel:
    """A named permission group a user can be assigned to."""

    name: str
    code: str
    description: Optional[str] = None
    is_system: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class UserModel:
    """An application user account.

    ``employee_id`` is the system-wide unique identifier (e.g. ``MSS001``) and
    doubles as the login identity subject. ``extra`` keeps the model open for
    new fields without schema migrations.
    """

    employee_id: str
    first_name: str
    last_name: str
    email: str
    role_code: str
    password_hash: str
    is_active: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DocumentModel:
    """A document registered in the knowledge base.

    ``document_id`` is a stable, human-readable unique id (e.g. ``DOC001``)
    and is written into every Chroma chunk so retrieval can restrict queries
    to authorized documents without duplicating permissions in Chroma.
    """

    filename: str
    owner_user_id: str = ""
    status: str = "active"
    document_id: str = ""
    allowed_role_codes: List[str] = field(default_factory=list)
    allowed_user_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AccessPolicy:
    """Caption describing who can access a document."""

    document_id: str
    owner_user_id: str
    allowed_role_codes: List[str] = field(default_factory=list)
    allowed_user_ids: List[str] = field(default_factory=list)
