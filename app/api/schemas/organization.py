from pydantic import BaseModel, ConfigDict, EmailStr, Field


class DepartmentCreate(BaseModel):
    department_id: str = Field(min_length=1)
    department_name: str = Field(min_length=1)


class DepartmentResponse(DepartmentCreate):
    model_config = ConfigDict(from_attributes=True)
    status: str


class UserCreate(BaseModel):
    uid: str = Field(min_length=1)
    name: str = Field(min_length=1)
    email: EmailStr
    role: str = Field(min_length=1)
    department_id: str = Field(min_length=1)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    email: EmailStr | None = None
    role: str | None = Field(default=None, min_length=1)
    department_id: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")


class UserResponse(UserCreate):
    model_config = ConfigDict(from_attributes=True)
    status: str
