from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status

from app.api.dependencies import (
    get_current_principal,
    get_document_access_service,
    get_document_management_service,
)
from app.api.schemas.documents import (
    DocumentAccessGrantCreate,
    DocumentCreate,
    DocumentGrantResponse,
    DocumentResponse,
)
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


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        return service.get_document(principal, document_id)
    except Exception as error:
        raise _error(error) from error


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreate,
    background_tasks: BackgroundTasks,
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        data = payload.model_dump()
        use_async = data.pop("async_mode", False)
        return service.register_document(
            principal,
            background_tasks=background_tasks if use_async else None,
            **data,
        )
    except Exception as error:
        raise _error(error) from error


@router.get("/projects/{project_id}/documents", response_model=list[DocumentResponse])
def list_project_documents(
    project_id: str,
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        return service.list_project_documents(principal, project_id)
    except Exception as error:
        raise _error(error) from error


@router.post("/projects/{project_id}/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_project_document(
    project_id: str,
    payload: DocumentCreate,
    background_tasks: BackgroundTasks,
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        data = payload.model_dump(exclude={"project_id"})
        use_async = data.pop("async_mode", False)
        return service.register_document(
            principal,
            project_id=project_id,
            background_tasks=background_tasks if use_async else None,
            **data,
        )
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


@router.get("/documents/{document_id}/access", response_model=list[DocumentGrantResponse])
def list_document_access(
    document_id: str,
    principal=Depends(get_current_principal),
    service=Depends(get_document_access_service),
):
    try:
        return service.list(principal, document_id)
    except Exception as error:
        raise _error(error) from error


@router.post("/documents/{document_id}/access", response_model=DocumentGrantResponse, status_code=status.HTTP_201_CREATED)
def grant_document_access(
    document_id: str,
    payload: DocumentAccessGrantCreate,
    principal=Depends(get_current_principal),
    service=Depends(get_document_access_service),
):
    try:
        return service.grant(principal, document_id, **payload.model_dump())
    except Exception as error:
        raise _error(error) from error


@router.delete("/document-access/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_document_access(
    grant_id: int,
    principal=Depends(get_current_principal),
    service=Depends(get_document_access_service),
):
    try:
        service.revoke(principal, grant_id)
    except Exception as error:
        raise _error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
