"""Pydantic schemas for Contacts, CRM, Tags, and Custom Attributes."""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import EmailStr, Field, field_validator, model_validator

from app.common.schemas import BaseSchema
from app.constants import ContactEventType, ContactLifecycleStage, IdentityType

MAX_CUSTOM_ATTRIBUTES = 50
MAX_CUSTOM_ATTRIBUTES_BYTES = 10_000
_PHONE_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def normalize_phone(value: Optional[str]) -> Optional[str]:
    """Normalize to E.164 (+<country><number>) so the same number always matches.

    WhatsApp identifies customers by full international number, so a number without its
    country code cannot be matched or messaged.
    """
    if value is None:
        return None
    cleaned = re.sub(r"[\s\-().]", "", value)
    if not cleaned:
        return None
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+"):
        if cleaned.isdigit():
            raise ValueError("Phone number must include the country code, e.g. +8801711000000")
        raise ValueError("Invalid phone number")
    if not _PHONE_RE.match(cleaned):
        raise ValueError("Invalid phone number; use international format, e.g. +8801711000000")
    return cleaned


def _clean_text(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip() or None
    return value


def _check_avatar(value: Optional[str]) -> Optional[str]:
    if value and not re.match(r"^https?://", value, re.IGNORECASE):
        raise ValueError("avatar_url must be an http(s) URL")
    return value


def _check_custom_attributes(value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if value is None:
        return value
    if len(value) > MAX_CUSTOM_ATTRIBUTES:
        raise ValueError(f"At most {MAX_CUSTOM_ATTRIBUTES} custom attributes are allowed")
    if len(json.dumps(value, default=str)) > MAX_CUSTOM_ATTRIBUTES_BYTES:
        raise ValueError("custom_attributes is too large (max 10 KB)")
    return value


class TagCreate(BaseSchema):
    name: str = Field(..., min_length=1, max_length=50)
    color_hex: str = Field(default="#6B7280", pattern="^#[0-9A-Fa-f]{6}$")
    description: Optional[str] = Field(None, max_length=255)

    _strip_name = field_validator("name", "description", mode="before")(_clean_text)


class TagResponse(BaseSchema):
    id: UUID
    name: str
    color_hex: str
    description: Optional[str] = None
    created_at: datetime


class ContactFields(BaseSchema):
    """Shared validation for create and update."""
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, max_length=50)
    avatar_url: Optional[str] = Field(None, max_length=1024)

    _strip = field_validator("first_name", "last_name", "email", "phone_number", "avatar_url", mode="before")(_clean_text)

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v)

    @field_validator("email")
    @classmethod
    def _email(cls, v: Optional[str]) -> Optional[str]:
        return v.lower() if v else v

    _avatar = field_validator("avatar_url")(_check_avatar)


class ContactCreate(ContactFields):
    lifecycle_stage: ContactLifecycleStage = ContactLifecycleStage.LEAD
    custom_attributes: Dict[str, Any] = Field(default_factory=dict)
    tag_ids: List[UUID] = Field(default_factory=list, max_length=50)

    _attrs = field_validator("custom_attributes")(_check_custom_attributes)

    @model_validator(mode="after")
    def _identifiable(self) -> "ContactCreate":
        if not any((self.first_name, self.last_name, self.email, self.phone_number)):
            raise ValueError("Provide at least a name, phone number or email")
        return self


class ContactUpdate(ContactFields):
    lifecycle_stage: Optional[ContactLifecycleStage] = None
    custom_attributes: Optional[Dict[str, Any]] = None
    is_blocked: Optional[bool] = None

    _attrs = field_validator("custom_attributes")(_check_custom_attributes)


class ContactTagsSet(BaseSchema):
    tag_ids: List[UUID] = Field(default_factory=list, max_length=50)


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
    note_text: str = Field(..., min_length=1, max_length=5000)
    is_pinned: bool = False

    _strip = field_validator("note_text", mode="before")(_clean_text)


class ContactNoteResponse(BaseSchema):
    id: UUID
    author_id: UUID
    author_name: Optional[str] = None
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
    # CRM enrichment
    tags: List[TagResponse] = []
    channels: List[str] = []
    conversation_count: int = 0
    last_activity_at: Optional[datetime] = None
