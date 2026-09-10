from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["organization"])


@router.get("/organization/status")
def organization_status():
    return {"status": "ready"}
