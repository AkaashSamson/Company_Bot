from fastapi import APIRouter

from app.api.schemas.chat import ChatRequest, ChatResponse, Citation
from app.use_cases.chat.query_orchestrator import QueryOrchestrator

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    orchestrator = QueryOrchestrator()
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

    return ChatResponse(
        session_id=request.session_id,
        answer=result["answer"],
        citations=citations,
    )
