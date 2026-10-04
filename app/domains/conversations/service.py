"""Business logic service for Unified Inbox, Message dispatch, and SLA timers."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    ConversationStatus,
    MessageDeliveryStatus,
    MessageSenderType,
)
from app.domains.conversations.models import Conversation, Message, SatisfactionRating
from app.domains.conversations.repository import ConversationRepository, MessageRepository
from app.domains.conversations.schemas import ConversationCreate, ConversationUpdate, MessageCreate
from app.exceptions import ResourceNotFoundError


class ConversationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.conv_repo = ConversationRepository(session)
        self.msg_repo = MessageRepository(session)

    async def create_conversation(
        self, org_id: UUID, data: ConversationCreate
    ) -> Conversation:
        # 24-hour customer service window for messaging channels (Meta WhatsApp policy)
        now = datetime.now(timezone.utc)
        window_expiry = now + timedelta(hours=24)

        conv = await self.conv_repo.create(
            organization_id=org_id,
            contact_id=data.contact_id,
            channel_account_id=data.channel_account_id,
            subject=data.subject,
            priority=data.priority.value,
            status=ConversationStatus.OPEN.value,
            service_window_expires_at=window_expiry,
            last_message_at=now,
        )
        return conv

    async def post_message(
        self,
        org_id: UUID,
        conversation_id: UUID,
        data: MessageCreate,
        sender_type: MessageSenderType,
        sender_id: Optional[UUID] = None,
    ) -> Message:
        conv = await self.conv_repo.get_by_id(conversation_id, organization_id=org_id)
        if not conv:
            raise ResourceNotFoundError("Conversation", conversation_id)

        now = datetime.now(timezone.utc)

        # Update WhatsApp 24-hour service window if message comes from contact
        if sender_type == MessageSenderType.CONTACT:
            conv.service_window_expires_at = now + timedelta(hours=24)
            conv.unread_count += 1
            conv.status = ConversationStatus.WAITING_FOR_AGENT.value
        else:
            # First response tracking
            if not conv.first_response_at:
                conv.first_response_at = now
            conv.status = ConversationStatus.WAITING_FOR_USER.value

        conv.last_message_at = now

        msg = await self.msg_repo.create(
            organization_id=org_id,
            conversation_id=conversation_id,
            sender_type=sender_type.value,
            sender_id=sender_id,
            content_type=data.content_type.value,
            text_content=data.text_content,
            payload_json=data.payload_json,
            delivery_status=MessageDeliveryStatus.SENT.value,
            reply_to_message_id=data.reply_to_message_id,
        )
        await self.session.flush()
        return msg

    async def resolve_conversation(
        self, org_id: UUID, conversation_id: UUID
    ) -> Conversation:
        conv = await self.conv_repo.get_by_id(conversation_id, organization_id=org_id)
        if not conv:
            raise ResourceNotFoundError("Conversation", conversation_id)

        now = datetime.now(timezone.utc)
        conv.status = ConversationStatus.RESOLVED.value
        conv.resolved_at = now

        # Create CSAT survey invite record
        csat = SatisfactionRating(
            organization_id=org_id,
            conversation_id=conv.id,
            contact_id=conv.contact_id,
            rating_score=0,  # Unrated initial state
            survey_sent_at=now,
        )
        self.session.add(csat)
        await self.session.flush()
        return conv
