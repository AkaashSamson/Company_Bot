from abc import ABC, abstractmethod
import logging
from typing import Any, Awaitable, Callable, Dict
from starlette.requests import Request

from app.domain.ports.channel_adapter import (
    ChannelAdapterPort,
    ChannelMessage,
    ChannelResponse,
)

logger = logging.getLogger(__name__)


class ChannelAuthenticationError(Exception):
    """Raised when channel message HMAC or JWT token validation fails."""
    pass


class ChannelValidationError(Exception):
    """Raised when inbound channel payload is malformed or empty."""
    pass


class BaseChannelAdapter(ChannelAdapterPort, ABC):
    """Abstract Base Class providing the Template Method pattern for webhook handling."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Name of the driving channel, e.g. 'teams' or 'slack'."""
        pass

    @abstractmethod
    async def parse_and_validate(self, request: Request) -> ChannelMessage:
        """Parse raw request into normalized ChannelMessage, validating signatures/tokens."""
        pass

    @abstractmethod
    def format_response(self, message: ChannelMessage, result: Dict[str, Any]) -> ChannelResponse:
        """Format domain orchestrator result into channel-specific payload."""
        pass

    async def handle_webhook(
        self,
        request: Request,
        chat_dispatcher: Callable[[ChannelMessage], Awaitable[Dict[str, Any]]],
    ) -> ChannelResponse:
        """Template Method: orchestrates validation, query execution, and response formatting."""
        try:
            message = await self.parse_and_validate(request)
        except ChannelAuthenticationError as exc:
            logger.warning("Channel [%s] auth failed: %s", self.channel_name, exc)
            return ChannelResponse(status_code=401, text=str(exc))
        except ChannelValidationError as exc:
            logger.warning("Channel [%s] validation failed: %s", self.channel_name, exc)
            return ChannelResponse(status_code=400, text=str(exc))
        except Exception as exc:
            logger.error("Channel [%s] payload parse exception: %s", self.channel_name, exc, exc_info=True)
            return ChannelResponse(status_code=400, text="Invalid channel payload")

        try:
            result = await chat_dispatcher(message)
            return self.format_response(message, result)
        except Exception as exc:
            logger.error("Channel [%s] dispatcher failed: %s", self.channel_name, exc, exc_info=True)
            return ChannelResponse(
                status_code=500,
                text="An error occurred while processing your request.",
            )
