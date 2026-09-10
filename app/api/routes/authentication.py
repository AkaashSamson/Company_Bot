from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import get_authentication_service, get_current_principal
from app.api.schemas.authentication import ChangePasswordRequest, LoginRequest, LoginResponse
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authentication_service import AuthenticationServiceImpl
from app.domain.services.organization_errors import AuthenticationError, ForbiddenError
from app.infrastructure.audit.authentication_events import record_authentication_event


router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, service: AuthenticationServiceImpl = Depends(get_authentication_service)):
    try:
        principal = service.authenticate(payload.username, payload.password)
    except AuthenticationError as error:
        record_authentication_event("login", success=False)
        raise HTTPException(status_code=401, detail="Invalid credentials") from error
    record_authentication_event("login", uid=principal.uid, success=True)
    return LoginResponse(access_token=principal.token or "", uid=principal.uid)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    service: AuthenticationServiceImpl = Depends(get_authentication_service),
):
    try:
        if payload.uid and payload.uid != principal.uid:
            service.admin_change_password(principal, payload.uid, payload.new_password)
        else:
            if not payload.current_password:
                raise AuthenticationError("Current password is required")
            service.change_password(principal, payload.current_password, payload.new_password)
    except AuthenticationError as error:
        record_authentication_event("password_change", uid=principal.uid, success=False)
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ForbiddenError as error:
        record_authentication_event("password_change", uid=principal.uid, success=False)
        raise HTTPException(status_code=403, detail=str(error)) from error
    record_authentication_event("password_change", uid=principal.uid, success=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(principal: AuthenticatedPrincipal = Depends(get_current_principal)):
    record_authentication_event("logout", uid=principal.uid, success=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)