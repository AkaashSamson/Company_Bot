from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_current_principal, get_organization_explorer_service
from app.api.schemas.explorer import OrganizationExplorerResponse
from app.domain.services.organization_errors import ForbiddenError

router = APIRouter(prefix="/api", tags=["explorer"])


@router.get("/explorer/organization", response_model=OrganizationExplorerResponse)
def get_organization_explorer(
    principal=Depends(get_current_principal),
    service=Depends(get_organization_explorer_service),
):
    try:
        return service.get_organization(principal)
    except ForbiddenError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error