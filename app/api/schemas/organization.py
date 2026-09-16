from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class DepartmentCreate(BaseModel):
    department_id: str | None = Field(default=None, min_length=1)
    department_name: str = Field(min_length=1)
    description: str | None = Field(default=None, max_length=500)
    default_billable: str = Field(default="billable", pattern="^(billable|non-billable|both)$")


class DepartmentUpdate(BaseModel):
    department_name: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, max_length=500)
    default_billable: str | None = Field(default=None, pattern="^(billable|non-billable|both)$")
    status: str | None = Field(default=None, pattern="^(active|inactive)$")


class DepartmentResponse(DepartmentCreate):
    model_config = ConfigDict(from_attributes=True)
    department_id: str
    status: str


class UserCreate(BaseModel):
    uid: str = Field(min_length=1)
    username: str | None = Field(default=None, min_length=1)
    name: str = Field(min_length=1)
    email: EmailStr
    role: str = Field(min_length=1)
    department_id: str = Field(min_length=1)
    initial_password: str | None = Field(default=None, min_length=8)
    employee_id: str | None = Field(default=None, min_length=1, max_length=64)
    first_name: str | None = Field(default=None, min_length=1, max_length=200)
    last_name: str | None = Field(default=None, min_length=1, max_length=200)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    email: EmailStr | None = None
    role: str | None = Field(default=None, min_length=1)
    department_id: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")
    employee_id: str | None = Field(default=None, min_length=1, max_length=64)
    first_name: str | None = Field(default=None, min_length=1, max_length=200)
    last_name: str | None = Field(default=None, min_length=1, max_length=200)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    username: str
    name: str
    email: str
    role: str
    department_id: str
    status: str
    employee_id: str | None
    first_name: str | None
    last_name: str | None


class DepartmentMemberAssign(BaseModel):
    user_id: str = Field(min_length=1)
    billable_status: str | None = Field(default=None, pattern="^(billable|non-billable)$")
    membership_role: str = Field(default="Member", min_length=1)


class DepartmentMemberUpdate(BaseModel):
    billable_status: str | None = Field(default=None, pattern="^(billable|non-billable)$")
    membership_role: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")


class DepartmentMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    department_id: str
    membership_role: str
    billable_status: str | None
    status: str
    assigned_at: datetime
    left_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    project_id: str | None = Field(default=None, min_length=1)
    project_name: str = Field(min_length=1)
    department_id: str = Field(min_length=1)
    description: str | None = Field(default=None, max_length=500)
    manager_uid: str | None = Field(default=None, min_length=1)
    start_date: datetime | None = None
    end_date: datetime | None = None


class ProjectUpdate(BaseModel):
    project_name: str | None = Field(default=None, min_length=1)
    department_id: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, max_length=500)
    manager_uid: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, pattern="^(active|inactive|completed|archived)$")
    start_date: datetime | None = None
    end_date: datetime | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    internal_id: int
    project_id: str
    project_name: str
    department_id: str
    status: str
    description: str | None
    manager_uid: str | None
    start_date: datetime | None
    end_date: datetime | None
    created_by_uid: str | None
    created_at: datetime
    updated_at: datetime


class ProjectMemberAssign(BaseModel):
    membership_role: str | None = Field(default=None, min_length=1)


class ProjectMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    project_id: str
    membership_role: str
    status: str
    assigned_at: datetime
    left_at: datetime | None


class ProjectAccessGrantCreate(BaseModel):
    principal_type: str = Field(pattern="^(role|user)$")
    role_id: int | None = None
    user_id: str | None = Field(default=None, min_length=1)


class ProjectGrantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    internal_id: int
    project_id: str
    principal_type: str
    role_id: int | None
    user_id: str | None
    status: str
    granted_by_uid: str | None
    granted_at: datetime