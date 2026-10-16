"""Instagram Direct Messaging Channel Service for Meta Graph API integration.

Handles:
- Processing inbound webhook events from Instagram Messaging (Meta Graph API)
- Syncing contacts and conversations to PostgreSQL
- Generating AI Agent responses with RAG knowledge grounding
- Dispatching outbound messages via Meta Graph API for Instagram
- Credit ledger usage tracking
"""

import json
import logging
from typing import Any, Dict, Optional
import httpx
from sqlalchemy import text

from app.database import admin_session_factory
from app.domains.channels import inbound
from app.domains.channels.dedup import claim_inbound_message
from app.domains.channels.typing import start_typing, stop_typing

logger = logging.getLogger("instagram_messaging")
META_GRAPH_API_VERSION = "v19.0"


def _instagram_messages_url(access_token: str, sender_account_id: Optional[str] = None) -> str:
    # Instagram Login tokens (IGAA…/IGQ…) use graph.instagram.com; Page tokens use graph.facebook.com
    if access_token.startswith("IGAA") or access_token.startswith("IGQ"):
        return f"https://graph.instagram.com/{META_GRAPH_API_VERSION}/me/messages"
    return f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/{sender_account_id or 'me'}/messages"


async def send_instagram_sender_action(
    access_token: str, recipient_igsid: str, action: str, sender_account_id: Optional[str] = None
) -> None:
    """Send an Instagram sender action: 'mark_seen', 'typing_on' or 'typing_off'."""
    url = _instagram_messages_url(access_token, sender_account_id)
    params = {"access_token": access_token}
    payload = {"recipient": {"id": recipient_igsid}, "sender_action": action}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(url, params=params, json=payload)
            if resp.status_code != 200:
                logger.warning(f"Instagram sender_action '{action}' failed ({resp.status_code}): {resp.text}")
        except Exception as e:
            logger.warning(f"Exception sending Instagram sender_action '{action}': {e}")


async def send_instagram_message(
    access_token: str,
    recipient_igsid: str,
    text_content: str,
    sender_account_id: Optional[str] = None,
) -> bool:
    """Send an outbound text message to an Instagram user via Meta Graph API."""
    url = _instagram_messages_url(access_token, sender_account_id)
    params = {"access_token": access_token}
    payload = {
        "recipient": {"id": recipient_igsid},
        "message": {"text": text_content},
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(url, params=params, json=payload)
            if resp.status_code == 200:
                logger.info(f"Successfully dispatched Instagram DM to IGSID {recipient_igsid}")
                return True
            else:
                logger.error(f"Meta Instagram API error ({resp.status_code}): {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Exception sending Instagram DM: {e}")
            return False


async def handle_inbound_instagram_event(payload: Dict[str, Any]) -> None:
    """Process an incoming webhook payload from Meta Instagram Messaging."""
    logger.debug(f"Incoming Instagram webhook payload: {json.dumps(payload)}")
    if payload.get("object") not in ("instagram", "page"):
        return

    entries = payload.get("entry", [])
    for entry in entries:
        account_id = str(entry.get("id"))
        messaging_events = entry.get("messaging", [])

        for event in messaging_events:
            sender_id = event.get("sender", {}).get("id")
            message_obj = event.get("message")

            # Ignore echoes sent by the account itself or read receipts
            if not message_obj or message_obj.get("is_echo") or not sender_id:
                continue

            user_text = message_obj.get("text")
            if not user_text:
                continue

            # Meta retries deliveries; process each message ID once
            if not await claim_inbound_message("instagram", message_obj.get("mid")):
                logger.info(f"Skipping duplicate Instagram webhook delivery for message {message_obj.get('mid')}")
                continue

            logger.info(f"Received Instagram message from IGSID {sender_id} to Account {account_id}")

            await _process_instagram_message(account_id, sender_id, user_text, message_obj.get("mid"))


async def _process_instagram_message(
    account_id: str, sender_igsid: str, user_text: str, mid: Optional[str] = None
) -> None:
    async with admin_session_factory() as session:
        # 1. Route to the organization that owns this Instagram account
        ch_row = await inbound.find_channel_account(session, "instagram", account_id)
        if not ch_row:
            logger.warning(f"No active channel account found for Instagram Account ID {account_id}")
            return

        channel_account_id = ch_row["id"]
        org_id = ch_row["organization_id"]
        creds = inbound.load_credentials(ch_row["encrypted_credentials"])
        access_token = creds.get("access_token") or creds.get("page_access_token") or creds.get("api_key_or_token") or ""
        if not access_token:
            logger.error(f"No access_token stored for Instagram channel account {channel_account_id}")

        # 2. Find or Create Contact by IGSID
        q_contact = await session.execute(
            text(
                """
                SELECT id FROM contacts
                WHERE organization_id = :org_id AND is_deleted = false
                  AND custom_attributes->>'igsid' = :igsid
                LIMIT 1;
                """
            ),
            {"org_id": org_id, "igsid": sender_igsid},
        )
        contact_row = q_contact.mappings().first()

        if contact_row:
            contact_id = contact_row["id"]
        else:
            q_ins_contact = await session.execute(
                text(
                    """
                    INSERT INTO contacts (id, organization_id, first_name, last_name, lifecycle_stage, custom_attributes, created_at, updated_at)
                    VALUES (gen_random_uuid(), :org_id, 'Instagram User', :igsid_suffix, 'customer', CAST(:attrs AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id;
                    """
                ),
                {
                    "org_id": org_id,
                    "igsid_suffix": sender_igsid[-4:] if len(sender_igsid) >= 4 else sender_igsid,
                    "attrs": json.dumps({"igsid": sender_igsid, "source": "instagram_direct"}),
                },
            )
            contact_id = q_ins_contact.scalar_one()
            await inbound.log_contact_event(session, org_id, contact_id, "created", {"source": "instagram"})

        # 3. Thread the message and make it visible in the inbox right away
        conversation_id = await inbound.upsert_conversation(
            session, org_id, contact_id, channel_account_id, f"Instagram DM ({user_text[:40]}...)"
        )
        await inbound.save_message(session, org_id, conversation_id, "contact", user_text, "delivered", mid)
        await session.commit()

        # 4. A human agent owns the conversation: leave it to them
        if not await inbound.bot_should_reply(session, conversation_id):
            logger.info(f"Bot paused for Instagram conversation {conversation_id}: human agent is handling it")
            return

        typing_task = None
        if access_token:
            await send_instagram_sender_action(access_token, sender_igsid, "mark_seen", account_id)
            typing_task = start_typing(
                lambda: send_instagram_sender_action(access_token, sender_igsid, "typing_on", account_id)
            )
        try:
            ai_reply, used_ai = await inbound.generate_bot_reply(session, org_id, conversation_id, user_text, "instagram")
        finally:
            if typing_task:
                await stop_typing(typing_task)

        # 5. Send, record and bill the reply
        sent = bool(access_token) and await send_instagram_message(
            access_token, sender_igsid, ai_reply, sender_account_id=account_id
        )
        await inbound.save_message(session, org_id, conversation_id, "bot", ai_reply, "delivered" if sent else "failed")
        if used_ai:
            await inbound.charge_ai_turn(session, org_id, "Instagram AI Turn Inference")
        await session.commit()
        logger.info(f"Processed Instagram message for org {org_id} (conversation {conversation_id}, sent={sent})")
