"""Business logic service for Contacts and CRM operations."""

import math
import re
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import enum_value
from app.common.schemas import PaginationMeta
from app.constants import ContactEventType
from app.domains.channels.models import Channel, ChannelAccount
from app.domains.contacts.models import Contact, ContactEvent, ContactNote, ContactTag, Tag
from app.domains.contacts.repository import ContactRepository, TagRepository
from app.domains.contacts.schemas import (
    ContactCreate,
    ContactNoteCreate,
    ContactNoteResponse,
    ContactResponse,
    ContactUpdate,
    TagCreate,
    TagResponse,
)
from app.domains.conversations.models import Conversation
from app.domains.identity.models import User
from app.exceptions import ResourceConflictError, ResourceNotFoundError, ValidationError

# Contact fields an update may set to null
_NULLABLE_FIELDS = {"first_name", "last_name", "email", "phone_number", "avatar_url"}


class ContactService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.contact_repo = ContactRepository(session)
        self.tag_repo = TagRepository(session)

    # ==========================================================================
    # Contacts
    # ==========================================================================

    async def get_owned(self, org_id: UUID, contact_id: UUID) -> Contact:
        contact = await self.contact_repo.get_by_id(contact_id, organization_id=org_id)
        if not contact:
            raise ResourceNotFoundError("Contact", contact_id)
        return contact

    def _event(self, org_id: UUID, contact_id: UUID, event_type: ContactEventType,
               actor_id: Optional[UUID], data: Optional[dict] = None) -> None:
        self.session.add(
            ContactEvent(
                organization_id=org_id,
                contact_id=contact_id,
                event_type=event_type.value,
                actor_id=actor_id,
                actor_type="agent" if actor_id else "system",
                event_data=data or {},
            )
        )

    async def _ensure_unique(self, org_id: UUID, phone: Optional[str], email: Optional[str],
                             exclude_id: Optional[UUID] = None) -> None:
        for column, value, label in ((Contact.phone_number, phone, "phone number"), (Contact.email, email, "email")):
            if not value:
                continue
            conds = [Contact.organization_id == org_id, Contact.is_deleted.is_(False), func.lower(column) == value.lower()]
            if exclude_id:
                conds.append(Contact.id != exclude_id)
            if (await self.session.execute(select(Contact.id).where(*conds).limit(1))).first():
                raise ResourceConflictError(f"A contact with this {label} already exists")

    async def _validate_tags(self, org_id: UUID, tag_ids: List[UUID]) -> List[UUID]:
        unique_ids = list(dict.fromkeys(tag_ids))
        if not unique_ids:
            return []
        found = (
            await self.session.execute(select(Tag.id).where(Tag.organization_id == org_id, Tag.id.in_(unique_ids)))
        ).scalars().all()
        missing = set(unique_ids) - set(found)
        if missing:
            raise ResourceNotFoundError("Tag", next(iter(missing)))
        return unique_ids

    async def to_responses(self, org_id: UUID, contacts: Sequence[Contact]) -> List[ContactResponse]:
        """Attach tags, channels, conversation count and last activity."""
        if not contacts:
            return []
        ids = [c.id for c in contacts]

        tags: Dict[UUID, List[Tag]] = defaultdict(list)
        for contact_id, tag in await self.session.execute(
            select(ContactTag.contact_id, Tag).join(Tag, Tag.id == ContactTag.tag_id)
            .where(ContactTag.contact_id.in_(ids)).order_by(Tag.name)
        ):
            tags[contact_id].append(tag)

        stats = {
            r.contact_id: r
            for r in await self.session.execute(
                select(
                    Conversation.contact_id,
                    func.count(Conversation.id).label("n"),
                    func.max(Conversation.last_message_at).label("last"),
                    func.array_agg(func.distinct(Channel.type)).label("channels"),
                )
                .join(ChannelAccount, ChannelAccount.id == Conversation.channel_account_id)
                .join(Channel, Channel.id == ChannelAccount.channel_id)
                .where(Conversation.organization_id == org_id, Conversation.contact_id.in_(ids),
                       Conversation.is_deleted.is_(False))
                .group_by(Conversation.contact_id)
            )
        }

        out = []
        for c in contacts:
            s = stats.get(c.id)
            # Build from columns only: reading the ORM `tags` relationship would lazy-load
            columns = {col.key: getattr(c, col.key) for col in Contact.__table__.columns}
            out.append(
                ContactResponse.model_validate(columns).model_copy(update={
                    "tags": [TagResponse.model_validate(t) for t in tags.get(c.id, [])],
                    "channels": sorted(ch for ch in (s.channels if s else []) if ch),
                    "conversation_count": s.n if s else 0,
                    "last_activity_at": (s.last if s else None) or c.created_at,
                })
            )
        return out

    async def list_contacts(
        self,
        org_id: UUID,
        page: int,
        page_size: int,
        q: Optional[str] = None,
        lifecycle_stage: Optional[str] = None,
        tag_id: Optional[UUID] = None,
        is_blocked: Optional[bool] = None,
    ) -> Tuple[Sequence[Contact], PaginationMeta]:
        """Search and filter contacts, most recently active first."""
        conds = [Contact.organization_id == org_id, Contact.is_deleted.is_(False)]
        if q and q.strip():
            term = f"%{q.strip()}%"
            matches = [
                func.concat_ws(" ", Contact.first_name, Contact.last_name).ilike(term),
                Contact.email.ilike(term),
                Contact.phone_number.ilike(term),
            ]
            digits = re.sub(r"\D", "", q)
            if len(digits) >= 4:
                matches.append(func.regexp_replace(Contact.phone_number, r"\D", "", "g").like(f"%{digits}%"))
            conds.append(or_(*matches))
        if lifecycle_stage:
            conds.append(Contact.lifecycle_stage == lifecycle_stage)
        if is_blocked is not None:
            conds.append(Contact.is_blocked.is_(is_blocked))
        if tag_id:
            conds.append(exists().where(and_(ContactTag.contact_id == Contact.id, ContactTag.tag_id == tag_id)))

        last_activity = (
            select(func.max(Conversation.last_message_at))
            .where(Conversation.contact_id == Contact.id, Conversation.is_deleted.is_(False))
            .correlate(Contact)
            .scalar_subquery()
        )
        total = (await self.session.execute(select(func.count()).select_from(Contact).where(*conds))).scalar_one()
        items = (
            await self.session.execute(
                select(Contact)
                .where(*conds)
                .order_by(func.coalesce(last_activity, Contact.created_at).desc(), Contact.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        total_pages = math.ceil(total / page_size) if total else 0
        return items, PaginationMeta(
            total_count=total, page=page, page_size=page_size, total_pages=total_pages,
            has_next=page < total_pages, has_previous=page > 1,
        )

    async def create_contact(
        self, org_id: UUID, data: ContactCreate, actor_id: Optional[UUID] = None
    ) -> Contact:
        await self._ensure_unique(org_id, data.phone_number, data.email)
        tag_ids = await self._validate_tags(org_id, data.tag_ids)

        contact = await self.contact_repo.create(
            organization_id=org_id,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            phone_number=data.phone_number,
            avatar_url=data.avatar_url,
            lifecycle_stage=enum_value(data.lifecycle_stage),
            custom_attributes=data.custom_attributes,
        )
        for tag_id in tag_ids:
            self.session.add(ContactTag(organization_id=org_id, contact_id=contact.id, tag_id=tag_id))
        self._event(org_id, contact.id, ContactEventType.CREATED, actor_id, {"lifecycle_stage": contact.lifecycle_stage})
        await self.session.flush()
        return contact

    async def update_contact(
        self, org_id: UUID, contact_id: UUID, data: ContactUpdate, actor_id: Optional[UUID] = None
    ) -> Contact:
        contact = await self.get_owned(org_id, contact_id)
        changes = data.model_dump(exclude_unset=True)

        # Explicit nulls clear optional fields; nulls on required fields are ignored
        for key in list(changes):
            if changes[key] is None and key not in _NULLABLE_FIELDS:
                del changes[key]

        merged = {f: changes.get(f, getattr(contact, f)) for f in ("first_name", "last_name", "email", "phone_number")}
        if not any(merged.values()):
            raise ValidationError("A contact needs at least a name, phone number or email")
        await self._ensure_unique(
            org_id,
            changes.get("phone_number") if "phone_number" in changes else None,
            changes.get("email") if "email" in changes else None,
            exclude_id=contact.id,
        )

        if "lifecycle_stage" in changes:
            changes["lifecycle_stage"] = changes["lifecycle_stage"].value if hasattr(changes["lifecycle_stage"], "value") else changes["lifecycle_stage"]
            if changes["lifecycle_stage"] != contact.lifecycle_stage:
                self._event(org_id, contact.id, ContactEventType.STAGE_CHANGED, actor_id,
                            {"from": contact.lifecycle_stage, "to": changes["lifecycle_stage"]})

        for key, value in changes.items():
            setattr(contact, key, value)
        await self.session.flush()
        await self.session.refresh(contact)
        return contact

    async def delete_contact(self, org_id: UUID, contact_id: UUID) -> None:
        """Soft-delete; conversation history is kept for the inbox and reporting."""
        contact = await self.get_owned(org_id, contact_id)
        contact.soft_delete()
        await self.session.flush()

    # ==========================================================================
    # Tags
    # ==========================================================================

    async def list_tags(self, org_id: UUID) -> Sequence[Tag]:
        return (await self.session.execute(select(Tag).where(Tag.organization_id == org_id).order_by(Tag.name))).scalars().all()

    async def create_tag(self, org_id: UUID, data: TagCreate) -> Tag:
        existing = await self.session.execute(
            select(Tag.id).where(Tag.organization_id == org_id, func.lower(Tag.name) == data.name.lower())
        )
        if existing.first():
            raise ResourceConflictError(f"A tag named '{data.name}' already exists")
        return await self.tag_repo.create(
            organization_id=org_id, name=data.name, color_hex=data.color_hex, description=data.description
        )

    async def delete_tag(self, org_id: UUID, tag_id: UUID) -> None:
        tag = await self.tag_repo.get_by_id(tag_id, organization_id=org_id)
        if not tag:
            raise ResourceNotFoundError("Tag", tag_id)
        await self.session.delete(tag)
        await self.session.flush()

    async def set_contact_tags(self, org_id: UUID, contact_id: UUID, tag_ids: List[UUID],
                               actor_id: Optional[UUID] = None) -> Contact:
        contact = await self.get_owned(org_id, contact_id)
        wanted = set(await self._validate_tags(org_id, tag_ids))
        current = set(
            (await self.session.execute(select(ContactTag.tag_id).where(ContactTag.contact_id == contact.id))).scalars().all()
        )
        if current - wanted:
            await self.session.execute(
                delete(ContactTag).where(ContactTag.contact_id == contact.id, ContactTag.tag_id.in_(current - wanted))
            )
        for tag_id in wanted - current:
            self.session.add(ContactTag(organization_id=org_id, contact_id=contact.id, tag_id=tag_id))
        for tag_id in wanted - current:
            self._event(org_id, contact.id, ContactEventType.TAG_ADDED, actor_id, {"tag_id": str(tag_id)})
        for tag_id in current - wanted:
            self._event(org_id, contact.id, ContactEventType.TAG_REMOVED, actor_id, {"tag_id": str(tag_id)})
        await self.session.flush()
        return contact

    # ==========================================================================
    # Notes & timeline
    # ==========================================================================

    async def list_notes(self, org_id: UUID, contact_id: UUID) -> List[ContactNoteResponse]:
        await self.get_owned(org_id, contact_id)
        rows = await self.session.execute(
            select(ContactNote, User.full_name)
            .outerjoin(User, User.id == ContactNote.author_id)
            .where(ContactNote.organization_id == org_id, ContactNote.contact_id == contact_id)
            .order_by(ContactNote.is_pinned.desc(), ContactNote.created_at.desc())
        )
        return [
            ContactNoteResponse.model_validate(note).model_copy(update={"author_name": name})
            for note, name in rows
        ]

    async def add_note(self, org_id: UUID, contact_id: UUID, data: ContactNoteCreate, author_id: UUID) -> ContactNoteResponse:
        await self.get_owned(org_id, contact_id)
        note = ContactNote(
            organization_id=org_id, contact_id=contact_id, author_id=author_id,
            note_text=data.note_text, is_pinned=data.is_pinned,
        )
        self.session.add(note)
        self._event(org_id, contact_id, ContactEventType.NOTE_ADDED, author_id, {"preview": data.note_text[:80]})
        await self.session.flush()
        await self.session.refresh(note)
        author = await self.session.get(User, author_id)
        return ContactNoteResponse.model_validate(note).model_copy(update={"author_name": author.full_name if author else None})

    async def delete_note(self, org_id: UUID, contact_id: UUID, note_id: UUID) -> None:
        note = await self.session.get(ContactNote, note_id)
        if not note or note.organization_id != org_id or note.contact_id != contact_id:
            raise ResourceNotFoundError("ContactNote", note_id)
        await self.session.delete(note)
        await self.session.flush()

    async def list_events(self, org_id: UUID, contact_id: UUID, limit: int = 100) -> Sequence[ContactEvent]:
        await self.get_owned(org_id, contact_id)
        return (
            await self.session.execute(
                select(ContactEvent)
                .where(ContactEvent.organization_id == org_id, ContactEvent.contact_id == contact_id)
                .order_by(ContactEvent.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
