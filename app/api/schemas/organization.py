from pydantic import BaseModel, ConfigDict, EmailStr, Field


class DepartmentCreate(BaseModel):
    department_id: str = Field(min_length=1)
    department_name: str = Field(min_length=1)


class DepartmentResponse(DepartmentCreate):
    model_config = ConfigDict(from_attributes=True)
    status: str


class UserCreate(BaseModel):
    uid: str = Field(min_length=1)
    username: str | None = Field(default=None, min_length=1)
    name: str = Field(min_length=1)
    email: EmailStr
    role: str = Field(min_length=1)
    department_id: str = Field(min_length=1)
    initial_password: str | None = Field(default=None, min_length=8)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    email: EmailStr | None = None
    role: str | None = Field(default=None, min_length=1)
    department_id: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    username: str
    name: str
    email: str
    role: str
    department_id: str
    status: str


class ProjectCreate(BaseModel):
    project_id: str = Field(min_length=1)
    project_name: str = Field(min_length=1)
    department_id: str = Field(min_length=1)


class ProjectResponse(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    status: str
