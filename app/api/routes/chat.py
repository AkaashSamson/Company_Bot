import asyncio
import inspect
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_authorization_service, get_chat_principal
from app.api.schemas.chat import (
    ChatRequest,
    ChatResponse,
    Citation,
    FAQResponse,
    TokenUsageInfo,
)
from app.domain.services.authorization_engine import AuthorizationScope
from app.domain.services.llm_provider import LLMProviderError
from app.use_cases.chat.query_orchestrator import QueryOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

_DefaultQueryOrchestrator = QueryOrchestrator
_orchestrator: QueryOrchestrator | None = None
orchestrator: QueryOrchestrator | None = None


def init_orchestrator() -> None:
    global _orchestrator
    _orchestrator = QueryOrchestrator()
    logger.info("QueryOrchestrator initialised and ready.")


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    principal=Depends(get_chat_principal),
    authorization=Depends(get_authorization_service),
):
    if principal is not None:
        scope = authorization.authorization_scope(principal, request.project_id)
        if request.project_id is not None and scope.project_ids == [] and not scope.document_ids:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        scope = AuthorizationScope(is_admin=False, project_ids=[], document_ids=None, include_unassigned=True)

    logger.info(
        "chat_call session_id=%s history_messages=%d question=%s",
        request.session_id,
        len(request.conversation_history or []),
        request.question[:50],
    )

    import app.api.routes.chat as this_module
    module_orchestrator = getattr(this_module, "orchestrator", None)

    if module_orchestrator is not None:
        active_orchestrator = module_orchestrator
    elif this_module.QueryOrchestrator is not _DefaultQueryOrchestrator:
        active_orchestrator = this_module.QueryOrchestrator(
            project_contact_lookup=getattr(authorization, "project_access_contact", None) if authorization else None,
        )
    else:
        global _orchestrator
        if _orchestrator is None:
            init_orchestrator()
        active_orchestrator = _orchestrator
        if authorization and hasattr(authorization, "project_access_contact"):
            active_orchestrator.project_contact_lookup = authorization.project_access_contact

    history = [m.model_dump() for m in (request.conversation_history or [])]

    answer_sig = inspect.signature(active_orchestrator.answer)
    kwargs = {}
    if "conversation_history" in answer_sig.parameters:
        kwargs["conversation_history"] = history
    if "authorization_scope" in answer_sig.parameters:
        kwargs["authorization_scope"] = scope
    if "session_id" in answer_sig.parameters:
        kwargs["session_id"] = request.session_id
    if "defer_citations" in answer_sig.parameters:
        kwargs["defer_citations"] = request.defer_citations if request.defer_citations is not None else False
    if "user_context" in answer_sig.parameters:
        kwargs["user_context"] = principal

    try:
        result = await asyncio.to_thread(
            active_orchestrator.answer,
            request.question,
            **kwargs,
        )
    except LLMProviderError as exc:
        logger.warning("LLM provider error: %s", exc)
        result = {
            "answer": (
                "I'm having trouble reaching the AI provider right now. "
                "Please try again in a moment."
            ),
            "citations": [],
            "cache_hit": False,
            "tokens": None,
        }

    citations = [
        Citation(
            source=item.get("source", "Policy"),
            section=item.get("section", "Policy"),
            text=item.get("text", ""),
        )
        for item in result.get("citations", [])
    ]

    token_usage = None
    if result.get("tokens"):
        tokens_data = result["tokens"]
        token_usage = TokenUsageInfo(
            prompt_tokens=tokens_data.get("prompt_tokens", 0),
            completion_tokens=tokens_data.get("completion_tokens", 0),
            total_tokens=tokens_data.get("total_tokens", 0),
            cache_hit=tokens_data.get("cache_hit", False),
        )
        logger.info(
            "Token usage in response: prompt=%d, completion=%d, total=%d, cache_hit=%s",
            token_usage.prompt_tokens,
            token_usage.completion_tokens,
            token_usage.total_tokens,
            token_usage.cache_hit,
        )

    logger.info(
        "chat_complete session_id=%s citations=%d",
        request.session_id,
        len(citations),
    )

    return ChatResponse(
        session_id=request.session_id,
        answer=result.get("answer", ""),
        citations=citations,
        cache_hit=result.get("cache_hit", False),
        matched_faq=result.get("matched_faq"),
        similarity=result.get("similarity"),
        tokens=token_usage,
    )


@router.get("/faqs", response_model=FAQResponse)
async def faqs():
    import app.api.routes.chat as this_module
    active_orchestrator = getattr(this_module, "orchestrator", None) or _orchestrator
    if active_orchestrator is None:
        init_orchestrator()
        active_orchestrator = _orchestrator

    logger.info("faq_generation_call")
    result = active_orchestrator.generate_faqs()
    citations = [
        Citation(
            source=item.get("source", "Policy"),
            section=item.get("section", "Policy"),
            text=item.get("text", ""),
        )
        for item in result.get("citations", [])
    ]
    logger.info("faq_generation_complete citations=%d", len(citations))
    return FAQResponse(faqs=result.get("faqs", ""), citations=citations)
