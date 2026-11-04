from datetime import datetime

from pydantic import BaseModel


class ProfileUser(BaseModel):
    uid: str
    name: str
    email: str
    employee_id: str | None
    role: str
    status: str


class ProfileDepartment(BaseModel):
    department_id: str
    department_name: str


class ProfileManager(BaseModel):
    uid: str
    name: str | None


class ProfileMembership(BaseModel):
    membership_role: str
    status: str
    joined_at: datetime


class ProfileProject(BaseModel):
    project_id: str
    project_name: str
    project_status: str
    manager: ProfileManager | None
    is_member: bool
    membership: ProfileMembership | None
    access_source: str


class ProfileDocument(BaseModel):
    document_id: str
    document_name: str
    project_id: str | None
    project_name: str | None
    file_type: str | None
    version: str
    status: str
    uploaded_at: datetime | None
    access_source: str


class ProfileRole(BaseModel):
    role_id: int
    name: str
    scope: str
    department_id: str | None
    description: str | None


class ProfileResponse(BaseModel):
    user: ProfileUser
    department: ProfileDepartment | None
    billable_status: str | None
    projects: list[ProfileProject]
    documents: list[ProfileDocument]
    roles: list[ProfileRole]
    permissions: list[str]