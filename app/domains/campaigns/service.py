"""Business logic service for WhatsApp Templates and Broadcast Campaigns."""

from typing import List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CampaignStatus, TemplateApprovalStatus
from app.domains.campaigns.models import Campaign, CampaignSegment, MessageTemplate
from app.domains.campaigns.schemas import (
    CampaignCreate,
    CampaignSegmentCreate,
    MessageTemplateCreate,
)


class CampaignService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_template(
        self, org_id: UUID, data: MessageTemplateCreate
    ) -> MessageTemplate:
        template = MessageTemplate(
            organization_id=org_id,
            channel_account_id=data.channel_account_id,
            name=data.name,
            language=data.language,
            category=data.category.value,
            components_json=data.components_json,
            status=TemplateApprovalStatus.DRAFT.value,
        )
        self.session.add(template)
        await self.session.flush()
        return template

    async def create_segment(
        self, org_id: UUID, data: CampaignSegmentCreate
    ) -> CampaignSegment:
        segment = CampaignSegment(
            organization_id=org_id,
            name=data.name,
            description=data.description,
            filter_criteria_json=data.filter_criteria_json,
        )
        self.session.add(segment)
        await self.session.flush()
        return segment

    async def create_campaign(self, org_id: UUID, data: CampaignCreate) -> Campaign:
        campaign = Campaign(
            organization_id=org_id,
            name=data.name,
            channel_account_id=data.channel_account_id,
            template_id=data.template_id,
            segment_id=data.segment_id,
            status=CampaignStatus.SCHEDULED.value if data.scheduled_at else CampaignStatus.DRAFT.value,
            scheduled_at=data.scheduled_at,
        )
        self.session.add(campaign)
        await self.session.flush()
        return campaign
