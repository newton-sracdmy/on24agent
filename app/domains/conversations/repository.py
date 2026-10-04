"""Data access repositories for Conversations, Messages, and SLAs."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
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
        self, conversation_id: UUID, limit: int = 50
    ) -> List[Message]:
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .options(selectinload(Message.attachments))
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
