from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import (
    get_current_principal,
    get_membership_management_service,
    get_project_management_service,
    get_user_management_service,
)
from app.api.schemas.organization import (
    DepartmentCreate,
    DepartmentResponse,
    ProjectCreate,
    ProjectResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError

router = APIRouter(prefix="/api", tags=["organization"])


def _error(error):
    if isinstance(error, ConflictError):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, NotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, ForbiddenError):
        return HTTPException(status_code=403, detail=str(error))
    return HTTPException(status_code=400, detail=str(error))


@router.get("/organization/status")
def organization_status():
    return {"status": "ready"}


@router.post("/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department(
    payload: DepartmentCreate,
    principal=Depends(get_current_principal),
    service=Depends(get_user_management_service),
):
    try:
        return service.create_department(principal.uid, payload.department_id, payload.department_name)
    except Exception as error:
        raise _error(error) from error


@router.get("/departments", response_model=list[DepartmentResponse])
def list_departments(
    principal=Depends(get_current_principal),
    service=Depends(get_user_management_service),
):
    return service.list_departments()


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    principal=Depends(get_current_principal),
    service=Depends(get_user_management_service),
):
    try:
        return service.create_user(principal.uid, **payload.model_dump())
    except Exception as error:
        raise _error(error) from error


@router.get("/users", response_model=list[UserResponse])
def list_users(
    principal=Depends(get_current_principal),
    service=Depends(get_user_management_service),
):
    return service.list_users()


@router.get("/users/{uid}", response_model=UserResponse)
def get_user(
    uid: str,
    principal=Depends(get_current_principal),
    service=Depends(get_user_management_service),
):
    try:
        return service.get_user(uid, principal.uid)
    except Exception as error:
        raise _error(error) from error


@router.patch("/users/{uid}", response_model=UserResponse)
def update_user(
    uid: str,
    payload: UserUpdate,
    principal=Depends(get_current_principal),
    service=Depends(get_user_management_service),
):
    try:
        return service.update_user(principal.uid, uid, payload.model_dump(exclude_unset=True))
    except Exception as error:
        raise _error(error) from error


@router.delete("/users/{uid}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    uid: str,
    principal=Depends(get_current_principal),
    service=Depends(get_user_management_service),
):
    try:
        service.deactivate_user(principal.uid, uid)
    except Exception as error:
        raise _error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    principal=Depends(get_current_principal),
    service=Depends(get_project_management_service),
):
    try:
        return service.create_project(principal.uid, **payload.model_dump())
    except Exception as error:
        raise _error(error) from error


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(
    principal=Depends(get_current_principal),
    service=Depends(get_project_management_service),
):
    try:
        return service.list_projects(principal.uid)
    except Exception as error:
        raise _error(error) from error


@router.post("/projects/{project_id}/members/{uid}", status_code=status.HTTP_204_NO_CONTENT)
def assign_member(
    project_id: str,
    uid: str,
    principal=Depends(get_current_principal),
    service=Depends(get_membership_management_service),
):
    try:
        service.assign(principal.uid, uid, project_id)
    except Exception as error:
        raise _error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/projects/{project_id}/members/{uid}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_member(
    project_id: str,
    uid: str,
    principal=Depends(get_current_principal),
    service=Depends(get_membership_management_service),
):
    try:
        service.revoke(principal.uid, uid, project_id)
    except Exception as error:
        raise _error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
