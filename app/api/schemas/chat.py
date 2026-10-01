from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)
    timestamp: Optional[str] = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    question_timestamp: Optional[str] = None
    session_id: str = Field(default="default-session")
    project_id: Optional[str] = None
    conversation_history: Optional[List[ChatMessage]] = None
    defer_citations: Optional[bool] = None


class Citation(BaseModel):
    source: str
    section: str
    text: str


class TokenUsageInfo(BaseModel):
    """Token usage statistics for an LLM call."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_hit: bool = False


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: List[Citation] = []
    cache_hit: bool = False
    cache_id: Optional[str] = None
    assigned_role: Optional[str] = None
    matched_faq: Optional[str] = None
    similarity: Optional[float] = None
    tokens: Optional[TokenUsageInfo] = None
    is_latest: bool = Field(default=True, description="Indicates if the response is based on the latest version of the documents")
    corrections: List[str] = Field(default_factory=list, description="Spelling or typo corrections applied to the query")


class FAQResponse(BaseModel):
    faqs: str
    citations: List[Citation] = []
