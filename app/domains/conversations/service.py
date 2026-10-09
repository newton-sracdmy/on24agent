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

        # Dispatch outbound message to external channel if applicable (e.g. Facebook Messenger, WhatsApp)
        if sender_type == MessageSenderType.AGENT and data.text_content:
            try:
                import json
                import asyncio
                from sqlalchemy import text
                from app.security import decrypt_secret
                from app.domains.channels.facebook_service import send_facebook_message
                from app.domains.channels.whatsapp_service import send_whatsapp_message

                q_ch = await self.session.execute(
                    text("SELECT account_identifier, encrypted_credentials FROM channel_accounts WHERE id = :chid AND is_deleted = false;"),
                    {"chid": conv.channel_account_id},
                )
                ch_data = q_ch.mappings().first()
                if ch_data and ch_data["encrypted_credentials"]:
                    creds = json.loads(decrypt_secret(ch_data["encrypted_credentials"]))
                    q_contact = await self.session.execute(
                        text("SELECT phone_number, custom_attributes FROM contacts WHERE id = :cid;"),
                        {"cid": conv.contact_id},
                    )
                    c_data = q_contact.mappings().first()

                    # 1. Facebook Messenger Dispatch
                    page_token = creds.get("page_access_token")
                    if c_data and c_data["custom_attributes"] and "psid" in c_data["custom_attributes"] and page_token:
                        recipient_psid = c_data["custom_attributes"]["psid"]
                        asyncio.create_task(send_facebook_message(page_token, recipient_psid, data.text_content))

                    # 2. WhatsApp Cloud API Dispatch
                    wa_token = creds.get("access_token")
                    phone_number_id = creds.get("phone_number_id", ch_data["account_identifier"])
                    recipient_wa = None
                    if c_data:
                        if c_data["custom_attributes"] and "wa_id" in c_data["custom_attributes"]:
                            recipient_wa = c_data["custom_attributes"]["wa_id"]
                        elif c_data["phone_number"]:
                            recipient_wa = c_data["phone_number"].replace("+", "").strip()

                    if wa_token and phone_number_id and recipient_wa:
                        asyncio.create_task(send_whatsapp_message(wa_token, phone_number_id, recipient_wa, data.text_content))
            except Exception as e:
                pass

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
