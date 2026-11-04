from typing import Protocol

from app.domain.ports.organization_repositories import (
    DepartmentRepository,
    MembershipRepository,
    PermissionRepository,
    ProjectRepository,
    RoleRepository,
    UserRepository,
)
from app.domain.ports.document_repository import DocumentRepository


class UnitOfWork(Protocol):
    users: UserRepository
    departments: DepartmentRepository
    projects: ProjectRepository
    documents: DocumentRepository
    memberships: MembershipRepository
    roles: RoleRepository
    permissions: PermissionRepository

    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exc_type, exc_value, traceback) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
