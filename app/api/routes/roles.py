from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import get_current_principal, get_role_management_service
from app.api.schemas.roles import (
    PermissionCreate,
    PermissionResponse,
    RoleCreate,
    RolePermissionsResponse,
    RolePermissionsUpdate,
    RoleResponse,
    RoleUpdate,
    UserPermissionsResponse,
)
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError


router = APIRouter(prefix="/api", tags=["roles"])


def _error(error):
    if isinstance(error, ConflictError):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, NotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, ForbiddenError):
        return HTTPException(status_code=403, detail=str(error))
    return HTTPException(status_code=400, detail=str(error))


def _role_permissions_response(role_id, permissions):
    return RolePermissionsResponse(
        role_id=role_id,
        permission_ids=[permission.permission_id for permission in permissions],
        permissions=[PermissionResponse.model_validate(permission) for permission in permissions],
    )


@router.get("/permissions", response_model=list[PermissionResponse])
def list_permissions(
    principal=Depends(get_current_principal),
    service=Depends(get_role_management_service),
):
    try:
        return service.list_permissions(principal.uid)
    except Exception as error:
        raise _error(error) from error


@router.post("/permissions", response_model=PermissionResponse, status_code=status.HTTP_201_CREATED)
def create_permission(
    payload: PermissionCreate,
    principal=Depends(get_current_principal),
    service=Depends(get_role_management_service),
):
    try:
        return service.create_permission(principal.uid, payload.name, payload.description)
    except Exception as error:
        raise _error(error) from error


@router.get("/roles", response_model=list[RoleResponse])
def list_roles(
    principal=Depends(get_current_principal),
    service=Depends(get_role_management_service),
):
    try:
        return service.list_roles(principal.uid)
    except Exception as error:
        raise _error(error) from error


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    principal=Depends(get_current_principal),
    service=Depends(get_role_management_service),
):
    try:
        return service.create_role(
            principal.uid, payload.name, payload.description,
            payload.scope, payload.department_id, payload.permission_ids,
        )
    except Exception as error:
        raise _error(error) from error


@router.get("/roles/{role_id}", response_model=RoleResponse)
def get_role(
    role_id: int,
    principal=Depends(get_current_principal),
    service=Depends(get_role_management_service),
):
    try:
        return service.get_role(principal.uid, role_id)
    except Exception as error:
        raise _error(error) from error


@router.patch("/roles/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: int,
    payload: RoleUpdate,
    principal=Depends(get_current_principal),
    service=Depends(get_role_management_service),
):
    try:
        return service.update_role(principal.uid, role_id, payload.model_dump(exclude_unset=True))
    except Exception as error:
        raise _error(error) from error


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: int,
    principal=Depends(get_current_principal),
    service=Depends(get_role_management_service),
):
    try:
        service.delete_role(principal.uid, role_id)
    except Exception as error:
        raise _error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/roles/{role_id}/permissions", response_model=RolePermissionsResponse)
def list_role_permissions(
    role_id: int,
    principal=Depends(get_current_principal),
    service=Depends(get_role_management_service),
):
    try:
        permissions = service.list_role_permissions(principal.uid, role_id)
    except Exception as error:
        raise _error(error) from error
    return _role_permissions_response(role_id, permissions)


@router.put("/roles/{role_id}/permissions", response_model=RolePermissionsResponse)
def set_role_permissions(
    role_id: int,
    payload: RolePermissionsUpdate,
    principal=Depends(get_current_principal),
    service=Depends(get_role_management_service),
):
    try:
        service.set_role_permissions(principal.uid, role_id, payload.permission_ids)
        permissions = service.list_role_permissions(principal.uid, role_id)
    except Exception as error:
        raise _error(error) from error
    return _role_permissions_response(role_id, permissions)


@router.get("/users/{uid}/permissions", response_model=UserPermissionsResponse)
def get_user_permissions(
    uid: str,
    principal=Depends(get_current_principal),
    service=Depends(get_role_management_service),
):
    try:
        return UserPermissionsResponse(uid=uid, permissions=service.effective_permissions(principal.uid, uid))
    except Exception as error:
        raise _error(error) from error


@router.get("/users/{uid}/roles", response_model=list[RoleResponse])
def get_user_roles(
    uid: str,
    principal=Depends(get_current_principal),
    service=Depends(get_role_management_service),
):
    try:
        return service.roles_for_user(principal.uid, uid)
    except Exception as error:
        raise _error(error) from error
