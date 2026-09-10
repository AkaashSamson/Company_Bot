from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/documents/status")
def documents_status():
    return {"status": "ready"}
