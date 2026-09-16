from typing import Protocol

from app.domain.ports.organization_repositories import (
    DepartmentMemberRepository,
    DepartmentRepository,
    DocumentGrantRepository,
    MembershipRepository,
    PermissionRepository,
    ProjectGrantRepository,
    ProjectRepository,
    RoleRepository,
    UserRepository,
)
from app.domain.ports.document_repository import DocumentRepository
from app.domain.ports.sequence_repository import SequenceRepository


class UnitOfWork(Protocol):
    users: UserRepository
    departments: DepartmentRepository
    projects: ProjectRepository
    documents: DocumentRepository
    memberships: MembershipRepository
    department_members: DepartmentMemberRepository
    roles: RoleRepository
    permissions: PermissionRepository
    project_grants: ProjectGrantRepository
    document_grants: DocumentGrantRepository
    sequences: SequenceRepository

    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exc_type, exc_value, traceback) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
