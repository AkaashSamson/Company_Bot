from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    uid: str
    must_change_password: bool = False
    refresh_token: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    uid: str


class ChangePasswordRequest(BaseModel):
    current_password: str | None = Field(default=None, min_length=1)
    new_password: str = Field(min_length=8)
    uid: str | None = None