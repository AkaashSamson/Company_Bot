import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.api.schemas.chat import ChatRequest, ChatResponse, Citation, TokenUsageInfo, FAQResponse
from app.domain.services.llm_provider import LLMProviderError
from app.use_cases.chat.query_orchestrator import QueryOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

_orchestrator: QueryOrchestrator | None = None


def init_orchestrator() -> None:
    global _orchestrator
    _orchestrator = QueryOrchestrator()
    logger.info("QueryOrchestrator initialised and ready.")


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Service not ready yet.")

    logger.info(
        "chat_call session_id=%s history_messages=%d question=%s",
        request.session_id,
        len(request.conversation_history or []),
        request.question[:50],  # Log first 50 chars of question
    )

    history = [m.model_dump() for m in (request.conversation_history or [])]

    try:
        result = await asyncio.to_thread(
            _orchestrator.answer,
            request.question,
            history,
            request.session_id,
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
        Citation(source=item["source"], section=item["section"], text=item["text"])
        for item in result.get("citations", [])
    ]

    # Extract token usage from result
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
        answer=result["answer"],
        citations=citations,
        cache_hit=result.get("cache_hit", False),
        matched_faq=result.get("matched_faq"),
        similarity=result.get("similarity"),
        tokens=token_usage,
    )


@router.get("/faqs", response_model=FAQResponse)
async def faqs():
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Service not ready yet.")
    
    logger.info("faq_generation_call")
    result = _orchestrator.generate_faqs()
    citations = [
        Citation(
            source=item["source"],
            section=item["section"],
            text=item["text"],
        )
        for item in result.get("citations", [])
    ]
    logger.info("faq_generation_complete citations=%d", len(citations))
    return FAQResponse(faqs=result["faqs"], citations=citations)
