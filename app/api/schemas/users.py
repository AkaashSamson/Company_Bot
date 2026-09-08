from typing import Optional

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=60)
    last_name: str = Field(..., min_length=1, max_length=60)
    role_code: str = Field(
        ...,
        description="manager, tester, solution_architect or developer",
    )
    email: Optional[str] = Field(
        default=None,
        description="Defaults to <first>.<last>@<domain> when omitted",
    )
    password: Optional[str] = Field(
        default=None,
        description="Defaults to the employee id for the MVP",
    )


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    role_code: Optional[str] = None
    extra: Optional[dict] = None


class UserResponse(BaseModel):
    employee_id: str
    first_name: str
    last_name: str
    email: str
    role_code: str
    is_active: bool
    created_at: Optional[str] = None