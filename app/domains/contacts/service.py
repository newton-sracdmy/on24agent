"""Business logic service for Contacts and CRM operations."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ContactEventType
from app.domains.contacts.models import Contact, ContactEvent, ContactIdentity, Tag
from app.domains.contacts.repository import ContactRepository, TagRepository
from app.domains.contacts.schemas import ContactCreate, ContactUpdate
from app.exceptions import ResourceConflictError, ResourceNotFoundError


class ContactService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.contact_repo = ContactRepository(session)
        self.tag_repo = TagRepository(session)

    async def create_contact(
        self, org_id: UUID, data: ContactCreate, actor_id: Optional[UUID] = None
    ) -> Contact:
        if data.phone_number:
            existing = await self.contact_repo.get_by_phone(org_id, data.phone_number)
            if existing:
                raise ResourceConflictError("A contact with this phone number already exists")

        contact = await self.contact_repo.create(
            organization_id=org_id,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            phone_number=data.phone_number,
            avatar_url=data.avatar_url,
            lifecycle_stage=data.lifecycle_stage.value,
            custom_attributes=data.custom_attributes,
        )

        # Log Contact Created event to timeline
        event = ContactEvent(
            organization_id=org_id,
            contact_id=contact.id,
            event_type=ContactEventType.CREATED.value,
            actor_id=actor_id,
            actor_type="agent" if actor_id else "system",
            event_data={"lifecycle_stage": contact.lifecycle_stage},
        )
        self.session.add(event)
        await self.session.flush()

        return contact

    async def update_contact(
        self, org_id: UUID, contact_id: UUID, data: ContactUpdate, actor_id: Optional[UUID] = None
    ) -> Contact:
        contact = await self.contact_repo.get_by_id(contact_id, organization_id=org_id)
        if not contact:
            raise ResourceNotFoundError("Contact", contact_id)

        update_dict = data.model_dump(exclude_unset=True)
        updated = await self.contact_repo.update(contact, update_dict)
        return updated
