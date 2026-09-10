from fastapi import HTTPException, Request

from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_service import OrganizationAuthorizationService
from app.infrastructure.persistence.factory import create_unit_of_work


def get_current_principal(request: Request) -> AuthenticatedPrincipal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return principal


def get_unit_of_work():
    return create_unit_of_work()


def get_authorization_service():
    return OrganizationAuthorizationService(create_unit_of_work())
