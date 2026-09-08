from typing import List, Optional

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    filename: str
    status: str
    message: str
    chunks_count: Optional[int] = None
    already_existed: Optional[bool] = None
    collection: Optional[str] = None
    document_id: Optional[str] = None
    allowed_role_codes: Optional[List[str]] = None
    allowed_user_ids: Optional[List[str]] = None