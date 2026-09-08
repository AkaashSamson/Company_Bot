import os

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status

from app.api.dependencies.auth import Identity, get_current_user
from app.api.schemas.documents import DocumentUploadResponse
from app.core.settings import COLLECTION_NAME, UPLOADS_DIR
from app.db.documents_repository import DocumentsRepository
from app.db.roles_repository import RolesRepository
from app.db.users_repository import UsersRepository
from app.infrastructure.document.local_document_loader import SUPPORTED_EXTENSIONS
from app.use_cases.access.access_control_service import AccessControlService
from app.use_cases.access.auth_service import DocumentRegistrationService
from app.use_cases.ingestion.document_ingestion_service import DocumentIngestionService

router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _validate_upload(file: UploadFile) -> str:
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{extension}'. Supported: {supported}",
        )
    return extension


def _normalize_access_lists(
    allowed_role_codes: list[str] | None,
    allowed_user_ids: list[str] | None,
) -> tuple[list[str], list[str]]:
    roles_repo = RolesRepository()
    normalized_roles = []
    for code in allowed_role_codes or []:
        normalized = code.strip().lower()
        if not roles_repo.exists(normalized):
            raise HTTPException(
                status_code=400,
                detail=f"Unknown role '{code}'",
            )
        normalized_roles.append(normalized)

    users_repo = UsersRepository()
    normalized_users = []
    for employee_id in allowed_user_ids or []:
        employee_id = employee_id.strip()
        if users_repo.get_by_employee_id(employee_id) is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown employee '{employee_id}'",
            )
        normalized_users.append(employee_id)

    result = AccessControlService.normalize_allow_lists(
        normalized_roles,
        normalized_users,
    )
    return result["allowed_role_codes"], result["allowed_user_ids"]


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile,
    overwrite: bool = False,
    allowed_role_codes: list[str] = Form(default=[]),
    allowed_user_ids: list[str] = Form(default=[]),
    identity: Identity = Depends(get_current_user),
):
    if not identity.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file name provided")

    _validate_upload(file)

    can_role_codes, can_user_ids = _normalize_access_lists(
        allowed_role_codes,
        allowed_user_ids,
    )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the maximum allowed size",
        )

    async def _cleanup():
        try:
            await file.close()
        except Exception:
            pass

    upload_dir = UPLOADS_DIR
    os.makedirs(upload_dir, exist_ok=True)

    saved_name = file.filename
    saved_path = os.path.join(upload_dir, saved_name)

    probe = DocumentIngestionService()
    existing_chunks = probe.store.count_by_source(saved_name)
    if existing_chunks > 0 and not overwrite:
        await _cleanup()
        return DocumentUploadResponse(
            filename=saved_name,
            status="duplicate",
            message=(
                f"'{saved_name}' is already indexed in the collection. "
                "Duplicate upload skipped."
            ),
            chunks_count=existing_chunks,
            already_existed=True,
            collection=COLLECTION_NAME,
        )

    documents_repo = DocumentsRepository()
    existing_document = documents_repo.get_by_filename(saved_name)
    if existing_document is not None:
        # With overwrite the prior registration (and its chunks) is replaced.
        documents_repo.delete(existing_document.document_id)

    existing_conflict = os.path.exists(saved_path)

    try:
        with open(saved_path, "wb") as buffer:
            buffer.write(content)
    except Exception as exc:
        await _cleanup()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save the uploaded file: {exc}",
        )

    document_id = None
    try:
        registered = DocumentRegistrationService().register_document(
            filename=saved_name,
            owner_employee_id=identity.employee_id,
            allowed_role_codes=can_role_codes,
            allowed_user_ids=can_user_ids,
        )
        document_id = registered["document_id"]

        engine = DocumentIngestionService()
        result = engine.ingest(
            saved_path,
            source_name=saved_name,
            overwrite=overwrite,
            document_id=document_id,
        )
    except Exception as exc:
        if document_id:
            documents_repo.delete(document_id)
        await _cleanup()
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail=str(exc))
        if hasattr(exc, "status_code"):  # re-raise HTTPException unchanged
            raise
        raise HTTPException(
            status_code=500,
            detail=f"Document ingestion failed: {exc}",
        )

    await _cleanup()

    if existing_conflict:
        message = f"'{saved_name}' overwrote the existing file and was re-indexed."
    else:
        message = f"'{saved_name}' was processed and stored successfully."

    return DocumentUploadResponse(
        filename=saved_name,
        status=result.status,
        message=message,
        chunks_count=result.chunks_count,
        already_existed=result.already_existed,
        collection=COLLECTION_NAME,
        document_id=document_id,
        allowed_role_codes=can_role_codes,
        allowed_user_ids=can_user_ids,
    )