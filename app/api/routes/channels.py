import logging
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.domain.ports.channel_adapter import ChannelMessage
from app.infrastructure.channels.identity_bridge import ChannelIdentityBridge
from app.infrastructure.channels.registry import get_channel_adapter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/channels", tags=["channels"])

_identity_bridge = ChannelIdentityBridge()


def _get_orchestrator():
    from app.api.routes.chat import _orchestrator, init_orchestrator
    if _orchestrator is None:
        init_orchestrator()
    from app.api.routes.chat import _orchestrator as active_orc
    return active_orc


@router.post("/{channel_name}/messages")
async def channel_webhook(channel_name: str, request: Request) -> Response:
    adapter = get_channel_adapter(channel_name)
    if adapter is None:
        raise HTTPException(
            status_code=404,
            detail=f"Channel '{channel_name}' is not supported or not enabled.",
        )

    async def chat_dispatcher(message: ChannelMessage) -> Dict[str, Any]:
        orchestrator = _get_orchestrator()
        principal = _identity_bridge.resolve_principal(message.sender)

        # Build authorization scope if authorization engine available
        from app.domain.services.authorization_engine import AuthorizationScope
        scope = AuthorizationScope(is_admin=False, project_ids=[], document_ids=None, include_unassigned=True)
        try:
            from app.api.dependencies import get_authorization_service
            authz_service = get_authorization_service()
            if authz_service:
                scope = authz_service.authorization_scope(principal)
        except Exception as exc:
            logger.debug("Failed to calculate channel scope: %s", exc)

        return orchestrator.answer(
            question=message.text,
            session_id=message.session_id,
            authorization_scope=scope,
            user_context=principal,
        )

    result = await adapter.handle_webhook(request, chat_dispatcher)

    content = result.card_payload if result.card_payload is not None else {"text": result.text}
    return JSONResponse(status_code=result.status_code, content=content, headers=result.headers)
