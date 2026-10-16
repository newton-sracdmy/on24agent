"""FastAPI router endpoints for Contacts and CRM operations."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import APIResponse, PaginatedResponse
from app.constants import ContactLifecycleStage
from app.dependencies import AuthenticatedUserContext, get_db, require_tenant
from app.domains.contacts.schemas import (
    ContactCreate,
    ContactEventResponse,
    ContactNoteCreate,
    ContactNoteResponse,
    ContactResponse,
    ContactTagsSet,
    ContactUpdate,
    TagCreate,
    TagResponse,
)
from app.domains.contacts.service import ContactService

router = APIRouter()


# ==============================================================================
# Tags (declared before /{contact_id} so "tags" is not parsed as an ID)
# ==============================================================================

@router.get("/tags", response_model=APIResponse[List[TagResponse]])
async def list_tags(
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[List[TagResponse]]:
    """List the workspace's contact tags."""
    tags = await ContactService(db).list_tags(user_context.organization_id)
    return APIResponse.ok(data=[TagResponse.model_validate(t) for t in tags])


@router.post("/tags", status_code=status.HTTP_201_CREATED, response_model=APIResponse[TagResponse])
async def create_tag(
    payload: TagCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[TagResponse]:
    """Create a contact tag."""
    tag = await ContactService(db).create_tag(user_context.organization_id, payload)
    return APIResponse.ok(data=TagResponse.model_validate(tag))


@router.delete("/tags/{tag_id}", response_model=APIResponse[dict])
async def delete_tag(
    tag_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[dict]:
    """Delete a tag and remove it from every contact."""
    await ContactService(db).delete_tag(user_context.organization_id, tag_id)
    return APIResponse.ok(data={"message": "Tag deleted."})


# ==============================================================================
# Contacts
# ==============================================================================

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=APIResponse[ContactResponse])
async def create_contact(
    payload: ContactCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[ContactResponse]:
    """Create a new customer contact profile."""
    service = ContactService(db)
    contact = await service.create_contact(
        user_context.organization_id, payload, actor_id=user_context.user_id
    )
    return APIResponse.ok(data=(await service.to_responses(user_context.organization_id, [contact]))[0])


@router.get("/", response_model=APIResponse[PaginatedResponse[ContactResponse]])
async def list_contacts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: Optional[str] = Query(None, max_length=100, description="Search name, phone or email"),
    lifecycle_stage: Optional[ContactLifecycleStage] = Query(None),
    tag_id: Optional[UUID] = Query(None),
    is_blocked: Optional[bool] = Query(None),
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[PaginatedResponse[ContactResponse]]:
    """Search and filter contacts, most recently active first."""
    service = ContactService(db)
    items, meta = await service.list_contacts(
        user_context.organization_id, page, page_size, q=q,
        lifecycle_stage=lifecycle_stage.value if lifecycle_stage else None,
        tag_id=tag_id, is_blocked=is_blocked,
    )
    return APIResponse.ok(data=PaginatedResponse(
        items=await service.to_responses(user_context.organization_id, items), pagination=meta
    ))


@router.get("/{contact_id}", response_model=APIResponse[ContactResponse])
async def get_contact(
    contact_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[ContactResponse]:
    """Retrieve full details of a specific contact."""
    service = ContactService(db)
    contact = await service.get_owned(user_context.organization_id, contact_id)
    return APIResponse.ok(data=(await service.to_responses(user_context.organization_id, [contact]))[0])


@router.patch("/{contact_id}", response_model=APIResponse[ContactResponse])
async def update_contact(
    contact_id: UUID,
    payload: ContactUpdate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[ContactResponse]:
    """Update contact attributes, lifecycle stage, or metadata. Send null to clear a field."""
    service = ContactService(db)
    contact = await service.update_contact(
        user_context.organization_id, contact_id, payload, actor_id=user_context.user_id
    )
    return APIResponse.ok(data=(await service.to_responses(user_context.organization_id, [contact]))[0])


@router.delete("/{contact_id}", response_model=APIResponse[dict])
async def delete_contact(
    contact_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[dict]:
    """Delete a contact. Their conversation history stays in the inbox."""
    await ContactService(db).delete_contact(user_context.organization_id, contact_id)
    return APIResponse.ok(data={"message": "Contact deleted."})


@router.put("/{contact_id}/tags", response_model=APIResponse[ContactResponse])
async def set_contact_tags(
    contact_id: UUID,
    payload: ContactTagsSet,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[ContactResponse]:
    """Replace the contact's tags with exactly this list."""
    service = ContactService(db)
    contact = await service.set_contact_tags(
        user_context.organization_id, contact_id, payload.tag_ids, actor_id=user_context.user_id
    )
    return APIResponse.ok(data=(await service.to_responses(user_context.organization_id, [contact]))[0])


@router.get("/{contact_id}/notes", response_model=APIResponse[List[ContactNoteResponse]])
async def list_notes(
    contact_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[List[ContactNoteResponse]]:
    """Internal agent notes, pinned first."""
    return APIResponse.ok(data=await ContactService(db).list_notes(user_context.organization_id, contact_id))


@router.post("/{contact_id}/notes", status_code=status.HTTP_201_CREATED, response_model=APIResponse[ContactNoteResponse])
async def add_note(
    contact_id: UUID,
    payload: ContactNoteCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[ContactNoteResponse]:
    """Add an internal note (never shown to the customer)."""
    note = await ContactService(db).add_note(user_context.organization_id, contact_id, payload, user_context.user_id)
    return APIResponse.ok(data=note)


@router.delete("/{contact_id}/notes/{note_id}", response_model=APIResponse[dict])
async def delete_note(
    contact_id: UUID,
    note_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[dict]:
    await ContactService(db).delete_note(user_context.organization_id, contact_id, note_id)
    return APIResponse.ok(data={"message": "Note deleted."})


@router.get("/{contact_id}/events", response_model=APIResponse[List[ContactEventResponse]])
async def list_events(
    contact_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[List[ContactEventResponse]]:
    """Activity timeline, newest first."""
    events = await ContactService(db).list_events(user_context.organization_id, contact_id)
    return APIResponse.ok(data=[ContactEventResponse.model_validate(e) for e in events])
