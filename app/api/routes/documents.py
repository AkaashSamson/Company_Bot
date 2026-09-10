from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import get_current_principal, get_document_management_service
from app.api.schemas.documents import DocumentCreate, DocumentResponse
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/documents/status")
def documents_status():
    return {"status": "ready"}


def _error(error):
    if isinstance(error, ConflictError):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, NotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, ForbiddenError):
        return HTTPException(status_code=403, detail=str(error))
    return HTTPException(status_code=400, detail=str(error))


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        return service.list_documents(principal)
    except Exception as error:
        raise _error(error) from error


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreate,
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        return service.register_document(principal, **payload.model_dump())
    except Exception as error:
        raise _error(error) from error


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        service.delete_document(principal, document_id)
    except Exception as error:
        raise _error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
