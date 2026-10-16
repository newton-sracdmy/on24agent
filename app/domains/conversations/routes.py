"""FastAPI router endpoints for Unified Inbox, Messaging, and Conversation resolution."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common import llm_rate_limit
from app.common.schemas import APIResponse, PaginatedResponse
from app.constants import ConversationStatus, MessageSenderType
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
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[ConversationResponse]:
    """Start an outbound customer conversation thread."""
    service = ConversationService(db)
    conv = await service.create_conversation(user_context.organization_id, payload)
    return APIResponse.ok(data=(await service.to_responses([conv]))[0])


@router.get("/", response_model=APIResponse[PaginatedResponse[ConversationResponse]])
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[ConversationStatus] = Query(None, alias="status"),
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[PaginatedResponse[ConversationResponse]]:
    """List omnichannel conversation inbox feeds, most recent activity first."""
    service = ConversationService(db)
    items, meta = await service.list_conversations(
        user_context.organization_id, page, page_size,
        status=status_filter.value if status_filter else None,
    )
    return APIResponse.ok(data=PaginatedResponse(items=await service.to_responses(items), pagination=meta))


@router.get("/{conversation_id}", response_model=APIResponse[ConversationResponse])
async def get_conversation(
    conversation_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[ConversationResponse]:
    """Retrieve full conversation details and status."""
    service = ConversationService(db)
    conv = await service.get_owned(user_context.organization_id, conversation_id)
    return APIResponse.ok(data=(await service.to_responses([conv]))[0])


@router.patch("/{conversation_id}", response_model=APIResponse[ConversationResponse])
async def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[ConversationResponse]:
    """Change status, priority, assignee or team."""
    service = ConversationService(db)
    conv = await service.update_conversation(user_context.organization_id, conversation_id, payload)
    return APIResponse.ok(data=(await service.to_responses([conv]))[0])


@router.post("/{conversation_id}/read", response_model=APIResponse[ConversationResponse])
async def mark_conversation_read(
    conversation_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[ConversationResponse]:
    """Clear the unread counter once an agent has opened the conversation."""
    service = ConversationService(db)
    conv = await service.mark_read(user_context.organization_id, conversation_id)
    return APIResponse.ok(data=(await service.to_responses([conv]))[0])


@router.post("/{conversation_id}/suggest-reply", response_model=APIResponse[dict])
async def suggest_reply(
    conversation_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[dict]:
    """AI-draft a reply to the customer's latest message for the agent to review and send."""
    await llm_rate_limit.ensure_llm_call_allowed(user_context.organization_id, "reply_suggest")
    service = ConversationService(db)
    draft = await service.suggest_reply(user_context.organization_id, conversation_id)
    return APIResponse.ok(data={"suggested_reply": draft})


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED, response_model=APIResponse[MessageResponse])
async def send_message(
    conversation_id: UUID,
    payload: MessageCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[MessageResponse]:
    """Send an outbound message from an agent to the customer.

    The message is always stored; delivery_status is "failed" (with payload_json.delivery_error)
    when the channel could not deliver it. A human reply also pauses the AI bot for this
    conversation until it is resolved.
    """
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
    before: Optional[UUID] = Query(None, description="Return messages older than this message ID"),
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[List[MessageResponse]]:
    """The latest messages of a conversation, oldest first; page back with ?before=<oldest id>."""
    service = ConversationService(db)
    await service.get_owned(user_context.organization_id, conversation_id)
    messages = await service.msg_repo.list_by_conversation(
        conversation_id, user_context.organization_id, limit=limit, before_id=before
    )
    return APIResponse.ok(data=[MessageResponse.model_validate(m) for m in messages])


@router.post("/{conversation_id}/resolve", response_model=APIResponse[ConversationResponse])
async def resolve_conversation(
    conversation_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[ConversationResponse]:
    """Resolve a conversation and trigger post-chat CSAT feedback survey."""
    service = ConversationService(db)
    conv = await service.resolve_conversation(user_context.organization_id, conversation_id)
    return APIResponse.ok(data=(await service.to_responses([conv]))[0])
