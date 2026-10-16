"""Facebook Messenger Channel Service for Meta Graph API integration.

Handles:
- Processing inbound webhook events from Meta Messenger
- Syncing contacts and conversations to PostgreSQL
- Generating AI Agent responses with RAG knowledge grounding
- Dispatching outbound messages via Meta Graph API
"""

import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID
import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import admin_session_factory
from app.domains.channels import inbound
from app.domains.channels.dedup import claim_inbound_message
from app.domains.channels.typing import start_typing, stop_typing

logger = logging.getLogger("facebook_messenger")
META_GRAPH_API_VERSION = "v19.0"


async def send_facebook_message(page_access_token: str, recipient_psid: str, text_content: str) -> bool:
    """Send an outbound text message to a Facebook user via Meta Graph API."""
    url = f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/me/messages"
    params = {"access_token": page_access_token}
    payload = {
        "recipient": {"id": recipient_psid},
        "message": {"text": text_content},
        "messaging_type": "RESPONSE",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(url, params=params, json=payload)
            if resp.status_code == 200:
                logger.info(f"Successfully dispatched Facebook Messenger reply to PSID {recipient_psid}")
                return True
            else:
                logger.error(f"Meta Graph API error ({resp.status_code}): {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Exception sending Facebook message: {e}")
            return False


async def send_facebook_sender_action(page_access_token: str, recipient_psid: str, action: str) -> None:
    """Send a Messenger sender action: 'mark_seen', 'typing_on' or 'typing_off'."""
    url = f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/me/messages"
    params = {"access_token": page_access_token}
    payload = {"recipient": {"id": recipient_psid}, "sender_action": action}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(url, params=params, json=payload)
            if resp.status_code != 200:
                logger.warning(f"Messenger sender_action '{action}' failed ({resp.status_code}): {resp.text}")
        except Exception as e:
            logger.warning(f"Exception sending Messenger sender_action '{action}': {e}")


async def handle_inbound_facebook_event(payload: Dict[str, Any]) -> None:
    """Process an incoming webhook payload from Meta Messenger."""
    if payload.get("object") != "page":
        return

    entries = payload.get("entry", [])
    for entry in entries:
        page_id = str(entry.get("id"))
        messaging_events = entry.get("messaging", [])

        for event in messaging_events:
            sender_id = event.get("sender", {}).get("id")
            recipient_id = event.get("recipient", {}).get("id")
            message_obj = event.get("message")

            # Ignore echo messages sent by the page itself or delivery receipts
            if not message_obj or message_obj.get("is_echo") or not sender_id:
                continue

            user_text = message_obj.get("text")
            if not user_text:
                continue

            # Meta retries deliveries; process each message ID once
            if not await claim_inbound_message("messenger", message_obj.get("mid")):
                logger.info(f"Skipping duplicate Messenger webhook delivery for message {message_obj.get('mid')}")
                continue

            logger.info(f"Received Facebook message from PSID {sender_id} to Page {page_id}")

            # Process in database
            await _process_facebook_message(page_id, sender_id, user_text, message_obj.get("mid"))


async def _process_facebook_message(
    page_id: str, sender_psid: str, user_text: str, mid: Optional[str] = None
) -> None:
    async with admin_session_factory() as session:
        # 1. Route to the organization that owns this Page
        ch_row = await inbound.find_channel_account(session, "messenger", page_id)
        if not ch_row:
            logger.warning(f"No active channel account found for Facebook Page ID {page_id}")
            return

        channel_account_id = ch_row["id"]
        org_id = ch_row["organization_id"]
        creds = inbound.load_credentials(ch_row["encrypted_credentials"])
        page_access_token = creds.get("page_access_token") or creds.get("api_key_or_token") or ""
        if not page_access_token:
            logger.error(f"No page_access_token stored for Facebook channel account {channel_account_id}")

        # 2. Find or Create Contact by PSID
        q_contact = await session.execute(
            text(
                """
                SELECT id FROM contacts
                WHERE organization_id = :org_id AND is_deleted = false
                  AND custom_attributes->>'psid' = :psid
                LIMIT 1;
                """
            ),
            {"org_id": org_id, "psid": sender_psid},
        )
        contact_row = q_contact.mappings().first()

        if contact_row:
            contact_id = contact_row["id"]
        else:
            q_ins_contact = await session.execute(
                text(
                    """
                    INSERT INTO contacts (id, organization_id, first_name, last_name, lifecycle_stage, custom_attributes, created_at, updated_at)
                    VALUES (gen_random_uuid(), :org_id, 'Facebook Member', :psid, 'customer', CAST(:attrs AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id;
                    """
                ),
                {
                    "org_id": org_id,
                    "psid": sender_psid[-4:],
                    "attrs": json.dumps({"psid": sender_psid, "source": "facebook_messenger"}),
                },
            )
            contact_id = q_ins_contact.scalar_one()
            await inbound.log_contact_event(session, org_id, contact_id, "created", {"source": "messenger"})

        # 3. Thread the message and make it visible in the inbox right away
        conversation_id = await inbound.upsert_conversation(
            session, org_id, contact_id, channel_account_id, f"Messenger Chat ({user_text[:40]}...)"
        )
        await inbound.save_message(session, org_id, conversation_id, "contact", user_text, "delivered", mid)
        await session.commit()

        # 4. A human agent owns the conversation: leave it to them
        if not await inbound.bot_should_reply(session, conversation_id):
            logger.info(f"Bot paused for Messenger conversation {conversation_id}: human agent is handling it")
            return

        typing_task = None
        if page_access_token:
            await send_facebook_sender_action(page_access_token, sender_psid, "mark_seen")
            typing_task = start_typing(lambda: send_facebook_sender_action(page_access_token, sender_psid, "typing_on"))
        try:
            ai_reply, used_ai = await inbound.generate_bot_reply(session, org_id, conversation_id, user_text, "messenger")
        finally:
            if typing_task:
                await stop_typing(typing_task)

        # 5. Send, record and bill the reply
        sent = bool(page_access_token) and await send_facebook_message(page_access_token, sender_psid, ai_reply)
        await inbound.save_message(session, org_id, conversation_id, "bot", ai_reply, "delivered" if sent else "failed")
        if used_ai:
            await inbound.charge_ai_turn(session, org_id, "Messenger AI Turn Inference")
        await session.commit()
        logger.info(f"Processed Messenger message for org {org_id} (conversation {conversation_id}, sent={sent})")
