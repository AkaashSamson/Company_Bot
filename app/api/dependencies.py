from fastapi import Depends, HTTPException, Request

from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_service import OrganizationAuthorizationService
from app.infrastructure.persistence.factory import create_unit_of_work
from app.use_cases.organization.user_management import UserManagementService
from app.use_cases.organization.membership_management import MembershipManagementService
from app.use_cases.organization.project_management import ProjectManagementService
from app.use_cases.organization.document_management import DocumentManagementService
from app.infrastructure.ingestion.provisioner import provision_document, remove_document
from app.domain.services.authentication_service import AuthenticationServiceImpl
from app.infrastructure.authentication.password_hasher import PasswordHasher
from app.core.settings import AUTH_SECRET_KEY


def get_authentication_service():
    return AuthenticationServiceImpl(create_unit_of_work, PasswordHasher(), AUTH_SECRET_KEY)


def get_current_principal(
    request: Request,
    authentication_service: AuthenticationServiceImpl = Depends(get_authentication_service),
) -> AuthenticatedPrincipal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            try:
                service = authentication_service or get_authentication_service()
                principal = service.resolve_token(authorization[7:].strip())
            except Exception:
                principal = None
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return principal


def get_chat_principal(
    request: Request,
    authentication_service: AuthenticationServiceImpl = Depends(get_authentication_service),
) -> AuthenticatedPrincipal | None:
    try:
        return get_current_principal(request, authentication_service)
    except HTTPException:
        return getattr(request.state, "principal", None)


def get_unit_of_work():
    return create_unit_of_work()


def get_authorization_service():
    return OrganizationAuthorizationService(create_unit_of_work())


def get_user_management_service():
    return UserManagementService(create_unit_of_work, PasswordHasher())


def get_project_management_service():
    return ProjectManagementService(create_unit_of_work)


def get_membership_management_service():
    return MembershipManagementService(create_unit_of_work)


def get_document_management_service():
    return DocumentManagementService(
        create_unit_of_work,
        ingestion_handler=provision_document,
        deletion_handler=remove_document,
    )
