"""Data access repositories for Conversations, Messages, and SLAs."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.repository import BaseRepository
from app.domains.conversations.models import (
    CannedResponse,
    Conversation,
    Message,
    MessageAttachment,
    SatisfactionRating,
    SLAPolicy,
)


class ConversationRepository(BaseRepository[Conversation]):
    def __init__(self, session: AsyncSession):
        super().__init__(Conversation, session)

    async def get_with_messages(
        self, conversation_id: UUID, org_id: UUID
    ) -> Optional[Conversation]:
        query = (
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.organization_id == org_id,
                Conversation.is_deleted == False,  # noqa: E712
            )
            .options(
                selectinload(Conversation.messages).selectinload(Message.attachments),
                selectinload(Conversation.contact),
            )
        )
        result = await self.session.execute(query)
        return result.scalars().first()


class MessageRepository(BaseRepository[Message]):
    def __init__(self, session: AsyncSession):
        super().__init__(Message, session)

    async def list_by_conversation(
        self, conversation_id: UUID, org_id: UUID, limit: int = 50, before_id: Optional[UUID] = None
    ) -> List[Message]:
        """The newest `limit` messages (or those older than `before_id`), returned oldest first."""
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.organization_id == org_id)
            .options(selectinload(Message.attachments))
        )
        if before_id:
            anchor = (
                await self.session.execute(
                    select(Message.created_at, Message.id).where(
                        Message.id == before_id, Message.conversation_id == conversation_id
                    )
                )
            ).first()
            if not anchor:
                return []
            query = query.where(tuple_(Message.created_at, Message.id) < tuple_(anchor.created_at, anchor.id))
        query = query.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(reversed(result.scalars().all()))
