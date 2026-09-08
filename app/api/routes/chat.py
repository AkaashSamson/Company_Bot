from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies.auth import Identity, get_current_user
from app.api.schemas.chat import ChatRequest, ChatResponse, Citation
from app.use_cases.chat.query_orchestrator import QueryOrchestrator

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    identity: Identity = Depends(get_current_user),
):
    if not identity.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    orchestrator = QueryOrchestrator()
    result = orchestrator.answer(
        request.question,
        conversation_history=[message.model_dump() for message in (request.conversation_history or [])],
        employee_id=identity.employee_id,
        role_code=identity.role_code,
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