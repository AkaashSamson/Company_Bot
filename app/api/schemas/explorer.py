from datetime import datetime

from pydantic import BaseModel


class ExplorerPerson(BaseModel):
    uid: str
    name: str | None


class ExplorerMember(BaseModel):
    uid: str
    name: str | None
    membership_role: str
    status: str
    joined_at: datetime


class ExplorerDocument(BaseModel):
    document_id: str
    document_name: str
    file_type: str | None
    version: str
    status: str
    uploaded_by: ExplorerPerson | None
    uploaded_at: datetime | None
    description: str | None
    access: str
    granted_by: ExplorerPerson | None
    granted_at: datetime | None


class ExplorerProject(BaseModel):
    project_id: str
    project_name: str
    description: str | None
    department_id: str
    department_name: str
    status: str
    manager: ExplorerPerson | None
    members_visible: bool
    members: list[ExplorerMember]
    documents: list[ExplorerDocument]


class ExplorerDepartment(BaseModel):
    department_id: str
    department_name: str
    projects: list[ExplorerProject]


class OrganizationExplorerResponse(BaseModel):
    departments: list[ExplorerDepartment]
    unassigned_documents: list[ExplorerDocument]
    additional_documents: list[ExplorerDocument]