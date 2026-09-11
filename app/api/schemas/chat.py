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
    matched_faq: Optional[str] = None
    similarity: Optional[float] = None
    tokens: Optional[TokenUsageInfo] = None


class FAQResponse(BaseModel):
    faqs: str
    citations: List[Citation] = []
