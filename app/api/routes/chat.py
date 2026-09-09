import logging

from fastapi import APIRouter

from app.api.schemas.chat import ChatRequest, ChatResponse, Citation, FAQResponse
from app.use_cases.chat.query_orchestrator import QueryOrchestrator

router = APIRouter(prefix="/api", tags=["chat"])
orchestrator = QueryOrchestrator()
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    logger.info(
        "chat_call session_id=%s history_messages=%d",
        request.session_id,
        len(request.conversation_history or []),
    )
    result = orchestrator.answer(
        request.question,
        conversation_history=[message.model_dump() for message in (request.conversation_history or [])],
    )

    citations = [
        Citation(
            source=item["source"],
            section=item["section"],
            text=item["text"],
        )
        for item in result.get("citations", [])
    ]

    logger.info(
        "chat_complete session_id=%s citations=%d",
        request.session_id,
        len(citations),
    )

    return ChatResponse(
        session_id=request.session_id,
        answer=result["answer"],
        citations=citations,
    )


@router.get("/faqs", response_model=FAQResponse)
async def faqs():
    logger.info("faq_generation_call")
    result = orchestrator.generate_faqs()
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
