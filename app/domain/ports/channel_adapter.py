from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol, runtime_checkable
from starlette.requests import Request


@dataclass(frozen=True)
class ChannelUser:
    """Normalized sender metadata across all chat channels."""
    user_id: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    tenant_id: Optional[str] = None


@dataclass(frozen=True)
class ChannelMessage:
    """Normalized inbound message from any driving channel."""
    channel_name: str
    conversation_id: str
    text: str
    sender: ChannelUser
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    message_id: Optional[str] = None
    service_url: Optional[str] = None

    @property
    def session_id(self) -> str:
        """Standardized session key format: '{channel_name}:{conversation_id}'."""
        return f"{self.channel_name}:{self.conversation_id}"


@dataclass(frozen=True)
class ChannelResponse:
    """Normalized outbound response delivered back to the channel."""
    status_code: int = 200
    text: str = ""
    card_payload: Optional[Dict[str, Any]] = None
    headers: Dict[str, str] = field(default_factory=dict)


@runtime_checkable
class ChannelAdapterPort(Protocol):
    """Hexagonal driving port for external chat channels (Teams, Slack, etc.)."""
    @property
    def channel_name(self) -> str: ...

    async def parse_and_validate(self, request: Request) -> ChannelMessage: ...

    def format_response(self, message: ChannelMessage, result: Dict[str, Any]) -> ChannelResponse: ...

    async def handle_webhook(
        self,
        request: Request,
        chat_dispatcher: Callable[[ChannelMessage], Awaitable[Dict[str, Any]]],
    ) -> ChannelResponse: ...
