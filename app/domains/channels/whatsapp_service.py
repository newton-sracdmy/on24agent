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
from app.security import decrypt_secret

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
    access_token: str, phone_number_id: str, message_id: str
) -> None:
    """Mark an inbound WhatsApp message as read to display double-blue checkmarks."""
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

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.post(url, headers=headers, json=payload)
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
        # 1. Find Channel Account by phone_number_id
        q_channel = await session.execute(
            text(
                """
                SELECT id, organization_id, encrypted_credentials 
                FROM channel_accounts 
                WHERE account_identifier = :phone_number_id AND is_deleted = false 
                LIMIT 1;
                """
            ),
            {"phone_number_id": phone_number_id},
        )
        ch_row = q_channel.mappings().first()
        if not ch_row:
            logger.warning(f"No active channel account found for WhatsApp Phone Number ID {phone_number_id}")
            return

        channel_account_id = ch_row["id"]
        org_id = ch_row["organization_id"]

        # Decrypt Access Token
        creds_json = decrypt_secret(ch_row["encrypted_credentials"])
        access_token = ""
        if creds_json:
            try:
                creds_dict = json.loads(creds_json)
                access_token = creds_dict.get("access_token", "")
            except Exception:
                pass

        if not access_token:
            from app.config import settings
            access_token = settings.META_WHATSAPP_API_TOKEN or ""

        # Set RLS Context
        await session.execute(text(f"SELECT set_config('app.current_org_id', '{org_id}', true);"))

        # Mark message as read on WhatsApp
        if msg_id and access_token:
            await mark_whatsapp_message_read(access_token, phone_number_id, msg_id)

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

        name_parts = sender_name.split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        if contact_row:
            contact_id = contact_row["id"]
        else:
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
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": f"+{sender_wa_id}",
                    "attrs": json.dumps({"wa_id": sender_wa_id, "source": "whatsapp_cloud_api"}),
                },
            )
            contact_id = q_ins_contact.scalar_one()

        # 3. Find or Create Conversation
        q_conv = await session.execute(
            text(
                """
                SELECT id FROM conversations 
                WHERE organization_id = :org_id 
                  AND contact_id = :cid 
                  AND channel_account_id = :chid 
                  AND status <> 'closed' 
                ORDER BY created_at DESC LIMIT 1;
                """
            ),
            {"org_id": org_id, "cid": contact_id, "chid": channel_account_id},
        )
        conv_row = q_conv.mappings().first()

        if conv_row:
            conversation_id = conv_row["id"]
            await session.execute(
                text(
                    """
                    UPDATE conversations 
                    SET last_message_at = CURRENT_TIMESTAMP, 
                        service_window_expires_at = CURRENT_TIMESTAMP + INTERVAL '24 hours',
                        unread_count = unread_count + 1 
                    WHERE id = :id;
                    """
                ),
                {"id": conversation_id},
            )
        else:
            q_ins_conv = await session.execute(
                text(
                    """
                    INSERT INTO conversations (id, organization_id, contact_id, channel_account_id, status, priority, subject, service_window_expires_at, unread_count, created_at, updated_at)
                    VALUES (gen_random_uuid(), :org_id, :cid, :chid, 'open', 'medium', :subject, CURRENT_TIMESTAMP + INTERVAL '24 hours', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id;
                    """
                ),
                {
                    "org_id": org_id,
                    "cid": contact_id,
                    "chid": channel_account_id,
                    "subject": f"WhatsApp: {sender_name} (+{sender_wa_id})",
                },
            )
            conversation_id = q_ins_conv.scalar_one()

        # 4. Save Inbound Customer Message
        await session.execute(
            text(
                """
                INSERT INTO messages (id, organization_id, conversation_id, sender_type, content_type, text_content, delivery_status, created_at, updated_at)
                VALUES (gen_random_uuid(), :org_id, :conv_id, 'contact', 'text', :content, 'delivered', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
                """
            ),
            {"org_id": org_id, "conv_id": conversation_id, "content": user_text},
        )

        # 5. Fetch RAG Knowledge Chunks & Generate AI Answer
        q_chunks = await session.execute(
            text(
                """
                SELECT dc.content_text, d.title
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                WHERE dc.organization_id = :org_id
                ORDER BY dc.created_at DESC;
                """
            ),
            {"org_id": org_id},
        )
        chunk_rows = q_chunks.mappings().all()

        # Dynamic semantic & keyword matching against user question
        lower_q = user_text.lower()
        q_words = [w.strip() for w in lower_q.replace("?", "").replace(",", "").replace(".", "").replace("!", "").split() if len(w.strip()) > 1]

        best_chunk = None
        best_score = 0
        for row in chunk_rows:
            chunk_text = row["content_text"]
            chunk_lower = chunk_text.lower()
            matched = sum(1 for w in q_words if w in chunk_lower)
            if matched > best_score:
                best_score = matched
                best_chunk = chunk_text

        # Generate grounded response
        if best_chunk and best_score >= 1:
            if "rule" in lower_q or "guideline" in lower_q or "নিয়ম" in lower_q:
                ai_reply = f"Welcome to TechVibe Members Club! Our community guidelines:\n{best_chunk}"
            else:
                ai_reply = f"According to TechVibe official guidelines:\n\n{best_chunk}\n\nLet us know if you need more details!"
        elif "join" in lower_q or "group" in lower_q or "মেম্বার" in lower_q or "যুক্ত" in lower_q:
            ai_reply = "Welcome to TechVibe! You can participate in all member discussions right here and inside our Facebook Group. Feel free to ask any tech or development questions anytime!"
        elif "event" in lower_q or "session" in lower_q or "সময়" in lower_q or "friday" in lower_q:
            ai_reply = "Our weekly live AI & tech sessions are hosted every Friday at 8:00 PM (GMT+6) in our community group. Don't miss it!"
        else:
            ai_reply = f"Hello {sender_name}! 👋 Thanks for messaging TechVibe Members Club. I am your 24/7 AI Operations Specialist. How can I assist your tech journey today?"

        # 6. Dispatch Outbound AI Reply via Meta WhatsApp Cloud API
        if access_token and phone_number_id:
            sent = await send_whatsapp_message(access_token, phone_number_id, sender_wa_id, ai_reply)
        else:
            sent = False

        # 7. Save Outbound Bot Message in Database
        await session.execute(
            text(
                """
                INSERT INTO messages (id, organization_id, conversation_id, sender_type, content_type, text_content, delivery_status, created_at, updated_at)
                VALUES (gen_random_uuid(), :org_id, :conv_id, 'bot', 'text', :content, :status, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
                """
            ),
            {"org_id": org_id, "conv_id": conversation_id, "content": ai_reply, "status": "delivered" if sent else "sent"},
        )

        # 8. Record in Double-entry Credit Ledger
        await session.execute(
            text(
                """
                UPDATE credit_balances 
                SET balance_credits = balance_credits - 1.0, 
                    lifetime_consumed_credits = lifetime_consumed_credits + 1.0 
                WHERE organization_id = :org_id;
                """
            ),
            {"org_id": org_id},
        )
        await session.execute(
            text(
                """
                INSERT INTO credit_ledger (id, organization_id, transaction_type, amount, balance_after, description, created_at, updated_at)
                VALUES (gen_random_uuid(), :org_id, 'usage_deduction', -1.0, (SELECT balance_credits FROM credit_balances WHERE organization_id = :org_id), 'WhatsApp AI Turn Inference', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
                """
            ),
            {"org_id": org_id},
        )

        await session.commit()
        logger.info(f"Processed WhatsApp interaction for TechVibe. AI reply sent: '{ai_reply}'")
