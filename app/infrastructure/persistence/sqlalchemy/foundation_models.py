from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.sqlalchemy.models import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RoleRecord(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="global")
    department_id: Mapped[Optional[str]] = mapped_column(ForeignKey("departments.department_id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by_uid: Mapped[Optional[str]] = mapped_column(ForeignKey("users.uid"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class PermissionRecord(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class RolePermissionRecord(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True, index=True)
    granted_by_uid: Mapped[Optional[str]] = mapped_column(ForeignKey("users.uid"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)


class DepartmentMemberRecord(Base):
    __tablename__ = "department_members"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.uid", ondelete="CASCADE"), primary_key=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.department_id", ondelete="CASCADE"), primary_key=True, index=True)
    membership_role: Mapped[str] = mapped_column(String(200), nullable=False, default="Member")
    assigned_by_uid: Mapped[Optional[str]] = mapped_column(ForeignKey("users.uid"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)
    billable_status: Mapped[Optional[str]] = mapped_column(String(32))
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class DocumentPermissionRecord(Base):
    __tablename__ = "document_permissions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "principal_type", "role_id", "user_id", "permission",
            name="uq_document_permission",
        ),
        CheckConstraint(
            "principal_type IN ('role', 'user') AND ("
            "(principal_type = 'role' AND role_id IS NOT NULL AND user_id IS NULL) OR "
            "(principal_type = 'user' AND user_id IS NOT NULL AND role_id IS NULL)"
            ")",
            name="ck_document_permissions_principal",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False, index=True)
    principal_type: Mapped[str] = mapped_column(String(12), nullable=False)
    role_id: Mapped[Optional[int]] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.uid", ondelete="CASCADE"), index=True)
    permission: Mapped[str] = mapped_column(String(32), nullable=False)
    granted_by_uid: Mapped[Optional[str]] = mapped_column(ForeignKey("users.uid"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class ProjectGrantRecord(Base):
    __tablename__ = "project_grants"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "principal_type", "role_id", "user_id",
            name="uq_project_grant",
        ),
        CheckConstraint(
            "principal_type IN ('role', 'user') AND ("
            "(principal_type = 'role' AND role_id IS NOT NULL AND user_id IS NULL) OR "
            "(principal_type = 'user' AND user_id IS NOT NULL AND role_id IS NULL)"
            ")",
            name="ck_project_grants_principal",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True)
    principal_type: Mapped[str] = mapped_column(String(12), nullable=False)
    role_id: Mapped[Optional[int]] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.uid", ondelete="CASCADE"), index=True)
    granted_by_uid: Mapped[Optional[str]] = mapped_column(ForeignKey("users.uid"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)