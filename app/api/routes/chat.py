from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_authorization_service, get_chat_principal
from app.api.schemas.chat import ChatRequest, ChatResponse, Citation
from app.domain.services.authorization_engine import AuthorizationScope
from app.use_cases.chat.query_orchestrator import QueryOrchestrator

router = APIRouter(prefix="/api", tags=["chat"])


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
        scope = AuthorizationScope(is_admin=False, project_ids=[], document_ids=None, include_unassigned=False)
    orchestrator = QueryOrchestrator(
        project_contact_lookup=getattr(authorization, "project_access_contact", None),
    )
    result = orchestrator.answer(
        request.question,
        conversation_history=[message.model_dump() for message in (request.conversation_history or [])],
        authorization_scope=scope,
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
