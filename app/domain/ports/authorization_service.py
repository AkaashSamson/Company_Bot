from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    uid: str


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
