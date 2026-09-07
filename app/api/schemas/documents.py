from typing import Optional
from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    filename: str
    status: str
    message: str
    chunks_count: Optional[int] = None
    already_existed: Optional[bool] = None
    collection: Optional[str] = None
