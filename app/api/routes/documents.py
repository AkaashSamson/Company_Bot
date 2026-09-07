import os

from fastapi import APIRouter, HTTPException, UploadFile, status

from app.api.schemas.documents import DocumentUploadResponse
from app.core.settings import COLLECTION_NAME, UPLOADS_DIR
from app.infrastructure.document.local_document_loader import SUPPORTED_EXTENSIONS
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


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile,
    overwrite: bool = False,
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file name provided")

    _validate_upload(file)

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

    try:
        engine = DocumentIngestionService()
        result = engine.ingest(
            saved_path,
            source_name=saved_name,
            overwrite=overwrite,
        )
    except ValueError as exc:
        await _cleanup()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        await _cleanup()
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
    )
