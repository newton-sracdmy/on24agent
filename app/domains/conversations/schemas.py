"""Pydantic schemas for Unified Inbox, Messages, SLAs, and CSAT."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.common.schemas import BaseSchema
from app.constants import (
    ConversationPriority,
    ConversationStatus,
    MessageContentType,
    MessageDeliveryStatus,
    MessageSenderType,
    SLABreachStatus,
)


# WhatsApp's limit for a text message body; Messenger/Instagram allow less, enforced by Meta
MAX_MESSAGE_LENGTH = 4096


class MessageCreate(BaseSchema):
    text_content: Optional[str] = Field(None, max_length=MAX_MESSAGE_LENGTH)
    content_type: MessageContentType = MessageContentType.TEXT
    payload_json: Dict[str, Any] = Field(default_factory=dict)
    reply_to_message_id: Optional[UUID] = None

    @field_validator("text_content", mode="before")
    @classmethod
    def _strip_text(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _text_required(self) -> "MessageCreate":
        if self.content_type == MessageContentType.TEXT and not self.text_content:
            raise ValueError("text_content is required for text messages")
        return self


class MessageAttachmentResponse(BaseSchema):
    id: UUID
    file_name: str
    file_type: str
    file_size_bytes: int
    storage_url: str
    mime_type: str


class MessageResponse(BaseSchema):
    id: UUID
    conversation_id: UUID
    sender_type: str
    sender_id: Optional[UUID] = None
    content_type: str
    text_content: Optional[str] = None
    payload_json: Dict[str, Any] = {}
    delivery_status: str
    external_id: Optional[str] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    created_at: datetime
    attachments: List[MessageAttachmentResponse] = []


class ConversationCreate(BaseSchema):
    contact_id: UUID
    channel_account_id: UUID
    subject: Optional[str] = Field(None, max_length=255)
    priority: ConversationPriority = ConversationPriority.MEDIUM


class ConversationUpdate(BaseSchema):
    status: Optional[ConversationStatus] = None
    priority: Optional[ConversationPriority] = None
    assigned_user_id: Optional[UUID] = None
    team_id: Optional[UUID] = None


class ConversationResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    contact_id: UUID
    channel_account_id: UUID
    team_id: Optional[UUID] = None
    assigned_user_id: Optional[UUID] = None
    assigned_agent_id: Optional[UUID] = None
    status: str
    priority: str
    subject: Optional[str] = None
    service_window_expires_at: Optional[datetime] = None
    first_response_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    sla_breach_status: str
    last_message_at: datetime
    unread_count: int
    created_at: datetime
    # Denormalized for inbox rendering
    contact_name: Optional[str] = None
    channel_type: Optional[str] = None


class CannedResponseCreate(BaseSchema):
    shortcut_code: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=100)
    content_text: str = Field(..., min_length=1)
    team_id: Optional[UUID] = None


class CannedResponseResponse(BaseSchema):
    id: UUID
    shortcut_code: str
    title: str
    content_text: str
    team_id: Optional[UUID] = None
    created_at: datetime


class CSATSurveySubmit(BaseSchema):
    rating_score: int = Field(..., ge=1, le=5)
    feedback_comment: Optional[str] = None
