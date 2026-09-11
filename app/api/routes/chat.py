from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_authorization_service, get_chat_principal
from app.api.schemas.chat import ChatRequest, ChatResponse, Citation
from app.use_cases.chat.query_orchestrator import QueryOrchestrator

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    principal=Depends(get_chat_principal),
    authorization=Depends(get_authorization_service),
):
    authorized_project_ids = None
    if principal is not None:
        if authorization.is_admin(principal):
            authorized_project_ids = (
                [request.project_id]
                if request.project_id
                else None
            )
        else:
            authorized_project_ids = authorization.authorized_project_ids(
                principal,
                request.project_id,
            )
            if request.project_id and not authorized_project_ids:
                raise HTTPException(status_code=403, detail="Access denied")
    orchestrator = QueryOrchestrator()
    result = orchestrator.answer(
        request.question,
        conversation_history=[message.model_dump() for message in (request.conversation_history or [])],
        authorized_project_ids=authorized_project_ids,
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
