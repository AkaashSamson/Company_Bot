from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    document_id: str = Field(min_length=1)
    document_name: str = Field(min_length=1)
    project_id: str | None = None
    source_path: str | None = None
    content: str | None = None


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: str
    document_name: str
    project_id: str | None
    status: str
