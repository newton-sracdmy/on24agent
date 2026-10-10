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

        sender_type_val = sender_type.value if hasattr(sender_type, "value") else str(sender_type)
        content_type_val = data.content_type.value if hasattr(data.content_type, "value") else str(data.content_type)

        # Update WhatsApp 24-hour service window if message comes from contact
        if sender_type_val in ("contact", MessageSenderType.CONTACT.value):
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
            sender_type=sender_type_val,
            sender_id=sender_id,
            content_type=content_type_val,
            text_content=data.text_content,
            payload_json=data.payload_json,
            delivery_status=MessageDeliveryStatus.SENT.value,
            reply_to_message_id=data.reply_to_message_id,
        )
        msg.attachments = []
        await self.session.flush()

        # Dispatch outbound message to external channel if applicable (e.g. Facebook Messenger, WhatsApp)
        if sender_type_val in ("agent", "ai_bot", "bot", MessageSenderType.AGENT.value, MessageSenderType.AI_BOT.value) and data.text_content:
            try:
                import json
                import logging
                from sqlalchemy import text
                from app.security import decrypt_secret
                from app.config import settings
                from app.domains.channels.facebook_service import send_facebook_message
                from app.domains.channels.whatsapp_service import send_whatsapp_message

                logger = logging.getLogger("conversation_dispatch")

                q_ch = await self.session.execute(
                    text("""
                        SELECT ca.account_identifier, ca.encrypted_credentials, c.type AS channel_type 
                        FROM channel_accounts ca 
                        JOIN channels c ON c.id = ca.channel_id 
                        WHERE ca.id = :chid AND ca.is_deleted = false;
                    """),
                    {"chid": conv.channel_account_id},
                )
                ch_data = q_ch.mappings().first()
                if ch_data:
                    creds = {}
                    if ch_data["encrypted_credentials"]:
                        try:
                            creds = json.loads(decrypt_secret(ch_data["encrypted_credentials"]))
                        except Exception as dec_err:
                            logger.error(f"Failed to decrypt credentials: {dec_err}")

                    q_contact = await self.session.execute(
                        text("SELECT phone_number, custom_attributes FROM contacts WHERE id = :cid;"),
                        {"cid": conv.contact_id},
                    )
                    c_data = q_contact.mappings().first()

                    custom_attrs = {}
                    if c_data and c_data["custom_attributes"]:
                        if isinstance(c_data["custom_attributes"], str):
                            try:
                                custom_attrs = json.loads(c_data["custom_attributes"])
                            except Exception:
                                custom_attrs = {}
                        elif isinstance(c_data["custom_attributes"], dict):
                            custom_attrs = c_data["custom_attributes"]

                    channel_type = ch_data.get("channel_type")

                    # 1. Facebook Messenger Dispatch
                    if channel_type == "messenger" or "psid" in custom_attrs:
                        page_token = creds.get("page_access_token") or getattr(settings, "FB_PAGE_ACCESS_TOKEN", None)
                        recipient_psid = custom_attrs.get("psid")
                        if page_token and recipient_psid:
                            logger.info(f"Dispatching outbound Messenger message to PSID {recipient_psid}")
                            sent = await send_facebook_message(page_token, recipient_psid, data.text_content)
                            if sent:
                                msg.delivery_status = MessageDeliveryStatus.DELIVERED.value

                    # 2. WhatsApp Cloud API Dispatch
                    elif channel_type == "whatsapp" or "wa_id" in custom_attrs or (c_data and c_data["phone_number"]):
                        wa_token = creds.get("access_token") or settings.META_WHATSAPP_API_TOKEN
                        phone_number_id = creds.get("phone_number_id") or ch_data["account_identifier"] or settings.META_WHATSAPP_PHONE_NUMBER_ID
                        recipient_wa = custom_attrs.get("wa_id")
                        if not recipient_wa and c_data and c_data["phone_number"]:
                            recipient_wa = c_data["phone_number"].replace("+", "").replace(" ", "").replace("-", "").strip()

                        if wa_token and phone_number_id and recipient_wa:
                            logger.info(f"Dispatching outbound WhatsApp message to {recipient_wa} via phone number ID {phone_number_id}")
                            sent = await send_whatsapp_message(wa_token, phone_number_id, recipient_wa, data.text_content)
                            if sent:
                                msg.delivery_status = MessageDeliveryStatus.DELIVERED.value

                    # 3. Instagram Direct Message Dispatch
                    elif channel_type == "instagram" or "igsid" in custom_attrs:
                        from app.domains.channels.instagram_service import send_instagram_message
                        ig_token = creds.get("access_token") or getattr(settings, "INSTAGRAM_ACCESS_TOKEN", None) or getattr(settings, "META_WHATSAPP_API_TOKEN", None) or getattr(settings, "FB_PAGE_ACCESS_TOKEN", None)
                        recipient_igsid = custom_attrs.get("igsid")
                        if ig_token and recipient_igsid:
                            logger.info(f"Dispatching outbound Instagram DM to IGSID {recipient_igsid}")
                            sent = await send_instagram_message(ig_token, recipient_igsid, data.text_content)
                            if sent:
                                msg.delivery_status = MessageDeliveryStatus.DELIVERED.value
            except Exception as e:
                logger.exception(f"Error dispatching outbound message to external channel: {e}")

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
