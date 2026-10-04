"""FastAPI router endpoints for WhatsApp Templates and Broadcast Campaigns."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import APIResponse
from app.dependencies import AuthenticatedUserContext, get_db, require_tenant
from app.domains.campaigns.models import Campaign, CampaignSegment, MessageTemplate
from app.domains.campaigns.schemas import (
    CampaignCreate,
    CampaignResponse,
    CampaignSegmentCreate,
    CampaignSegmentResponse,
    MessageTemplateCreate,
    MessageTemplateResponse,
)
from app.domains.campaigns.service import CampaignService

router = APIRouter()


@router.post("/templates", status_code=status.HTTP_201_CREATED, response_model=APIResponse[MessageTemplateResponse])
async def create_template(
    payload: MessageTemplateCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[MessageTemplateResponse]:
    """Create a WhatsApp Cloud API HSM message template for Meta review."""
    service = CampaignService(db)
    tpl = await service.create_template(user_context.organization_id, payload)
    return APIResponse.ok(data=MessageTemplateResponse.model_validate(tpl))


@router.get("/templates", response_model=APIResponse[List[MessageTemplateResponse]])
async def list_templates(
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[List[MessageTemplateResponse]]:
    """List WhatsApp message templates."""
    query = select(MessageTemplate).where(MessageTemplate.organization_id == user_context.organization_id)
    res = await db.execute(query)
    templates = res.scalars().all()
    return APIResponse.ok(data=[MessageTemplateResponse.model_validate(t) for t in templates])


@router.post("/segments", status_code=status.HTTP_201_CREATED, response_model=APIResponse[CampaignSegmentResponse])
async def create_segment(
    payload: CampaignSegmentCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[CampaignSegmentResponse]:
    """Define dynamic target segment for broadcasts."""
    service = CampaignService(db)
    segment = await service.create_segment(user_context.organization_id, payload)
    return APIResponse.ok(data=CampaignSegmentResponse.model_validate(segment))


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=APIResponse[CampaignResponse])
async def create_campaign(
    payload: CampaignCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[CampaignResponse]:
    """Create and queue a WhatsApp broadcast campaign."""
    service = CampaignService(db)
    camp = await service.create_campaign(user_context.organization_id, payload)
    return APIResponse.ok(data=CampaignResponse.model_validate(camp))
