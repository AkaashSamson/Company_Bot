from dataclasses import dataclass
from typing import Protocol, Sequence

from app.domain.entities.organization_models import Role


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    uid: str
    token: str | None = None
    must_change_password: bool = False
    refresh_token: str | None = None


class AuthorizationService(Protocol):
    def authorized_project_ids(
        self,
        principal: AuthenticatedPrincipal,
        selected_project_id: str | None = None,
    ) -> Sequence[str]: ...

    def can_manage_department(
        self,
        principal: AuthenticatedPrincipal,
        department_id: str,
    ) -> bool: ...

    def can_manage_project(
        self,
        principal: AuthenticatedPrincipal,
        project_id: str,
    ) -> bool: ...

    def can_manage_role(
        self,
        principal: AuthenticatedPrincipal,
        role: Role,
    ) -> bool: ...

    def roles_for_user(self, uid: str) -> Sequence[Role]: ...

    def permissions_for_user(self, uid: str) -> set[str]: ...

    def has_permission(
        self,
        principal: AuthenticatedPrincipal,
        permission: str,
    ) -> bool: ...
