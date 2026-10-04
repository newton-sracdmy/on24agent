"""FastAPI router endpoints for Contacts and CRM operations."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams
from app.common.schemas import APIResponse, PaginatedResponse
from app.dependencies import AuthenticatedUserContext, get_db, require_tenant
from app.domains.contacts.schemas import (
    ContactCreate,
    ContactResponse,
    ContactUpdate,
    TagCreate,
    TagResponse,
)
from app.domains.contacts.service import ContactService

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=APIResponse[ContactResponse])
async def create_contact(
    payload: ContactCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ContactResponse]:
    """Create a new customer contact profile."""
    service = ContactService(db)
    contact = await service.create_contact(
        user_context.organization_id, payload, actor_id=user_context.user_id
    )
    return APIResponse.ok(data=ContactResponse.model_validate(contact))


@router.get("/", response_model=APIResponse[PaginatedResponse[ContactResponse]])
async def list_contacts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[PaginatedResponse[ContactResponse]]:
    """List contacts with offset pagination."""
    service = ContactService(db)
    params = PaginationParams(page=page, page_size=page_size)
    items, meta = await service.contact_repo.list_paginated(
        params=params, organization_id=user_context.organization_id
    )
    response_items = [ContactResponse.model_validate(c) for c in items]
    return APIResponse.ok(data=PaginatedResponse(items=response_items, pagination=meta))


@router.get("/{contact_id}", response_model=APIResponse[ContactResponse])
async def get_contact(
    contact_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ContactResponse]:
    """Retrieve full details of a specific contact."""
    service = ContactService(db)
    contact = await service.contact_repo.get_by_id(contact_id, organization_id=user_context.organization_id)
    if not contact:
        return APIResponse.fail(code="CONTACT_NOT_FOUND", message="Contact profile not found")
    return APIResponse.ok(data=ContactResponse.model_validate(contact))


@router.patch("/{contact_id}", response_model=APIResponse[ContactResponse])
async def update_contact(
    contact_id: UUID,
    payload: ContactUpdate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ContactResponse]:
    """Update contact attributes, lifecycle stage, or metadata."""
    service = ContactService(db)
    contact = await service.update_contact(
        user_context.organization_id, contact_id, payload, actor_id=user_context.user_id
    )
    return APIResponse.ok(data=ContactResponse.model_validate(contact))
