from datetime import datetime, timezone
from typing import List
from pydantic import BaseModel, Field


class ConversationMessage(BaseModel):
    """
    A single message within a conversation log.
    """

    role: str = Field(..., description="The chat role, such as user or assistant")
    content: str = Field(..., description="Message content")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC timestamp for the message in ISO 8601 format",
    )


class ConversationLog(BaseModel):
    """
    One JSON document representing one completed conversation.
    """

    employee_id: str = Field(
        ...,
        description="Employee ID representing the employee associated with the authenticated user",
    )
    session_id: str = Field(
        ...,
        description="Existing application session identifier",
    )
    messages: List[ConversationMessage] = Field(
        ...,
        description="Ordered message records for the completed conversation",
    )
    recording_status: str = Field(
        default="completed",
        description="Recording status, completed for a successfully recorded conversation",
    )
