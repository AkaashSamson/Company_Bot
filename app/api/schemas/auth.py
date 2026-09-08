from typing import List, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, description="first.last@mclarensv.com")
    password: str = Field(..., min_length=1)


class IdentityResponse(BaseModel):
    employee_id: str
    first_name: str
    last_name: str
    email: str
    role_code: str


class RoleResponse(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    is_system: bool


class DocumentRegisterRequest(BaseModel):
    filename: str = Field(..., min_length=1)
    allowed_role_codes: List[str] = Field(default_factory=list)
    allowed_user_ids: List[str] = Field(default_factory=list)


class DocumentRegisterResponse(BaseModel):
    document_id: str
    filename: str
    owner_user_id: str
    allowed_role_codes: List[str]
    allowed_user_ids: List[str]