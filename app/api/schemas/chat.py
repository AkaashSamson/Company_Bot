from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: str = Field(default="default-session")
    conversation_history: Optional[List[ChatMessage]] = None


class Citation(BaseModel):
    source: str
    section: str
    text: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: List[Citation] = []
