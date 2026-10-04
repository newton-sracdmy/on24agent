"""FastAPI router endpoints for Unified Inbox, Messaging, and Conversation resolution."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams
from app.common.schemas import APIResponse, PaginatedResponse
from app.constants import MessageSenderType
from app.dependencies import AuthenticatedUserContext, get_db, require_tenant
from app.domains.conversations.schemas import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
)
from app.domains.conversations.service import ConversationService

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=APIResponse[ConversationResponse])
async def create_conversation(
    payload: ConversationCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ConversationResponse]:
    """Start an outbound customer conversation thread."""
    service = ConversationService(db)
    conv = await service.create_conversation(user_context.organization_id, payload)
    return APIResponse.ok(data=ConversationResponse.model_validate(conv))


@router.get("/", response_model=APIResponse[PaginatedResponse[ConversationResponse]])
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[PaginatedResponse[ConversationResponse]]:
    """List omnichannel conversation inbox feeds."""
    service = ConversationService(db)
    params = PaginationParams(page=page, page_size=page_size)
    items, meta = await service.conv_repo.list_paginated(
        params=params, organization_id=user_context.organization_id
    )
    response_items = [ConversationResponse.model_validate(c) for c in items]
    return APIResponse.ok(data=PaginatedResponse(items=response_items, pagination=meta))


@router.get("/{conversation_id}", response_model=APIResponse[ConversationResponse])
async def get_conversation(
    conversation_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ConversationResponse]:
    """Retrieve full conversation details and status."""
    service = ConversationService(db)
    conv = await service.conv_repo.get_by_id(conversation_id, organization_id=user_context.organization_id)
    if not conv:
        return APIResponse.fail(code="CONVERSATION_NOT_FOUND", message="Conversation not found")
    return APIResponse.ok(data=ConversationResponse.model_validate(conv))


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED, response_model=APIResponse[MessageResponse])
async def send_message(
    conversation_id: UUID,
    payload: MessageCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[MessageResponse]:
    """Send an outbound message from an agent to the customer."""
    service = ConversationService(db)
    msg = await service.post_message(
        org_id=user_context.organization_id,
        conversation_id=conversation_id,
        data=payload,
        sender_type=MessageSenderType.AGENT,
        sender_id=user_context.user_id,
    )
    return APIResponse.ok(data=MessageResponse.model_validate(msg))


@router.get("/{conversation_id}/messages", response_model=APIResponse[List[MessageResponse]])
async def list_messages(
    conversation_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[List[MessageResponse]]:
    """List message history within a conversation."""
    service = ConversationService(db)
    messages = await service.msg_repo.list_by_conversation(conversation_id, limit=limit)
    response_msgs = [MessageResponse.model_validate(m) for m in messages]
    return APIResponse.ok(data=response_msgs)


@router.post("/{conversation_id}/resolve", response_model=APIResponse[ConversationResponse])
async def resolve_conversation(
    conversation_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ConversationResponse]:
    """Resolve a conversation and trigger post-chat CSAT feedback survey."""
    service = ConversationService(db)
    conv = await service.resolve_conversation(user_context.organization_id, conversation_id)
    return APIResponse.ok(data=ConversationResponse.model_validate(conv))
