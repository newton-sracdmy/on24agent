"""FastAPI router endpoints for Integrations & Connected Applications."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import APIResponse
from app.constants import MembershipRole
from app.dependencies import AuthenticatedUserContext, get_db, require_role, require_tenant
from app.domains.integrations.schemas import (
    ConnectIntegrationRequest,
    ConnectIntegrationResponse,
    IntegrationListResponse,
    RequestIntegrationSubmission,
)
from app.domains.integrations.service import IntegrationsService

router = APIRouter()

# Connecting or disconnecting replaces workspace-wide credentials, so it is limited to admins (owners always pass)
require_integration_admin = require_role([MembershipRole.ADMIN])


@router.get("/", response_model=APIResponse[IntegrationListResponse])
async def list_integrations(
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[IntegrationListResponse]:
    """List all available integrations, category counters, and tenant connection status."""
    res = await IntegrationsService.list_integrations(db, user_context.organization_id)
    return APIResponse.ok(data=res)


@router.post("/connect", response_model=APIResponse[ConnectIntegrationResponse])
async def connect_integration(
    payload: ConnectIntegrationRequest,
    user_context: AuthenticatedUserContext = Depends(require_integration_admin),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[ConnectIntegrationResponse]:
    """Securely connect and encrypt credentials for a channel or SaaS integration."""
    try:
        res = await IntegrationsService.connect_integration(
            db, user_context.organization_id, payload
        )
        return APIResponse.ok(data=res)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{app_slug}/disconnect", response_model=APIResponse[dict])
async def disconnect_integration(
    app_slug: str,
    user_context: AuthenticatedUserContext = Depends(require_integration_admin),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[dict]:
    """Disconnect an active channel or SaaS integration."""
    try:
        await IntegrationsService.disconnect_integration(
            db, user_context.organization_id, app_slug
        )
        return APIResponse.ok(data={"success": True, "app_slug": app_slug, "status": "disconnected"})
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/request", response_model=APIResponse[dict])
async def request_integration(
    payload: RequestIntegrationSubmission,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
) -> APIResponse[dict]:
    """Submit a request for a new external integration."""
    return APIResponse.ok(data={
        "success": True,
        "message": f"Thank you! Request for '{payload.name}' under {payload.category} has been received.",
        "request": payload.model_dump()
    })
