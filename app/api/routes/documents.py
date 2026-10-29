import hashlib
import os
import re
from pathlib import Path
# pyrefly: ignore[missing-import]
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status

from app.api.dependencies import (
    get_current_principal,
    get_current_user,
    get_document_access_service,
    get_document_ingestion_use_case,
    get_document_management_service,
)
from app.api.schemas.documents import (
    DocumentAccessGrantCreate,
    DocumentCreate,
    DocumentGrantResponse,
    DocumentResponse,
)
from app.domain.entities.organization_models import Employee
from app.domain.services.organization_errors import ConflictError, ForbiddenError, NotFoundError
from app.infrastructure.document.processor_factory import get_document_processor
from app.use_cases.ingestion.document_processing import DocumentIngestionUseCase

router = APIRouter(prefix="/api", tags=["documents"])


def _sanitize_filename(raw_filename: str) -> str:
    """EC-04: Prevent path traversal (../../etc/passwd.pdf) and multi-extension artifacts."""
    base_name = os.path.basename(raw_filename or "uploaded_document.txt")
    sanitized = re.sub(r"[^\w\-.]", "_", base_name).strip("._")
    return sanitized or "uploaded_document.txt"


def _build_collision_safe_doc_id(safe_filename: str, content_bytes: bytes) -> str:
    """
    EC-01: Prevent prefix collision between `handbook_2025.pdf` and `handbook_2026.pdf`.
    Combines sanitized stem with a 6-char SHA-256 content + filename digest.
    """
    stem = re.sub(r"[^\w]", "", Path(safe_filename).stem).upper()[:6] or "DOC"
    hasher = hashlib.sha256()
    hasher.update(safe_filename.encode("utf-8"))
    hasher.update(content_bytes)
    digest = hasher.hexdigest()[:6].upper()
    return f"DOC-{stem}-{digest}"


def _error(error):
    if isinstance(error, ConflictError):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, NotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, ForbiddenError):
        return HTTPException(status_code=403, detail=str(error))
    return HTTPException(status_code=400, detail=str(error))


@router.post("/documents/upload")
@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    current_user: Employee = Depends(get_current_user),
    ingestion_service: DocumentIngestionUseCase = Depends(get_document_ingestion_use_case),
):
    # Verify RBAC permission for project upload
    if not current_user.can_upload_to_project(project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have upload access to this project.",
        )

    safe_filename = _sanitize_filename(file.filename or "")

    # EC-02 & EC-03: Reset spool cursor, validate non-empty payload, and reset cursor for processor
    await file.seek(0)
    raw_bytes = await file.read()
    if not raw_bytes or len(raw_bytes.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes).",
        )
    await file.seek(0)

    # EC-03: Catch corrupted/encrypted binary parsing failures cleanly into HTTP 400
    try:
        processor = get_document_processor(safe_filename)
        raw_fragments = await processor.process(file)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse document '{safe_filename}': {exc}",
        ) from exc

    if not raw_fragments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No readable text or tables extracted from '{safe_filename}'.",
        )

    doc_reference = _build_collision_safe_doc_id(safe_filename, raw_bytes)
    created_chunks = ingestion_service.process_and_index_document(
        raw_chunks=raw_fragments,
        source_filename=safe_filename,
        document_id=doc_reference,
        project_id=project_id,
    )

    return {
        "status": "success",
        "document_id": doc_reference,
        "filename": safe_filename,
        "total_chunks_indexed": len(created_chunks),
    }


@router.get("/documents/status")
def documents_status():
    return {"status": "ready"}


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
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        return service.register_document(principal, project_id=project_id, **payload.model_dump(exclude={"project_id"}))
    except Exception as error:
        raise _error(error) from error


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    permanent: bool = Query(default=False, description="Set to true to permanently delete document and chunks"),
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        service.delete_document(principal, document_id, permanent=permanent)
        # Invalidate any cached answers that reference the deleted document
        try:
            from app.infrastructure.cache.factory import get_semantic_cache
            cache = get_semantic_cache()
            if cache and hasattr(cache, "invalidate_document"):
                cache.invalidate_document(document_id)
        except Exception:
            pass
    except Exception as error:
        raise _error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/{document_id}/archive", response_model=DocumentResponse, status_code=status.HTTP_200_OK)
def archive_document(
    document_id: str,
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        doc = service.archive_document(principal, document_id)
        try:
            from app.infrastructure.cache.factory import get_semantic_cache
            cache = get_semantic_cache()
            if cache and hasattr(cache, "invalidate_document"):
                cache.invalidate_document(document_id)
        except Exception:
            pass
        return doc
    except Exception as error:
        raise _error(error) from error


@router.post("/documents/{document_id}/unarchive", response_model=DocumentResponse, status_code=status.HTTP_200_OK)
def unarchive_document(
    document_id: str,
    principal=Depends(get_current_principal),
    service=Depends(get_document_management_service),
):
    try:
        doc = service.unarchive_document(principal, document_id)
        try:
            from app.infrastructure.cache.factory import get_semantic_cache
            cache = get_semantic_cache()
            if cache and hasattr(cache, "invalidate_document"):
                cache.invalidate_document(document_id)
        except Exception:
            pass
        return doc
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