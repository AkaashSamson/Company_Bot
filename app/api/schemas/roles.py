from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PermissionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150, pattern="^[A-Z][A-Z0-9_]*$")
    description: str | None = Field(default=None, max_length=255)


class PermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    permission_id: int
    name: str
    description: str | None = None


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    scope: str = Field(default="global", pattern="^(global|department)$")
    department_id: str | None = Field(default=None, min_length=1)
    permission_ids: list[int] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    scope: str | None = Field(default=None, pattern="^(global|department)$")
    department_id: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: int
    name: str
    description: str | None = None
    scope: str
    department_id: str | None = None
    status: str
    created_by_uid: str | None = None
    created_at: datetime
    updated_at: datetime


class RolePermissionsUpdate(BaseModel):
    permission_ids: list[int] = Field(default_factory=list)


class RolePermissionsResponse(BaseModel):
    role_id: int
    permission_ids: list[int]
    permissions: list[PermissionResponse]


class UserPermissionsResponse(BaseModel):
    uid: str
    permissions: list[str]
