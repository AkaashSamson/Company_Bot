from fastapi import Depends, HTTPException, Request
from functools import partial

from app.domain.services.business_id_generator import build_business_id_generator
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authorization_service import OrganizationAuthorizationService
from app.infrastructure.persistence.factory import create_unit_of_work
from app.use_cases.organization.user_management import UserManagementService
from app.use_cases.organization.membership_management import MembershipManagementService
from app.use_cases.organization.department_membership import DepartmentMembershipService
from app.use_cases.organization.project_management import ProjectManagementService
from app.use_cases.organization.role_management import RoleManagementService
from app.use_cases.organization.document_management import DocumentManagementService
from app.use_cases.organization.document_access import DocumentAccessService
from app.use_cases.organization.project_access import ProjectAccessService
from app.use_cases.organization.profile import ProfileService
from app.use_cases.organization.organization_explorer import OrganizationExplorerService
from app.infrastructure.ingestion.provisioner import provision_document, remove_document
from app.infrastructure.document.processor_factory import build_document_processor
from app.domain.services.authentication_service import AuthenticationServiceImpl
from app.infrastructure.authentication.password_hasher import PasswordHasher
from app.core.settings import (
    AUTH_SECRET_KEY,
    DEPARTMENT_ID_PREFIX,
    DOCUMENT_ID_PREFIX,
    EMPLOYEE_ID_PREFIX,
    PROJECT_ID_PREFIX,
)


def get_business_id_generator():
    return build_business_id_generator(
        user_prefix=EMPLOYEE_ID_PREFIX,
        department_prefix=DEPARTMENT_ID_PREFIX,
        project_prefix=PROJECT_ID_PREFIX,
        document_prefix=DOCUMENT_ID_PREFIX,
    )


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
    return UserManagementService(create_unit_of_work, PasswordHasher(), business_id_generator=get_business_id_generator())


def get_project_management_service():
    return ProjectManagementService(create_unit_of_work, business_id_generator=get_business_id_generator())


def get_membership_management_service():
    return MembershipManagementService(create_unit_of_work)


def get_department_membership_service():
    return DepartmentMembershipService(create_unit_of_work)


def get_role_management_service():
    return RoleManagementService(create_unit_of_work, get_authorization_service())


def get_document_processor():
    """Build the document-processing port implementation ingestion will use.

    Composition happens here, in the dependency wiring, so the use cases and the
    provisioner depend only on the port and never on a document-conversion
    library. The concrete parsers are selected by
    :func:`app.infrastructure.document.processor_factory.build_document_processor`.
    """
    return build_document_processor()


def get_document_management_service():
    return DocumentManagementService(
        create_unit_of_work,
        ingestion_handler=partial(provision_document, processor=get_document_processor()),
        deletion_handler=remove_document,
        business_id_generator=get_business_id_generator(),
    )


def get_document_access_service():
    from app.domain.services.authorization_engine import AuthorizationEngine

    return DocumentAccessService(create_unit_of_work, AuthorizationEngine(create_unit_of_work))


def get_project_access_service():
    from app.domain.services.authorization_engine import AuthorizationEngine

    return ProjectAccessService(create_unit_of_work, AuthorizationEngine(create_unit_of_work))


def get_profile_service():
    return ProfileService(create_unit_of_work)


def get_organization_explorer_service():
    return OrganizationExplorerService(create_unit_of_work)
