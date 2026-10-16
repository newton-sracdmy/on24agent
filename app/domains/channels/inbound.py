"""Shared inbound-message pipeline for WhatsApp, Messenger and Instagram.

Each channel service resolves its own contact identity and does its own sending; everything
else (routing to the right organization, threading, the AI reply, human handoff and billing)
lives here so the three channels behave identically.
"""

import json
import logging
from typing import Any, Mapping, Optional, Tuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.security import decrypt_secret

logger = logging.getLogger("channel_inbound")

# Number of earlier turns sent to the model as conversation context
HISTORY_TURNS = 6
# Placeholder identifier an Instagram account gets when connected without its account ID
INSTAGRAM_PLACEHOLDER = "instagram_default"

FALLBACK_REPLY = (
    "Thanks for your message! We've received it and our team will get back to you shortly."
)


async def find_channel_account(
    session: AsyncSession, channel_type: str, account_identifier: str
) -> Optional[Mapping[str, Any]]:
    """Return the active channel account that owns this identifier, or None.

    Matches the channel type and identifier exactly, so a message is never routed to another
    organization's account.
    """
    if not account_identifier:
        return None
    res = await session.execute(
        text(
            """
            SELECT ca.id, ca.organization_id, ca.encrypted_credentials, ca.account_identifier
            FROM channel_accounts ca
            JOIN channels ch ON ch.id = ca.channel_id
            WHERE ch.type = :type AND ca.account_identifier = :ident AND ca.is_deleted = false
            ORDER BY ca.updated_at DESC
            LIMIT 1;
            """
        ),
        {"type": channel_type, "ident": account_identifier},
    )
    row = res.mappings().first()
    if row or channel_type != "instagram":
        return row

    # An Instagram account connected without its ID is bound on first message, but only when
    # exactly one such placeholder exists, otherwise the owner would be a guess
    res = await session.execute(
        text(
            """
            SELECT ca.id, ca.organization_id, ca.encrypted_credentials, ca.account_identifier
            FROM channel_accounts ca
            JOIN channels ch ON ch.id = ca.channel_id
            WHERE ch.type = 'instagram' AND ca.account_identifier = :placeholder AND ca.is_deleted = false
            LIMIT 2;
            """
        ),
        {"placeholder": INSTAGRAM_PLACEHOLDER},
    )
    rows = res.mappings().all()
    if len(rows) != 1:
        return None
    await session.execute(
        text("UPDATE channel_accounts SET account_identifier = :ident, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
        {"ident": account_identifier, "id": rows[0]["id"]},
    )
    return {**rows[0], "account_identifier": account_identifier}


def load_credentials(encrypted: Optional[str]) -> dict:
    if not encrypted:
        return {}
    try:
        return json.loads(decrypt_secret(encrypted) or "{}")
    except Exception as e:
        logger.error(f"Could not decrypt channel credentials: {e}")
        return {}


async def log_contact_event(
    session: AsyncSession, org_id: UUID, contact_id: UUID, event_type: str, data: Optional[dict] = None
) -> None:
    """Append a system event to the contact's CRM timeline."""
    await session.execute(
        text(
            """
            INSERT INTO contact_events (id, organization_id, contact_id, event_type, actor_type, event_data, created_at, updated_at)
            VALUES (gen_random_uuid(), :org_id, :cid, :type, 'system', CAST(:data AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            """
        ),
        {"org_id": org_id, "cid": contact_id, "type": event_type, "data": json.dumps(data or {})},
    )


async def upsert_conversation(
    session: AsyncSession, org_id: UUID, contact_id: UUID, channel_account_id: UUID, subject: str
) -> UUID:
    """Append to the contact's open thread on this channel, reopening it if it was resolved."""
    res = await session.execute(
        text(
            """
            SELECT id FROM conversations
            WHERE organization_id = :org_id AND contact_id = :cid AND channel_account_id = :chid
              AND status <> 'closed' AND is_deleted = false
            ORDER BY last_message_at DESC LIMIT 1;
            """
        ),
        {"org_id": org_id, "cid": contact_id, "chid": channel_account_id},
    )
    row = res.mappings().first()
    if row:
        await session.execute(
            text(
                """
                UPDATE conversations
                SET last_message_at = CURRENT_TIMESTAMP,
                    service_window_expires_at = CURRENT_TIMESTAMP + INTERVAL '24 hours',
                    unread_count = unread_count + 1,
                    status = CASE WHEN status IN ('resolved', 'snoozed') THEN 'open' ELSE status END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id;
                """
            ),
            {"id": row["id"]},
        )
        return row["id"]

    res = await session.execute(
        text(
            """
            INSERT INTO conversations (id, organization_id, contact_id, channel_account_id, status, priority, subject,
                                       service_window_expires_at, unread_count, last_message_at, created_at, updated_at)
            VALUES (gen_random_uuid(), :org_id, :cid, :chid, 'open', 'medium', :subject,
                    CURRENT_TIMESTAMP + INTERVAL '24 hours', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id;
            """
        ),
        {"org_id": org_id, "cid": contact_id, "chid": channel_account_id, "subject": subject[:255]},
    )
    conversation_id = res.scalar_one()
    await log_contact_event(session, org_id, contact_id, "conversation_started", {"conversation_id": str(conversation_id)})
    return conversation_id


async def save_message(
    session: AsyncSession,
    org_id: UUID,
    conversation_id: UUID,
    sender_type: str,
    content: str,
    delivery_status: str,
    external_id: Optional[str] = None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO messages (id, organization_id, conversation_id, sender_type, content_type, text_content,
                                  delivery_status, external_id, created_at, updated_at)
            VALUES (gen_random_uuid(), :org_id, :conv_id, :sender, 'text', :content, :status, :ext,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            """
        ),
        {"org_id": org_id, "conv_id": conversation_id, "sender": sender_type, "content": content,
         "status": delivery_status, "ext": external_id},
    )


async def bot_should_reply(session: AsyncSession, conversation_id: UUID) -> bool:
    """False for blocked contacts, and once a human agent has replied since the conversation
    was last resolved. Resolving the conversation hands it back to the bot.
    """
    res = await session.execute(
        text(
            """
            SELECT NOT EXISTS (
                SELECT 1 FROM messages m JOIN conversations c ON c.id = m.conversation_id
                WHERE m.conversation_id = :conv_id AND m.sender_type = 'agent'
                  AND m.created_at > COALESCE(c.resolved_at, '-infinity'::timestamptz)
            ) AND NOT EXISTS (
                SELECT 1 FROM conversations c JOIN contacts ct ON ct.id = c.contact_id
                WHERE c.id = :conv_id AND ct.is_blocked
            );
            """
        ),
        {"conv_id": conversation_id},
    )
    return bool(res.scalar())


async def generate_bot_reply(
    session: AsyncSession, org_id: UUID, conversation_id: UUID, user_text: str, gap_channel: str
) -> Tuple[str, bool]:
    """Build the bot's reply to `user_text`. Returns (reply, generated_by_ai)."""
    from app.domains.agents.service import AgentService
    from app.domains.ai.gemini_service import generate_grounded_reply
    from app.domains.rag.service import RAGService

    retrieval = await RAGService.retrieve_context(session, org_id, user_text)

    # The most recent earlier turns, oldest first; the current message is sent separately
    res = await session.execute(
        text(
            """
            SELECT sender_type, text_content FROM (
                SELECT sender_type, text_content, created_at FROM messages
                WHERE conversation_id = :conv_id AND text_content IS NOT NULL
                ORDER BY created_at DESC
                OFFSET 1 LIMIT :n
            ) recent ORDER BY created_at ASC;
            """
        ),
        {"conv_id": conversation_id, "n": HISTORY_TURNS},
    )
    chat_history = [dict(r) for r in res.mappings().all()]

    system_prompt = await AgentService.get_active_system_prompt(session, org_id)
    ai_reply, kb_covered = await generate_grounded_reply(
        user_query=user_text,
        system_prompt=system_prompt,
        kb_context=retrieval.as_context(),
        chat_history=chat_history,
    )

    if RAGService.should_record_gap(user_text, kb_covered, retrieval):
        try:
            async with session.begin_nested():
                await RAGService.record_knowledge_gap(session, org_id, user_text, channel=gap_channel)
        except Exception as e:
            logger.warning(f"Failed to record knowledge gap: {e}")

    if ai_reply:
        return ai_reply, True

    # Model unavailable: quote the closest knowledge base passage, else acknowledge receipt
    if retrieval.chunks and (retrieval.top_score is None or retrieval.top_score >= 0.6):
        return retrieval.chunks[0]["content_text"], False
    return FALLBACK_REPLY, False


async def charge_ai_turn(session: AsyncSession, org_id: UUID, description: str) -> None:
    """Deduct one credit for an AI-generated reply and record it in the ledger."""
    res = await session.execute(
        text(
            """
            UPDATE credit_balances
            SET balance_credits = balance_credits - 1.0,
                lifetime_consumed_credits = lifetime_consumed_credits + 1.0
            WHERE organization_id = :org_id
            RETURNING balance_credits;
            """
        ),
        {"org_id": org_id},
    )
    balance = res.scalar()
    if balance is None:
        logger.warning(f"Organization {org_id} has no credit balance row; AI turn not billed")
        return
    await session.execute(
        text(
            """
            INSERT INTO credit_ledger (id, organization_id, transaction_type, amount, balance_after, description,
                                       created_at, updated_at)
            VALUES (gen_random_uuid(), :org_id, 'usage_deduction', -1.0, :balance, :description,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            """
        ),
        {"org_id": org_id, "balance": balance, "description": description},
    )
