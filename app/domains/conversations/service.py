"""Business logic service for Unified Inbox, Message dispatch, and SLA timers."""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import enum_value
from app.common.schemas import PaginationMeta
from app.constants import (
    ContactEventType,
    ConversationStatus,
    MessageDeliveryStatus,
    MessageSenderType,
)
from app.domains.channels import inbound
from app.domains.channels.models import Channel, ChannelAccount
from app.domains.contacts.models import Contact, ContactEvent
from app.domains.conversations.models import Conversation, Message, SatisfactionRating, Team
from app.domains.conversations.repository import ConversationRepository, MessageRepository
from app.domains.conversations.schemas import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
)
from app.domains.identity.models import Membership
from app.exceptions import AIProviderError, ResourceNotFoundError, ValidationError

logger = logging.getLogger("conversation_service")

WHATSAPP_WINDOW = timedelta(hours=24)


class ConversationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.conv_repo = ConversationRepository(session)
        self.msg_repo = MessageRepository(session)

    async def get_owned(self, org_id: UUID, conversation_id: UUID) -> Conversation:
        conv = await self.conv_repo.get_by_id(conversation_id, organization_id=org_id)
        if not conv:
            raise ResourceNotFoundError("Conversation", conversation_id)
        return conv

    async def to_responses(self, convs: Sequence[Conversation]) -> List[ConversationResponse]:
        """Attach contact name and channel type so the inbox needs no extra lookups."""
        if not convs:
            return []
        rows = await self.session.execute(
            select(Conversation.id, Contact.first_name, Contact.last_name, Channel.type)
            .join(Contact, Contact.id == Conversation.contact_id)
            .join(ChannelAccount, ChannelAccount.id == Conversation.channel_account_id)
            .join(Channel, Channel.id == ChannelAccount.channel_id)
            .where(Conversation.id.in_([c.id for c in convs]))
        )
        extra: Dict[UUID, Tuple[Optional[str], Optional[str]]] = {
            r.id: (" ".join(p for p in (r.first_name, r.last_name) if p) or None, r.type) for r in rows
        }
        out = []
        for c in convs:
            name, channel_type = extra.get(c.id, (None, None))
            out.append(
                ConversationResponse.model_validate(c).model_copy(
                    update={"contact_name": name, "channel_type": channel_type}
                )
            )
        return out

    async def list_conversations(
        self, org_id: UUID, page: int, page_size: int, status: Optional[str] = None,
        contact_id: Optional[UUID] = None,
    ) -> Tuple[Sequence[Conversation], PaginationMeta]:
        """Inbox order: most recent activity first."""
        conds = [Conversation.organization_id == org_id, Conversation.is_deleted.is_(False)]
        if status:
            conds.append(Conversation.status == status)
        if contact_id:
            conds.append(Conversation.contact_id == contact_id)
        total = (await self.session.execute(select(func.count()).select_from(Conversation).where(*conds))).scalar_one()
        items = (
            await self.session.execute(
                select(Conversation)
                .where(*conds)
                .order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        total_pages = math.ceil(total / page_size) if total else 0
        meta = PaginationMeta(
            total_count=total, page=page, page_size=page_size, total_pages=total_pages,
            has_next=page < total_pages, has_previous=page > 1,
        )
        return items, meta

    async def create_conversation(
        self, org_id: UUID, data: ConversationCreate
    ) -> Conversation:
        contact = await self.session.get(Contact, data.contact_id)
        if not contact or contact.organization_id != org_id or contact.is_deleted:
            raise ResourceNotFoundError("Contact", data.contact_id)
        account = await self.session.get(ChannelAccount, data.channel_account_id)
        if not account or account.organization_id != org_id or account.is_deleted:
            raise ResourceNotFoundError("ChannelAccount", data.channel_account_id)

        # The WhatsApp 24h reply window only opens when the customer messages us
        return await self.conv_repo.create(
            organization_id=org_id,
            contact_id=data.contact_id,
            channel_account_id=data.channel_account_id,
            subject=data.subject,
            priority=enum_value(data.priority),
            status=ConversationStatus.OPEN.value,
            service_window_expires_at=None,
            last_message_at=datetime.now(timezone.utc),
        )

    async def post_message(
        self,
        org_id: UUID,
        conversation_id: UUID,
        data: MessageCreate,
        sender_type: MessageSenderType,
        sender_id: Optional[UUID] = None,
    ) -> Message:
        conv = await self.get_owned(org_id, conversation_id)
        now = datetime.now(timezone.utc)
        sender_type_val = sender_type.value if hasattr(sender_type, "value") else str(sender_type)
        content_type_val = data.content_type.value if hasattr(data.content_type, "value") else str(data.content_type)

        if sender_type_val == MessageSenderType.CONTACT.value:
            conv.service_window_expires_at = now + WHATSAPP_WINDOW
            conv.unread_count += 1
            conv.status = ConversationStatus.WAITING_FOR_AGENT.value
        else:
            if not conv.first_response_at:
                conv.first_response_at = now
            conv.status = ConversationStatus.WAITING_FOR_USER.value
        conv.last_message_at = now

        payload = dict(data.payload_json)
        delivery_status = MessageDeliveryStatus.SENT.value
        if sender_type_val != MessageSenderType.CONTACT.value and data.text_content:
            delivery_status, error = await self._dispatch_outbound(conv, data.text_content)
            if error:
                payload["delivery_error"] = error

        msg = await self.msg_repo.create(
            organization_id=org_id,
            conversation_id=conversation_id,
            sender_type=sender_type_val,
            sender_id=sender_id,
            content_type=content_type_val,
            text_content=data.text_content,
            payload_json=payload,
            delivery_status=delivery_status,
            reply_to_message_id=data.reply_to_message_id,
        )
        return msg

    async def _dispatch_outbound(self, conv: Conversation, text_content: str) -> Tuple[str, Optional[str]]:
        """Send an agent reply on the conversation's channel. Returns (delivery_status, error)."""
        from app.domains.channels.facebook_service import send_facebook_message
        from app.domains.channels.instagram_service import send_instagram_message
        from app.domains.channels.whatsapp_service import send_whatsapp_message

        failed = MessageDeliveryStatus.FAILED.value
        row = (
            await self.session.execute(
                select(ChannelAccount.account_identifier, ChannelAccount.encrypted_credentials, Channel.type)
                .join(Channel, Channel.id == ChannelAccount.channel_id)
                .where(ChannelAccount.id == conv.channel_account_id, ChannelAccount.is_deleted.is_(False))
            )
        ).first()
        if not row:
            return failed, "The channel for this conversation is disconnected"

        contact = await self.session.get(Contact, conv.contact_id)
        attrs = (contact.custom_attributes or {}) if contact else {}
        creds = inbound.load_credentials(row.encrypted_credentials)
        channel_type = row.type

        try:
            if channel_type == "whatsapp":
                window = conv.service_window_expires_at
                if not window or window < datetime.now(timezone.utc):
                    return failed, (
                        "WhatsApp only allows free-form replies within 24 hours of the customer's last message; "
                        "use an approved template to re-open the conversation"
                    )
                token = creds.get("access_token") or creds.get("api_key_or_token")
                phone_number_id = creds.get("phone_number_id") or row.account_identifier
                recipient = attrs.get("wa_id") or (
                    contact.phone_number.lstrip("+").replace(" ", "").replace("-", "") if contact and contact.phone_number else None
                )
                if not (token and recipient):
                    return failed, "Missing WhatsApp credentials or customer number"
                sent = await send_whatsapp_message(token, phone_number_id, recipient, text_content)
            elif channel_type == "messenger":
                token = creds.get("page_access_token") or creds.get("api_key_or_token")
                recipient = attrs.get("psid")
                if not (token and recipient):
                    return failed, "Missing Messenger credentials or customer PSID"
                sent = await send_facebook_message(token, recipient, text_content)
            elif channel_type == "instagram":
                token = creds.get("access_token") or creds.get("page_access_token") or creds.get("api_key_or_token")
                recipient = attrs.get("igsid")
                if not (token and recipient):
                    return failed, "Missing Instagram credentials or customer IGSID"
                sent = await send_instagram_message(token, recipient, text_content, sender_account_id=row.account_identifier)
            else:
                # Channels without an outbound API (e.g. web chat) read replies from the inbox
                return MessageDeliveryStatus.SENT.value, None
        except Exception as e:
            logger.exception(f"Outbound {channel_type} dispatch failed for conversation {conv.id}: {e}")
            return failed, "Unexpected error while sending"

        if sent:
            return MessageDeliveryStatus.DELIVERED.value, None
        label = {"whatsapp": "WhatsApp", "messenger": "Messenger", "instagram": "Instagram"}.get(channel_type, channel_type)
        return failed, f"{label} rejected the message; check the channel connection"

    async def resolve_conversation(
        self, org_id: UUID, conversation_id: UUID
    ) -> Conversation:
        """Resolve the conversation (idempotent) and hand it back to the bot for future messages."""
        conv = await self.get_owned(org_id, conversation_id)
        if conv.status == ConversationStatus.RESOLVED.value:
            return conv

        now = datetime.now(timezone.utc)
        conv.status = ConversationStatus.RESOLVED.value
        conv.resolved_at = now
        conv.unread_count = 0

        self.session.add(
            ContactEvent(
                organization_id=org_id, contact_id=conv.contact_id, event_type=ContactEventType.CONVERSATION_RESOLVED.value,
                actor_type="agent", event_data={"conversation_id": str(conv.id)},
            )
        )

        # One CSAT invite per conversation
        existing = await self.session.execute(
            select(SatisfactionRating.id).where(SatisfactionRating.conversation_id == conv.id)
        )
        if not existing.first():
            self.session.add(
                SatisfactionRating(
                    organization_id=org_id,
                    conversation_id=conv.id,
                    contact_id=conv.contact_id,
                    rating_score=0,  # Unrated initial state
                    survey_sent_at=now,
                )
            )
        await self.session.flush()
        return conv

    async def suggest_reply(self, org_id: UUID, conversation_id: UUID) -> str:
        """Draft a reply to the customer's latest message for an agent to review (never sent)."""
        from app.domains.agents.service import AgentService
        from app.domains.ai.gemini_service import generate_gemini_response
        from app.domains.rag.service import RAGService

        await self.get_owned(org_id, conversation_id)
        recent = await self.msg_repo.list_by_conversation(conversation_id, org_id, limit=inbound.HISTORY_TURNS + 1)
        customer_msgs = [m for m in recent if m.sender_type == MessageSenderType.CONTACT.value and m.text_content]
        if not customer_msgs:
            raise ValidationError("There is no customer message to reply to yet")

        question = customer_msgs[-1].text_content
        history = [
            {"sender_type": m.sender_type, "text_content": m.text_content}
            for m in recent if m.text_content and m is not customer_msgs[-1]
        ]
        retrieval = await RAGService.retrieve_context(self.session, org_id, question)
        system_prompt = await AgentService.get_active_system_prompt(self.session, org_id)
        draft = await generate_gemini_response(question, system_prompt, retrieval.as_context(), history)
        if not draft:
            raise AIProviderError("gemini", "Could not draft a reply right now. Please try again shortly.")
        return draft.strip()

    async def mark_read(self, org_id: UUID, conversation_id: UUID) -> Conversation:
        conv = await self.get_owned(org_id, conversation_id)
        conv.unread_count = 0
        await self.session.flush()
        return conv

    async def update_conversation(
        self, org_id: UUID, conversation_id: UUID, data: ConversationUpdate
    ) -> Conversation:
        conv = await self.get_owned(org_id, conversation_id)
        changes = data.model_dump(exclude_unset=True)

        if "assigned_user_id" in changes and changes["assigned_user_id"]:
            member = await self.session.execute(
                select(Membership.id).where(
                    Membership.organization_id == org_id, Membership.user_id == changes["assigned_user_id"]
                )
            )
            if not member.first():
                raise ValidationError("assigned_user_id is not a member of this workspace")

        if "team_id" in changes and changes["team_id"]:
            team = await self.session.get(Team, changes["team_id"])
            if not team or team.organization_id != org_id:
                raise ValidationError("team_id does not belong to this workspace")

        if "status" in changes and changes["status"]:
            new_status = changes["status"].value if hasattr(changes["status"], "value") else changes["status"]
            if new_status == ConversationStatus.RESOLVED.value:
                await self.resolve_conversation(org_id, conversation_id)
            else:
                conv.status = new_status
                if new_status == ConversationStatus.CLOSED.value:
                    conv.closed_at = datetime.now(timezone.utc)
        if "priority" in changes and changes["priority"]:
            conv.priority = changes["priority"].value if hasattr(changes["priority"], "value") else changes["priority"]
        for key in ("assigned_user_id", "team_id"):
            if key in changes:
                setattr(conv, key, changes[key])

        await self.session.flush()
        await self.session.refresh(conv)
        return conv
