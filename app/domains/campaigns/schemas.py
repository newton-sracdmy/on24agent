"""Pydantic schemas for Campaigns, Broadcasts, and WhatsApp Templates."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import Field

from app.common.schemas import BaseSchema
from app.constants import CampaignStatus, TemplateApprovalStatus, TemplateCategory


class MessageTemplateCreate(BaseSchema):
    channel_account_id: UUID
    name: str = Field(..., min_length=2, max_length=100)
    language: str = "en"
    category: TemplateCategory = TemplateCategory.MARKETING
    components_json: List[Dict[str, Any]] = Field(default_factory=list)


class MessageTemplateResponse(BaseSchema):
    id: UUID
    channel_account_id: UUID
    name: str
    language: str
    category: str
    status: str
    components_json: List[Dict[str, Any]] = []
    created_at: datetime


class CampaignSegmentCreate(BaseSchema):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    filter_criteria_json: Dict[str, Any] = Field(default_factory=dict)


class CampaignSegmentResponse(BaseSchema):
    id: UUID
    name: str
    description: Optional[str] = None
    cached_contact_count: int
    created_at: datetime


class CampaignCreate(BaseSchema):
    name: str = Field(..., min_length=2, max_length=100)
    channel_account_id: UUID
    template_id: Optional[UUID] = None
    segment_id: UUID
    scheduled_at: Optional[datetime] = None


class CampaignResponse(BaseSchema):
    id: UUID
    name: str
    channel_account_id: UUID
    template_id: Optional[UUID] = None
    segment_id: UUID
    status: str
    total_recipients: int
    sent_count: int
    delivered_count: int
    read_count: int
    failed_count: int
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
