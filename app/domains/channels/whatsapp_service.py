"""WhatsApp Channel Service for Meta WhatsApp Cloud API integration.

Handles:
- Processing inbound webhook events from Meta WhatsApp Cloud API
- Syncing contacts and conversations to PostgreSQL
- Generating AI Agent responses with RAG knowledge grounding
- Dispatching outbound messages via Meta WhatsApp Cloud API
- Deducting credits in the ledger
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

logger = logging.getLogger("whatsapp_service")
META_GRAPH_API_VERSION = "v19.0"


async def send_whatsapp_message(
    access_token: str, phone_number_id: str, recipient_wa_id: str, text_content: str
) -> bool:
    """Send an outbound text message to a WhatsApp user via Meta WhatsApp Cloud API."""
    url = f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_wa_id,
        "type": "text",
        "text": {"preview_url": False, "body": text_content},
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code in (200, 201):
                logger.info(f"Successfully dispatched WhatsApp reply to {recipient_wa_id}")
                return True
            else:
                logger.error(f"WhatsApp Cloud API error ({resp.status_code}): {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Exception sending WhatsApp message: {e}")
            return False


async def mark_whatsapp_message_read(
    access_token: str, phone_number_id: str, message_id: str, show_typing: bool = False
) -> None:
    """Mark an inbound WhatsApp message as read (blue ticks), optionally showing the typing indicator."""
    url = f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    if show_typing:
        # Shown until we reply or for up to 25 seconds
        payload["typing_indicator"] = {"type": "text"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code not in (200, 201):
                logger.warning(f"WhatsApp read/typing update failed ({resp.status_code}): {resp.text}")
        except Exception as e:
            logger.warning(f"Failed to mark WhatsApp message {message_id} as read: {e}")


async def handle_inbound_whatsapp_event(payload: Dict[str, Any]) -> None:
    """Process an incoming webhook payload from Meta WhatsApp Cloud API."""
    if payload.get("object") != "whatsapp_business_account":
        return

    entries = payload.get("entry", [])
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            field = change.get("field")
            if field != "messages":
                continue

            value = change.get("value", {})
            metadata = value.get("metadata", {})
            phone_number_id = str(metadata.get("phone_number_id", ""))
            contacts = value.get("contacts", [])
            messages = value.get("messages", [])

            sender_name = "WhatsApp User"
            if contacts and isinstance(contacts, list):
                profile = contacts[0].get("profile", {})
                if profile.get("name"):
                    sender_name = profile.get("name")

            for msg_item in messages:
                msg_type = msg_item.get("type")
                sender_wa_id = msg_item.get("from")
                msg_id = msg_item.get("id")

                user_text = ""
                if msg_type == "text":
                    user_text = msg_item.get("text", {}).get("body", "")
                elif msg_type == "interactive":
                    interactive = msg_item.get("interactive", {})
                    user_text = (
                        interactive.get("button_reply", {}).get("title")
                        or interactive.get("list_reply", {}).get("title")
                        or "Interactive Response"
                    )
                else:
                    user_text = f"[{msg_type.upper()} message received]"

                if not sender_wa_id or not user_text:
                    continue

                if not await claim_inbound_message("whatsapp", msg_id):
                    logger.info(f"Skipping duplicate WhatsApp webhook delivery for message {msg_id}")
                    continue

                logger.info(
                    f"Received WhatsApp message from {sender_wa_id} ({sender_name}) to Phone Number ID {phone_number_id}: '{user_text}'"
                )

                await _process_whatsapp_message(
                    phone_number_id=phone_number_id,
                    sender_wa_id=sender_wa_id,
                    sender_name=sender_name,
                    user_text=user_text,
                    msg_id=msg_id,
                )


async def _process_whatsapp_message(
    phone_number_id: str,
    sender_wa_id: str,
    sender_name: str,
    user_text: str,
    msg_id: Optional[str] = None,
) -> None:
    async with admin_session_factory() as session:
        # 1. Route to the organization that owns this WhatsApp number
        ch_row = await inbound.find_channel_account(session, "whatsapp", phone_number_id)
        if not ch_row:
            logger.warning(f"No active channel account found for WhatsApp Phone Number ID {phone_number_id}")
            return

        channel_account_id = ch_row["id"]
        org_id = ch_row["organization_id"]
        creds = inbound.load_credentials(ch_row["encrypted_credentials"])
        access_token = creds.get("access_token") or creds.get("api_key_or_token") or ""
        if not access_token:
            logger.error(f"No access_token stored for WhatsApp channel account {channel_account_id}")

        # 2. Find or Create Contact by WhatsApp Phone Number (wa_id)
        q_contact = await session.execute(
            text(
                """
                SELECT id FROM contacts
                WHERE organization_id = :org_id
                  AND (phone_number = :wa_phone OR custom_attributes->>'wa_id' = :wa_id)
                LIMIT 1;
                """
            ),
            {"org_id": org_id, "wa_phone": f"+{sender_wa_id}", "wa_id": sender_wa_id},
        )
        contact_row = q_contact.mappings().first()

        if contact_row:
            contact_id = contact_row["id"]
        else:
            name_parts = sender_name.split(" ", 1)
            q_ins_contact = await session.execute(
                text(
                    """
                    INSERT INTO contacts (id, organization_id, first_name, last_name, phone_number, lifecycle_stage, custom_attributes, created_at, updated_at)
                    VALUES (gen_random_uuid(), :org_id, :first_name, :last_name, :phone, 'customer', CAST(:attrs AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id;
                    """
                ),
                {
                    "org_id": org_id,
                    "first_name": name_parts[0][:100],
                    "last_name": (name_parts[1] if len(name_parts) > 1 else "")[:100],
                    "phone": f"+{sender_wa_id}",
                    "attrs": json.dumps({"wa_id": sender_wa_id, "source": "whatsapp_cloud_api"}),
                },
            )
            contact_id = q_ins_contact.scalar_one()

        # 3. Thread the message and make it visible in the inbox right away
        conversation_id = await inbound.upsert_conversation(
            session, org_id, contact_id, channel_account_id, f"WhatsApp: {sender_name} (+{sender_wa_id})"
        )
        await inbound.save_message(session, org_id, conversation_id, "contact", user_text, "delivered", msg_id)
        await session.commit()

        # 4. A human agent owns the conversation: leave it to them
        if not await inbound.bot_should_reply(session, conversation_id):
            logger.info(f"Bot paused for WhatsApp conversation {conversation_id}: human agent is handling it")
            return

        typing_task = None
        if msg_id and access_token:
            typing_task = start_typing(
                lambda: mark_whatsapp_message_read(access_token, phone_number_id, msg_id, show_typing=True)
            )
        try:
            ai_reply, used_ai = await inbound.generate_bot_reply(session, org_id, conversation_id, user_text, "whatsapp")
        finally:
            if typing_task:
                await stop_typing(typing_task)

        # 5. Send, record and bill the reply
        sent = bool(access_token) and await send_whatsapp_message(access_token, phone_number_id, sender_wa_id, ai_reply)
        await inbound.save_message(session, org_id, conversation_id, "bot", ai_reply, "delivered" if sent else "failed")
        if used_ai:
            await inbound.charge_ai_turn(session, org_id, "WhatsApp AI Turn Inference")
        await session.commit()
        logger.info(f"Processed WhatsApp message for org {org_id} (conversation {conversation_id}, sent={sent})")
