from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status

from app.api.dependencies import (
    get_current_principal,
    get_document_access_service,
    get_document_management_service,
    get_vector_store,
)
from app.api.schemas.documents import (
    ChunkResponse,
    ChunkSearchRequest,
    DocumentAccessGrantCreate,
    DocumentCreate,
    DocumentGrantResponse,
    DocumentResponse,
    DocumentStatusResponse,
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
    include_archived: bool = Query(False),
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        return service.list_documents(principal, include_archived=include_archived)
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


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
def create_document(
    payload: DocumentCreate,
    background_tasks: BackgroundTasks,
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        data = payload.model_dump()
        use_async = data.pop("async_mode", True)
        doc = service.register_document(
            principal,
            defer_ingestion=use_async,
            background_tasks=background_tasks if use_async else None,
            **data,
        )
        if use_async and (payload.content or payload.source_path) and hasattr(service, "ingest_document"):
            background_tasks.add_task(
                service.ingest_document,
                doc.document_id,
                payload.source_path,
                payload.content,
            )
        return doc
    except Exception as error:
        raise _error(error) from error


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
def get_document_status(
    document_id: str,
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        return service.get_document_status(principal, document_id)
    except Exception as error:
        raise _error(error) from error


@router.get("/documents/{document_id}/chunks")
def get_document_chunks(
    document_id: str,
    principal=Depends(get_current_principal),
    vector_store=Depends(get_vector_store),
):
    try:
        results = vector_store.collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
        )
        chunks = []
        docs = results.get("documents") or []
        metas = results.get("metadatas") or []
        for idx, (doc_text, meta) in enumerate(zip(docs, metas)):
            chunks.append({"index": idx, "text": doc_text, "metadata": meta})
        return chunks
    except Exception as error:
        raise _error(error) from error


@router.post("/documents/chunks/search")
def search_chunks(
    payload: ChunkSearchRequest,
    principal=Depends(get_current_principal),
    vector_store=Depends(get_vector_store),
):
    try:
        where = {}
        if payload.project_id:
            where["project_id"] = payload.project_id
        if not payload.include_archived:
            where["status"] = "active"
        return vector_store.query(
            payload.query,
            top_k=payload.top_k,
            where=where or None,
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


@router.post("/projects/{project_id}/documents", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
def create_project_document(
    project_id: str,
    payload: DocumentCreate,
    background_tasks: BackgroundTasks,
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        data = payload.model_dump(exclude={"project_id"})
        use_async = data.pop("async_mode", True)
        doc = service.register_document(
            principal,
            project_id=project_id,
            defer_ingestion=use_async,
            background_tasks=background_tasks if use_async else None,
            **data,
        )
        if use_async and (payload.content or payload.source_path) and hasattr(service, "ingest_document"):
            background_tasks.add_task(
                service.ingest_document,
                doc.document_id,
                payload.source_path,
                payload.content,
            )
        return doc
    except Exception as error:
        raise _error(error) from error


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    permanent: bool = Query(False),
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        service.delete_document(principal, document_id, permanent=permanent)
    except Exception as error:
        raise _error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/{document_id}/restore", response_model=DocumentResponse)
def restore_document(
    document_id: str,
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        return service.restore_document(principal, document_id)
    except Exception as error:
        raise _error(error) from error


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
