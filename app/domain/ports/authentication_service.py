from typing import Protocol

from app.domain.ports.authorization_service import AuthenticatedPrincipal


class AuthenticationService(Protocol):
    def authenticate(self, username: str, password: str) -> AuthenticatedPrincipal: ...

    def change_password(self, principal: AuthenticatedPrincipal, current_password: str, new_password: str) -> None: ...