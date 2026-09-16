from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import (
    get_current_principal,
    get_department_membership_service,
    get_membership_management_service,
    get_profile_service,
    get_project_access_service,
    get_project_management_service,
    get_user_management_service,
)
from app.api.schemas.organization import (
    DepartmentCreate,
    DepartmentMemberAssign,
    DepartmentMemberResponse,
    DepartmentMemberUpdate,
    DepartmentResponse,
    DepartmentUpdate,
    ProjectAccessGrantCreate,
    ProjectCreate,
    ProjectGrantResponse,
    ProjectMemberAssign,
    ProjectMemberResponse,
    ProjectResponse,
    ProjectUpdate,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.api.schemas.profile import ProfileResponse
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
        return service.create_department(principal.uid, payload.department_id, payload.department_name, payload.description, payload.default_billable)
    except Exception as error:
        raise _error(error) from error


@router.get("/departments", response_model=list[DepartmentResponse])
def list_departments(
    principal=Depends(get_current_principal),
    service=Depends(get_user_management_service),
):
    return service.list_departments()


@router.get("/departments/{department_id}", response_model=DepartmentResponse)
def get_department(
    department_id: str,
    principal=Depends(get_current_principal),
    service=Depends(get_user_management_service),
):
    try:
        return service.get_department(department_id)
    except Exception as error:
        raise _error(error) from error


@router.patch("/departments/{department_id}", response_model=DepartmentResponse)
def update_department(
    department_id: str,
    payload: DepartmentUpdate,
    principal=Depends(get_current_principal),
    service=Depends(get_user_management_service),
):
    try:
        return service.update_department(principal.uid, department_id, payload.model_dump(exclude_unset=True))
    except Exception as error:
        raise _error(error) from error


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


@router.get("/users/{uid}/memberships", response_model=list[DepartmentMemberResponse])
def list_user_memberships(
    uid: str,
    principal=Depends(get_current_principal),
    service=Depends(get_department_membership_service),
):
    try:
        return service.list_for_user(principal.uid, uid)
    except Exception as error:
        raise _error(error) from error


@router.get("/users/me/profile", response_model=ProfileResponse)
def get_my_profile(
    principal=Depends(get_current_principal),
    service=Depends(get_profile_service),
):
    try:
        return ProfileResponse(**service.get_profile(principal))
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


@router.post("/departments/{department_id}/members", response_model=DepartmentMemberResponse, status_code=status.HTTP_201_CREATED)
def assign_department_member(
    department_id: str,
    payload: DepartmentMemberAssign,
    principal=Depends(get_current_principal),
    service=Depends(get_department_membership_service),
):
    try:
        return service.assign(principal.uid, payload.user_id, department_id, payload.billable_status, payload.membership_role)
    except Exception as error:
        raise _error(error) from error


@router.get("/departments/{department_id}/members", response_model=list[DepartmentMemberResponse])
def list_department_members(
    department_id: str,
    principal=Depends(get_current_principal),
    service=Depends(get_department_membership_service),
):
    try:
        return service.list_for_department(principal.uid, department_id)
    except Exception as error:
        raise _error(error) from error


@router.patch("/departments/{department_id}/members/{user_id}", response_model=DepartmentMemberResponse)
def update_department_member(
    department_id: str,
    user_id: str,
    payload: DepartmentMemberUpdate,
    principal=Depends(get_current_principal),
    service=Depends(get_department_membership_service),
):
    try:
        return service.update(principal.uid, user_id, department_id, payload.model_dump(exclude_unset=True))
    except Exception as error:
        raise _error(error) from error


@router.delete("/departments/{department_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def leave_department(
    department_id: str,
    user_id: str,
    principal=Depends(get_current_principal),
    service=Depends(get_department_membership_service),
):
    try:
        service.leave(principal.uid, user_id, department_id)
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


@router.get("/projects/{project_key}", response_model=ProjectResponse)
def get_project(
    project_key: str,
    principal=Depends(get_current_principal),
    service=Depends(get_project_management_service),
):
    try:
        return service.get_project(principal.uid, project_key)
    except Exception as error:
        raise _error(error) from error


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    principal=Depends(get_current_principal),
    service=Depends(get_project_management_service),
):
    try:
        return service.update_project(principal.uid, project_id, payload.model_dump(exclude_unset=True))
    except Exception as error:
        raise _error(error) from error


@router.get("/projects/{project_id}/members", response_model=list[ProjectMemberResponse])
def list_project_members(
    project_id: str,
    principal=Depends(get_current_principal),
    service=Depends(get_membership_management_service),
):
    try:
        return service.list_members(principal.uid, project_id)
    except Exception as error:
        raise _error(error) from error


@router.post("/projects/{project_id}/members/{uid}", status_code=status.HTTP_204_NO_CONTENT)
def assign_member(
    project_id: str,
    uid: str,
    payload: ProjectMemberAssign | None = None,
    principal=Depends(get_current_principal),
    service=Depends(get_membership_management_service),
):
    try:
        service.assign(principal.uid, uid, project_id, payload.membership_role if payload else None)
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


@router.post("/projects/{project_id}/members/me/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_project(
    project_id: str,
    principal=Depends(get_current_principal),
    service=Depends(get_membership_management_service),
):
    try:
        service.leave(principal.uid, project_id)
    except Exception as error:
        raise _error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/access", response_model=list[ProjectGrantResponse])
def list_project_access(
    project_id: str,
    principal=Depends(get_current_principal),
    service=Depends(get_project_access_service),
):
    try:
        return service.list(principal, project_id)
    except Exception as error:
        raise _error(error) from error


@router.post("/projects/{project_id}/access", response_model=ProjectGrantResponse, status_code=status.HTTP_201_CREATED)
def grant_project_access(
    project_id: str,
    payload: ProjectAccessGrantCreate,
    principal=Depends(get_current_principal),
    service=Depends(get_project_access_service),
):
    try:
        return service.grant(principal, project_id, **payload.model_dump())
    except Exception as error:
        raise _error(error) from error


@router.delete("/project-access/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_project_access(
    grant_id: int,
    principal=Depends(get_current_principal),
    service=Depends(get_project_access_service),
):
    try:
        service.revoke(principal, grant_id)
    except Exception as error:
        raise _error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)