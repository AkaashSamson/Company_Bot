import base64
import hashlib
import hmac
import logging
import re
from typing import Any, Dict, Optional
from starlette.requests import Request

from app.domain.ports.channel_adapter import (
    ChannelMessage,
    ChannelResponse,
    ChannelUser,
)
from app.infrastructure.channels.base import (
    BaseChannelAdapter,
    ChannelAuthenticationError,
    ChannelValidationError,
)
from app.infrastructure.channels.teams.formatter import (
    format_teams_adaptive_card,
    format_teams_text,
)

logger = logging.getLogger(__name__)

# Pattern to strip <at>BotName</at> mention tags from incoming Teams text
_AT_MENTION_PATTERN = re.compile(r"<at>.*?</at>", re.IGNORECASE)


class TeamsChannelAdapter(BaseChannelAdapter):
    """Production Teams Adapter supporting Outgoing Webhooks and Bot Framework Activity schema."""

    def __init__(
        self,
        security_token: Optional[str] = None,
        skip_auth: bool = False,
    ):
        self._security_token = security_token
        self._skip_auth = skip_auth

    @property
    def channel_name(self) -> str:
        return "teams"

    def _verify_hmac_signature(self, body_bytes: bytes, auth_header: Optional[str]) -> bool:
        if not self._security_token:
            return True
        if not auth_header:
            return False

        parts = auth_header.split(" ", 1)
        token_to_verify = parts[1].strip() if len(parts) == 2 else parts[0].strip()

        key = self._security_token.encode("utf-8")
        expected_digest = hmac.new(key, body_bytes, hashlib.sha256).digest()
        expected_token = base64.b64encode(expected_digest).decode("utf-8")

        return hmac.compare_digest(token_to_verify, expected_token)

    async def parse_and_validate(self, request: Request) -> ChannelMessage:
        body_bytes = await request.body()
        if not body_bytes:
            raise ChannelValidationError("Empty request body")

        if not self._skip_auth and self._security_token:
            auth_header = request.headers.get("authorization")
            if not self._verify_hmac_signature(body_bytes, auth_header):
                raise ChannelAuthenticationError("Invalid HMAC signature")

        try:
            import json
            payload: Dict[str, Any] = json.loads(body_bytes.decode("utf-8"))
        except Exception as exc:
            raise ChannelValidationError(f"Invalid JSON payload: {exc}") from exc

        # Teams activity validation
        raw_text = payload.get("text") or ""
        clean_text = _AT_MENTION_PATTERN.sub("", raw_text).strip()
        if not clean_text:
            raise ChannelValidationError("Message text is empty after mention removal")

        conversation = payload.get("conversation") or {}
        conversation_id = conversation.get("id") or payload.get("id") or "default_thread"

        sender_info = payload.get("from") or {}
        user_id = sender_info.get("id") or "unknown_user"
        email = (
            sender_info.get("userPrincipalName")
            or sender_info.get("email")
            or sender_info.get("aadObjectId")
        )
        display_name = sender_info.get("name")

        user = ChannelUser(
            user_id=user_id,
            email=email,
            display_name=display_name,
            tenant_id=payload.get("channelData", {}).get("tenant", {}).get("id"),
        )

        return ChannelMessage(
            channel_name=self.channel_name,
            conversation_id=conversation_id,
            text=clean_text,
            sender=user,
            raw_payload=payload,
            message_id=payload.get("id"),
            service_url=payload.get("serviceUrl"),
        )

    def format_response(self, message: ChannelMessage, result: Dict[str, Any]) -> ChannelResponse:
        plain_text = format_teams_text(result)
        adaptive_card = format_teams_adaptive_card(result)

        activity_payload = {
            "type": "message",
            "text": plain_text,
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": adaptive_card,
                }
            ],
        }

        response_payload = {
            **activity_payload,
            "activities": [activity_payload],
        }

        return ChannelResponse(
            status_code=200,
            text=plain_text,
            card_payload=response_payload,
        )
