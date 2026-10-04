"""Pydantic schemas for Contacts, CRM, Tags, and Custom Attributes."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import EmailStr, Field

from app.common.schemas import BaseSchema
from app.constants import ContactEventType, ContactLifecycleStage, IdentityType


class TagCreate(BaseSchema):
    name: str = Field(..., min_length=1, max_length=50)
    color_hex: str = Field(default="#6B7280", pattern="^#[0-9A-Fa-f]{6}$")
    description: Optional[str] = None


class TagResponse(BaseSchema):
    id: UUID
    name: str
    color_hex: str
    description: Optional[str] = None
    created_at: datetime


class ContactCreate(BaseSchema):
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, max_length=50)
    avatar_url: Optional[str] = None
    lifecycle_stage: ContactLifecycleStage = ContactLifecycleStage.LEAD
    custom_attributes: Dict[str, Any] = Field(default_factory=dict)
    tag_ids: List[UUID] = Field(default_factory=list)


class ContactUpdate(BaseSchema):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    avatar_url: Optional[str] = None
    lifecycle_stage: Optional[ContactLifecycleStage] = None
    custom_attributes: Optional[Dict[str, Any]] = None
    is_blocked: Optional[bool] = None


class ContactIdentityCreate(BaseSchema):
    identity_type: IdentityType
    identifier_value: str
    metadata_json: Dict[str, Any] = Field(default_factory=dict)


class ContactIdentityResponse(BaseSchema):
    id: UUID
    identity_type: str
    identifier_value: str
    verified_at: Optional[datetime] = None
    metadata_json: Dict[str, Any] = {}
    created_at: datetime


class ContactEventResponse(BaseSchema):
    id: UUID
    event_type: str
    actor_id: Optional[UUID] = None
    actor_type: str
    event_data: Dict[str, Any] = {}
    created_at: datetime


class ContactNoteCreate(BaseSchema):
    note_text: str = Field(..., min_length=1)
    is_pinned: bool = False


class ContactNoteResponse(BaseSchema):
    id: UUID
    author_id: UUID
    note_text: str
    is_pinned: bool
    created_at: datetime


class ContactResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    avatar_url: Optional[str] = None
    lifecycle_stage: str
    custom_attributes: Dict[str, Any] = {}
    is_blocked: bool
    created_at: datetime
    updated_at: datetime
