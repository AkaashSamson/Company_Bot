import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import get_authentication_service, get_current_principal
from app.api.schemas.authentication import ChangePasswordRequest, LoginRequest, LoginResponse, RefreshRequest, RefreshResponse
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.authentication_service import AuthenticationServiceImpl
from app.domain.services.organization_errors import AuthenticationError, ForbiddenError
from app.infrastructure.audit.authentication_events import record_authentication_event


router = APIRouter(prefix="/api/auth", tags=["authentication"])
logger = logging.getLogger("knowlayer.authentication")


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, service: AuthenticationServiceImpl = Depends(get_authentication_service)):
    try:
        principal = service.authenticate(payload.username, payload.password)
    except AuthenticationError as error:
        record_authentication_event("login", success=False)
        logger.warning("login failed for identifier %r: %s", payload.username, error)
        raise HTTPException(status_code=401, detail="Invalid credentials") from error
    record_authentication_event("login", uid=principal.uid, success=True)
    logger.info("login succeeded for user %r", principal.uid)
    return LoginResponse(
        access_token=principal.token or "",
        refresh_token=principal.refresh_token or "",
        uid=principal.uid,
        must_change_password=principal.must_change_password,
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh_token(
    payload: RefreshRequest,
    service: AuthenticationServiceImpl = Depends(get_authentication_service),
):
    try:
        uid, access_token, refresh_token = service.refresh_access_token(payload.refresh_token)
    except AuthenticationError as error:
        record_authentication_event("token_refresh", success=False)
        logger.warning("token refresh failed: %s", error)
        raise HTTPException(status_code=401, detail="Invalid refresh token") from error
    record_authentication_event("token_refresh", uid=uid, success=True)
    logger.info("token refreshed for user %r", uid)
    return RefreshResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        uid=uid,
    )


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