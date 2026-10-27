from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    document_id: str | None = Field(default=None, min_length=1)
    document_name: str = Field(min_length=1)
    project_id: str | None = None
    source_path: str | None = None
    content: str | None = None
    original_filename: str | None = Field(default=None, min_length=1, max_length=255)
    file_type: str | None = Field(default=None, min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=500)
    version: str = Field(default="1.0", min_length=1, max_length=32)
    async_mode: bool = True


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    internal_id: int | None = None
    document_id: str
    document_name: str
    project_id: str | None = None
    status: str
    original_filename: str | None = None
    file_type: str | None = None
    description: str | None = None
    version: str = "1.0"
    storage_location: str | None = None
    uploaded_by: str | None = None
    uploaded_at: datetime | None = None
    file_hash: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentStatusResponse(BaseModel):
    document_id: str
    status: str
    progress: int | None = None
    message: str = "Ready"


class ChunkResponse(BaseModel):
    index: int
    text: str
    metadata: dict


class ChunkSearchRequest(BaseModel):
    query: str
    project_id: str | None = None
    top_k: int = 4
    include_archived: bool = False


class DocumentAccessGrantCreate(BaseModel):
    principal_type: str = Field(pattern="^(role|user)$")
    role_id: int | None = None
    user_id: str | None = Field(default=None, min_length=1)
    permission: str = Field(default="read", min_length=1, max_length=32)


class DocumentGrantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    internal_id: int
    document_id: str
    principal_type: str
    role_id: int | None
    user_id: str | None
    permission: str
    status: str
    granted_by_uid: str | None
    granted_at: datetime
