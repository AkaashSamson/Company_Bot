from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies.auth import Identity, get_current_user
from app.api.schemas.auth import (
    DocumentRegisterRequest,
    DocumentRegisterResponse,
    IdentityResponse,
    LoginRequest,
    RoleResponse,
)
from app.api.schemas.users import UserCreate, UserResponse, UserUpdate
from app.db.roles_repository import RolesRepository
from app.use_cases.access.access_control_service import AccessControlService
from app.use_cases.access.auth_service import (
    AuthError,
    DocumentRegistrationService,
    UserManagementService,
)

router = APIRouter(tags=["auth"])


def _require_identity(identity: Identity) -> None:
    if not identity.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )


def _serialize_user(user: dict) -> UserResponse:
    return UserResponse(
        employee_id=user["employee_id"],
        first_name=user["first_name"],
        last_name=user["last_name"],
        email=user["email"],
        role_code=user["role_code"],
        is_active=bool(user["is_active"]),
        created_at=user.get("created_at"),
    )


@router.post("/api/auth/login", response_model=IdentityResponse)
def login(request: LoginRequest):
    service = UserManagementService(seed_roles=True)
    try:
        identity = service.authenticate(request.email, request.password)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )
    return identity


@router.post("/api/users", response_model=IdentityResponse, status_code=status.HTTP_201_CREATED)
def register_user(request: UserCreate, identity: Identity = Depends(get_current_user)):
    """Create a user. Restricted to managers for the MVP."""
    _require_identity(identity)
    if identity.role_code != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only managers can create users",
        )
    service = UserManagementService(seed_roles=True)
    try:
        return service.register_user(
            first_name=request.first_name,
            last_name=request.last_name,
            role_code=request.role_code,
            email=request.email,
            password=request.password,
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/users", response_model=list[UserResponse])
def list_users(identity: Identity = Depends(get_current_user)):
    _require_identity(identity)
    return [
        _serialize_user(user)
        for user in UserManagementService(seed_roles=False).list_users()
    ]


@router.get("/api/users/{employee_id}", response_model=UserResponse)
def get_user(employee_id: str, identity: Identity = Depends(get_current_user)):
    _require_identity(identity)
    user = UserManagementService(seed_roles=False).get_user(employee_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{employee_id}' not found")
    return _serialize_user(user)


@router.put("/api/users/{employee_id}", response_model=UserResponse)
def update_user(
    employee_id: str,
    request: UserUpdate,
    identity: Identity = Depends(get_current_user),
):
    _require_identity(identity)
    if identity.role_code != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only managers can update users",
        )
    updates = request.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        user = UserManagementService(seed_roles=False).update_user(employee_id, updates)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize_user(user)


@router.post("/api/users/{employee_id}/deactivate", response_model=UserResponse)
def deactivate_user(employee_id: str, identity: Identity = Depends(get_current_user)):
    _require_identity(identity)
    if identity.role_code != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only managers can deactivate users",
        )
    try:
        user = UserManagementService(seed_roles=False).deactivate(employee_id)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize_user(user)


@router.post("/api/users/{employee_id}/activate", response_model=UserResponse)
def activate_user(employee_id: str, identity: Identity = Depends(get_current_user)):
    _require_identity(identity)
    if identity.role_code != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only managers can activate users",
        )
    try:
        user = UserManagementService(seed_roles=False).activate(employee_id)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize_user(user)


@router.get("/api/roles", response_model=list[RoleResponse])
def list_roles(identity: Identity = Depends(get_current_user)):
    _require_identity(identity)
    roles = RolesRepository().list_all()
    return [
        RoleResponse(
            code=role.code,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
        )
        for role in roles
    ]


@router.post(
    "/api/documents/register",
    response_model=DocumentRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_document(
    request: DocumentRegisterRequest,
    identity: Identity = Depends(get_current_user),
):
    """Register a document and its access policy in MongoDB.

    The document id returned here is later written into every Chroma chunk by
    the ingestion pipeline.
    """
    _require_identity(identity)
    allowed_roles, allowed_users = (
        AccessControlService.normalize_allow_lists(
            request.allowed_role_codes,
            request.allowed_user_ids,
        ).values()
    )
    service = DocumentRegistrationService()
    try:
        result = service.register_document(
            filename=request.filename,
            owner_employee_id=identity.employee_id,
            allowed_role_codes=allowed_roles,
            allowed_user_ids=allowed_users,
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return DocumentRegisterResponse(
        document_id=result["document_id"],
        filename=result["filename"],
        owner_user_id=result["owner_user_id"],
        allowed_role_codes=allowed_roles,
        allowed_user_ids=allowed_users,
    )