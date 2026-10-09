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
from app.security import decrypt_secret

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

            logger.info(f"Received Facebook message from PSID {sender_id} to Page {page_id}: '{user_text}'")

            # Process in database
            await _process_facebook_message(page_id, sender_id, user_text)


async def _process_facebook_message(page_id: str, sender_psid: str, user_text: str) -> None:
    async with admin_session_factory() as session:
        # 1. Find Channel Account by page_id
        q_channel = await session.execute(
            text("SELECT id, organization_id, encrypted_credentials FROM channel_accounts WHERE account_identifier = :page_id AND is_deleted = false LIMIT 1;"),
            {"page_id": page_id},
        )
        ch_row = q_channel.mappings().first()
        if not ch_row:
            logger.warning(f"No active channel account found for Facebook Page ID {page_id}")
            return

        channel_account_id = ch_row["id"]
        org_id = ch_row["organization_id"]

        # Decrypt Page Access Token
        creds_json = decrypt_secret(ch_row["encrypted_credentials"])
        page_access_token = json.loads(creds_json).get("page_access_token", "") if creds_json else ""
        if not page_access_token:
            from app.config import settings
            page_access_token = settings.FB_PAGE_ACCESS_TOKEN or ""

        # Set RLS Context
        await session.execute(text(f"SELECT set_config('app.current_org_id', '{org_id}', true);"))

        # 2. Find or Create Contact by PSID
        q_contact = await session.execute(
            text(
                """
                SELECT id FROM contacts 
                WHERE organization_id = :org_id 
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
                    "subject": f"Messenger Chat ({user_text[:40]}...)",
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

        # 5. Fetch RAG Knowledge Chunks & Generate AI Answer via Google Gemini
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
        kb_context = "\n\n".join([f"[{r['title']}]: {r['content_text']}" for r in chunk_rows])

        # Fetch recent conversation turns
        q_hist = await session.execute(
            text(
                """
                SELECT sender_type, text_content
                FROM messages
                WHERE conversation_id = :conv_id
                ORDER BY created_at ASC
                LIMIT 6;
                """
            ),
            {"conv_id": conversation_id},
        )
        chat_hist = [dict(r) for r in q_hist.mappings().all()]

        system_prompt = (
            "You are the official 24/7 AI Community Operations Specialist for TechVibe Members Club. "
            "You assist community members with guidelines, VIP membership, events, bootcamps, and technical questions. "
            "Be enthusiastic, polite, and clear. Format cleanly for Facebook Messenger with emojis and bullet points."
        )

        from app.domains.ai.gemini_service import generate_gemini_response
        ai_reply = await generate_gemini_response(
            user_query=user_text,
            system_prompt=system_prompt,
            kb_context=kb_context,
            chat_history=chat_hist,
        )

        # Fallback to extractive heuristic RAG matcher if Gemini is unavailable
        if not ai_reply:
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

            if best_chunk and best_score >= 1:
                if "rule" in lower_q or "guideline" in lower_q or "নিয়ম" in lower_q:
                    ai_reply = f"Welcome to TechVibe Members Club! Our community guidelines:\n{best_chunk}"
                else:
                    ai_reply = f"According to TechVibe official guidelines:\n\n{best_chunk}\n\nFeel free to ask if you have more questions!"
            elif "join" in lower_q or "group" in lower_q or "মেম্বার" in lower_q or "যুক্ত" in lower_q:
                ai_reply = "Welcome to TechVibe! You can participate in all member discussions right here and inside our Facebook Group. Feel free to ask any tech or development questions anytime!"
            elif "event" in lower_q or "session" in lower_q or "সময়" in lower_q or "friday" in lower_q:
                ai_reply = "Our weekly live AI & tech sessions are hosted every Friday at 8:00 PM (GMT+6) in our community group. Don't miss it!"
            else:
                ai_reply = f"Hello from TechVibe AI Assistant! Thanks for reaching out. We are glad to have you in TechVibe Members Club. How can I assist your tech journey today?"

        # 6. Dispatch AI Reply via Meta Graph API
        if page_access_token:
            sent = await send_facebook_message(page_access_token, sender_psid, ai_reply)
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
                VALUES (gen_random_uuid(), :org_id, 'usage_deduction', -1.0, (SELECT balance_credits FROM credit_balances WHERE organization_id = :org_id), 'Messenger AI Turn Inference', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
                """
            ),
            {"org_id": org_id},
        )

        await session.commit()
        logger.info(f"Processed Messenger interaction for TechVibe. AI reply sent: '{ai_reply}'")
