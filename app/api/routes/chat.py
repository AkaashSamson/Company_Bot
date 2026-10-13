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
    from app.core.settings import SEMANTIC_CACHE_ENABLED
    from app.infrastructure.cache import get_semantic_cache
    response_cache = get_semantic_cache() if SEMANTIC_CACHE_ENABLED else None
    _orchestrator = QueryOrchestrator(
        response_cache=response_cache,
    )
    try:
        reranker = getattr(getattr(_orchestrator, "retrieval", None), "reranker", None)
        if reranker is not None and hasattr(reranker, "model"):
            _ = reranker.model
    except Exception as exc:
        logger.warning("Could not pre-warm reranker: %s", exc)
    logger.info("QueryOrchestrator initialised with loosely-coupled semantic cache.")


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
    if "question_timestamp" in answer_sig.parameters:
        kwargs["question_timestamp"] = request.question_timestamp
    user_context = principal
    if principal is not None and authorization is not None:
        try:
            user_roles = authorization.roles_for_user(principal.uid)
            role_names = [getattr(r, "name", str(r)) for r in user_roles] if user_roles else []
            primary_role = role_names[0] if role_names else ("admin" if getattr(scope, "is_admin", False) else None)
            user_context = {
                "uid": principal.uid,
                "role": primary_role,
                "roles": role_names,
                "is_admin": getattr(scope, "is_admin", False),
                "principal": principal,
            }
        except Exception:
            user_context = principal
    if "user_context" in answer_sig.parameters:
        kwargs["user_context"] = user_context

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
        cache_id=result.get("cache_id"),
        assigned_role=result.get("assigned_role"),
        matched_faq=result.get("matched_faq"),
        similarity=result.get("similarity"),
        tokens=token_usage,
        is_latest=result.get("is_latest", True),
        corrections=result.get("corrections", []),
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


@router.post("/chat/cache/clear")
@router.post("/cache/clear")
async def clear_cache():
    """Clear in-memory response caches, LLM prompt caches, and session citations."""
    import app.api.routes.chat as this_module
    from app.use_cases.chat.query_orchestrator import _pending_citations

    active_orchestrator = getattr(this_module, "orchestrator", None) or _orchestrator
    cleared = []

    if active_orchestrator is not None:
        # 1. Clear response cache (QualityAwareCache / DualCache / PromptLRUCache)
        if hasattr(active_orchestrator, "response_cache") and active_orchestrator.response_cache:
            try:
                active_orchestrator.response_cache.clear()
                cleared.append("response_cache")
            except Exception as exc:
                logger.warning("Failed to clear response_cache: %s", exc)

        # 2. Clear LLM prompt cache
        if hasattr(active_orchestrator, "llm") and active_orchestrator.llm:
            llm = active_orchestrator.llm
            if hasattr(llm, "cache") and llm.cache and hasattr(llm.cache, "clear"):
                try:
                    llm.cache.clear()
                    cleared.append("llm_prompt_cache")
                except Exception as exc:
                    logger.warning("Failed to clear llm cache: %s", exc)

        # 3. Clear FAQ cache if applicable
        if hasattr(active_orchestrator, "faq_cache") and active_orchestrator.faq_cache and hasattr(active_orchestrator.faq_cache, "clear"):
            try:
                active_orchestrator.faq_cache.clear()
                cleared.append("faq_cache")
            except Exception as exc:
                logger.warning("Failed to clear faq cache: %s", exc)

    # 4. Clear module-level pending citations and interaction states
    _pending_citations.clear()
    cleared.append("pending_citations")
    try:
        from app.use_cases.chat.query_orchestrator import _last_interaction, _alternative_answer_given
        _last_interaction.clear()
        _alternative_answer_given.clear()
    except Exception:
        pass

    logger.info("Caches cleared successfully: %s", cleared)
    return {"status": "ok", "cleared": cleared}


@router.get("/providers/health")
@router.get("/chat/providers/health")
async def get_providers_health():
    """Return health metrics and circuit breaker status for all LLM providers (Task AB-1.2)."""
    from app.infrastructure.llm.provider_health import get_provider_health_monitor
    monitor = get_provider_health_monitor()
    all_metrics = monitor.get_all_metrics()
    result = {}
    for name, metrics in all_metrics.items():
        status = monitor.get_health_status(name)
        result[name] = {
            "status": status.value if status else "healthy",
            "available": monitor.is_provider_available(name),
            "total_requests": metrics.total_requests,
            "successful_requests": metrics.successful_requests,
            "failed_requests": metrics.failed_requests,
            "consecutive_failures": metrics.consecutive_failures,
            "consecutive_successes": metrics.consecutive_successes,
            "average_latency_ms": round(metrics.average_latency_ms, 2),
            "success_rate": round(metrics.success_rate, 1),
            "last_success_time": metrics.last_success_time,
            "last_failure_time": metrics.last_failure_time,
        }
    return result


@router.post("/providers/reset")
@router.post("/chat/providers/reset")
async def reset_providers():
    """Reset circuit breakers for all LLM providers."""
    from app.infrastructure.llm.provider_health import get_provider_health_monitor
    monitor = get_provider_health_monitor()
    monitor.reset_all()
    return {"status": "ok", "message": "All provider circuit breakers reset to healthy."}


