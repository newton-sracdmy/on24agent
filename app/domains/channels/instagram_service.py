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
from app.security import decrypt_secret

logger = logging.getLogger("instagram_messaging")
META_GRAPH_API_VERSION = "v19.0"


async def send_instagram_message(access_token: str, recipient_igsid: str, text_content: str) -> bool:
    """Send an outbound text message to an Instagram user via Meta Graph API."""
    url = f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/me/messages"
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
    if payload.get("object") != "instagram":
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

            logger.info(f"Received Instagram message from IGSID {sender_id} to Account {account_id}: '{user_text}'")

            await _process_instagram_message(account_id, sender_id, user_text)


async def _process_instagram_message(account_id: str, sender_igsid: str, user_text: str) -> None:
    async with admin_session_factory() as session:
        # 1. Find Channel Account by account_identifier or channel type 'instagram'
        q_channel = await session.execute(
            text(
                """
                SELECT ca.id, ca.organization_id, ca.encrypted_credentials 
                FROM channel_accounts ca
                JOIN channels ch ON ch.id = ca.channel_id
                WHERE (ca.account_identifier = :acc_id OR ch.type = 'instagram')
                  AND ca.is_deleted = false 
                LIMIT 1;
                """
            ),
            {"acc_id": account_id},
        )
        ch_row = q_channel.mappings().first()
        if not ch_row:
            logger.warning(f"No active channel account found for Instagram Account ID {account_id}")
            return

        channel_account_id = ch_row["id"]
        org_id = ch_row["organization_id"]

        # Decrypt Access Token
        creds_json = decrypt_secret(ch_row["encrypted_credentials"]) if ch_row["encrypted_credentials"] else ""
        access_token = ""
        if creds_json:
            try:
                creds_dict = json.loads(creds_json)
                access_token = creds_dict.get("access_token") or creds_dict.get("page_access_token") or ""
            except Exception:
                pass

        if not access_token:
            from app.config import settings
            access_token = settings.META_WHATSAPP_API_TOKEN or settings.FB_PAGE_ACCESS_TOKEN or ""

        # Set RLS Context
        await session.execute(text(f"SELECT set_config('app.current_org_id', '{org_id}', true);"))

        # 2. Find or Create Contact by IGSID
        q_contact = await session.execute(
            text(
                """
                SELECT id FROM contacts 
                WHERE organization_id = :org_id 
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
                    "subject": f"Instagram DM ({user_text[:40]}...)",
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
            "You are the official 24/7 AI Community Operations Specialist for TechVibe Members Club on Instagram. "
            "You assist members with community guidelines, VIP membership, events, bootcamps, and technical inquiries. "
            "Be energetic, polite, concise, and helpful. Format cleanly with emojis and concise bullet points suitable for Instagram DMs."
        )

        from app.domains.ai.gemini_service import generate_gemini_response
        ai_reply = await generate_gemini_response(
            user_query=user_text,
            system_prompt=system_prompt,
            kb_context=kb_context,
            chat_history=chat_hist,
        )

        # Fallback heuristic RAG matcher if Gemini is unavailable
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
                ai_reply = f"Hey! 👋 Official TechVibe guidelines:\n\n{best_chunk}\n\nFeel free to ask if you need anything else!"
            else:
                ai_reply = "Hey! 👋 Thanks for reaching out to TechVibe Members Club on Instagram. I am your 24/7 AI Specialist. How can I help you today?"

        # 6. Dispatch AI Reply via Meta Graph API
        sent = False
        if access_token:
            sent = await send_instagram_message(access_token, sender_igsid, ai_reply)

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
                VALUES (gen_random_uuid(), :org_id, 'usage_deduction', -1.0, (SELECT balance_credits FROM credit_balances WHERE organization_id = :org_id), 'Instagram AI Turn Inference', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
                """
            ),
            {"org_id": org_id},
        )

        await session.commit()
        logger.info(f"Processed Instagram interaction for TechVibe. AI reply sent to {sender_igsid}: '{ai_reply}'")
