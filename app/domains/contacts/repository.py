"""Data access repositories for Contacts and CRM."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.repository import BaseRepository
from app.domains.contacts.models import (
    Contact,
    ContactEvent,
    ContactIdentity,
    ContactNote,
    ContactTag,
    CustomField,
    Tag,
)


class ContactRepository(BaseRepository[Contact]):
    def __init__(self, session: AsyncSession):
        super().__init__(Contact, session)

    async def get_by_phone(self, org_id: UUID, phone: str) -> Optional[Contact]:
        query = select(Contact).where(
            Contact.organization_id == org_id,
            Contact.phone_number == phone,
            Contact.is_deleted == False,  # noqa: E712
        )
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_by_identity(
        self, org_id: UUID, identity_type: str, identifier_value: str
    ) -> Optional[Contact]:
        query = (
            select(Contact)
            .join(ContactIdentity, ContactIdentity.contact_id == Contact.id)
            .where(
                Contact.organization_id == org_id,
                ContactIdentity.identity_type == identity_type,
                ContactIdentity.identifier_value == identifier_value,
                Contact.is_deleted == False,  # noqa: E712
            )
        )
        result = await self.session.execute(query)
        return result.scalars().first()


class TagRepository(BaseRepository[Tag]):
    def __init__(self, session: AsyncSession):
        super().__init__(Tag, session)

    async def get_by_name(self, org_id: UUID, name: str) -> Optional[Tag]:
        query = select(Tag).where(Tag.organization_id == org_id, Tag.name == name)
        result = await self.session.execute(query)
        return result.scalars().first()
