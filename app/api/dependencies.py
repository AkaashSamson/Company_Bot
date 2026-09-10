from fastapi import HTTPException, Request

from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_service import OrganizationAuthorizationService
from app.infrastructure.persistence.factory import create_unit_of_work
from app.use_cases.organization.user_management import UserManagementService
from app.use_cases.organization.membership_management import MembershipManagementService
from app.use_cases.organization.project_management import ProjectManagementService


def get_current_principal(request: Request) -> AuthenticatedPrincipal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return principal


def get_chat_principal(request: Request) -> AuthenticatedPrincipal | None:
    return getattr(request.state, "principal", None)


def get_unit_of_work():
    return create_unit_of_work()


def get_authorization_service():
    return OrganizationAuthorizationService(create_unit_of_work())


def get_user_management_service():
    return UserManagementService(create_unit_of_work)


def get_project_management_service():
    return ProjectManagementService(create_unit_of_work)


def get_membership_management_service():
    return MembershipManagementService(create_unit_of_work)
