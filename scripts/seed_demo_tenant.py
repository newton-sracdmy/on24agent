"""Seed realistic demo tenant data for Gabster AI client demonstration.

Seeds:
- Demo Organization: Acme Global Tech (a0000000-0000-0000-0000-000000000001)
- Admin User: admin@gabster.ai (Password123!)
- Organization Role & Permissions
- Membership linking admin to organization
- Channel Accounts: WhatsApp Cloud API (+1 555-019-2831) and Webchat
- AI Agent: Apex Customer Operations Agent (with GPT-4o-mini version)
- Knowledge Base: Shipping, Returns & SLA with pgvector 1536-dim embeddings
- Contacts: Rahim Chowdhury, Sarah Jenkins, Michael Zhang
- Conversations & Messages: Active omnichannel threads
- Credit Balance & Ledger: 10,000 credits & usage transactions
"""

import asyncio
from datetime import datetime, timezone
import json
from uuid import UUID
from sqlalchemy import text
from app.database import admin_engine
from app.security import get_password_hash, encrypt_secret


ORG_ID = "00000000-0000-0000-0000-000000000001"
USER_ID = "00000000-0000-0000-0000-000000000002"
ROLE_ID = "00000000-0000-0000-0000-000000000003"
MEMBERSHIP_ID = "00000000-0000-0000-0000-000000000004"

WHATSAPP_ACC_ID = "00000000-0000-0000-0000-000000000010"
WEBCHAT_ACC_ID = "00000000-0000-0000-0000-000000000011"

AGENT_CONFIG_ID = "00000000-0000-0000-0000-000000000020"
AGENT_VERSION_ID = "00000000-0000-0000-0000-000000000021"

KB_ID = "00000000-0000-0000-0000-000000000030"
DOC_ID = "00000000-0000-0000-0000-000000000031"
DOC_VERSION_ID = "00000000-0000-0000-0000-000000000032"

CONTACT_1_ID = "00000000-0000-0000-0000-000000000041"
CONTACT_2_ID = "00000000-0000-0000-0000-000000000042"
CONTACT_3_ID = "00000000-0000-0000-0000-000000000043"

CONV_1_ID = "00000000-0000-0000-0000-000000000051"
CONV_2_ID = "00000000-0000-0000-0000-000000000052"
CONV_3_ID = "00000000-0000-0000-0000-000000000053"


async def seed_demo_tenant() -> None:
    print(f"Starting Demo Tenant Seed for Acme Global Tech ({ORG_ID})...")

    async with admin_engine.connect() as conn:
        # Step 1: Create Organization
        await conn.execute(
            text(
                """
                INSERT INTO organizations (id, name, slug, status, settings, default_locale, timezone, created_at, updated_at)
                VALUES (:id, 'Acme Global Tech', 'acme-global', 'active', :settings, 'en', 'UTC', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name;
                """
            ),
            {"id": ORG_ID, "settings": json.dumps({"theme": "dark", "features": ["rag", "campaigns", "voice"]})},
        )
        print("✓ Demo Organization created.")

        # Step 2: Create Admin User
        pw_hash = get_password_hash("Password123!")
        await conn.execute(
            text(
                """
                INSERT INTO users (id, email, password_hash, full_name, phone_number, status, is_superuser, timezone, locale, created_at, updated_at)
                VALUES (:id, 'admin@gabster.ai', :pw_hash, 'Chief Operations Lead', '+15550198000', 'active', true, 'UTC', 'en', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash;
                """
            ),
            {"id": USER_ID, "pw_hash": pw_hash},
        )
        print("✓ Demo Admin User (admin@gabster.ai) created.")

        # Step 3: Create Role
        await conn.execute(
            text(
                """
                INSERT INTO roles (id, organization_id, name, slug, description, is_system, created_at, updated_at)
                VALUES (:id, :org_id, 'Workspace Administrator', 'admin', 'Full control over all workspace resources', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (organization_id, slug) DO NOTHING;
                """
            ),
            {"id": ROLE_ID, "org_id": ORG_ID},
        )

        # Assign all system permissions to this role
        await conn.execute(
            text(
                """
                INSERT INTO role_permissions (id, role_id, permission_id, created_at, updated_at)
                SELECT gen_random_uuid(), :role_id, p.id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                FROM permissions p
                ON CONFLICT DO NOTHING;
                """
            ),
            {"role_id": ROLE_ID},
        )
        print("✓ Role & Permissions configured.")

        # Step 4: Now set RLS context for tenant tables
        await conn.execute(text(f"SET LOCAL app.current_org_id = '{ORG_ID}'"))

        # Step 5: Create Membership
        await conn.execute(
            text(
                """
                INSERT INTO memberships (id, organization_id, user_id, role_id, role, agent_status, max_concurrent_chats, is_active, created_at, updated_at)
                VALUES (:id, :org_id, :user_id, :role_id, 'admin', 'online', 10, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (organization_id, user_id) DO NOTHING;
                """
            ),
            {"id": MEMBERSHIP_ID, "org_id": ORG_ID, "user_id": USER_ID, "role_id": ROLE_ID},
        )
        print("✓ Membership created.")

        # Step 6: Channel Accounts (WhatsApp + Webchat)
        channels = (await conn.execute(text("SELECT id, type FROM channels;"))).mappings().all()
        channel_map = {c["type"]: c["id"] for c in channels}

        whatsapp_cred = encrypt_secret(json.dumps({"phone_number_id": "1002938475", "access_token": "EAAXsampleMetaToken"}))
        webchat_cred = encrypt_secret(json.dumps({"widget_token": "acme_live_widget_123"}))

        if "whatsapp" in channel_map:
            await conn.execute(
                text(
                    """
                    INSERT INTO channel_accounts (id, organization_id, channel_id, name, account_identifier, status, encrypted_credentials, phone_number, created_at, updated_at)
                    VALUES (:id, :org_id, :ch_id, 'WhatsApp Official Support', '+15550192831', 'connected', :cred, '+15550192831', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (organization_id, channel_id, account_identifier) DO NOTHING;
                    """
                ),
                {"id": WHATSAPP_ACC_ID, "org_id": ORG_ID, "ch_id": channel_map["whatsapp"], "cred": whatsapp_cred},
            )

        if "webchat" in channel_map:
            await conn.execute(
                text(
                    """
                    INSERT INTO channel_accounts (id, organization_id, channel_id, name, account_identifier, status, encrypted_credentials, phone_number, created_at, updated_at)
                    VALUES (:id, :org_id, :ch_id, 'Live Website Chat Widget', 'webchat-default', 'connected', :cred, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (organization_id, channel_id, account_identifier) DO NOTHING;
                    """
                ),
                {"id": WEBCHAT_ACC_ID, "org_id": ORG_ID, "ch_id": channel_map["webchat"], "cred": webchat_cred},
            )
        print("✓ Channel accounts connected.")

        # Step 7: LLM Models lookup
        models = (await conn.execute(text("SELECT id, model_identifier FROM llm_models;"))).mappings().all()
        model_map = {m["model_identifier"]: m["id"] for m in models}
        gpt_model_id = model_map.get("gpt-4o-mini") or model_map.get("gpt-4o")
        embedding_model_id = model_map.get("text-embedding-3-small") or gpt_model_id

        # Step 8: AI Agent Config & Version
        await conn.execute(
            text(
                """
                INSERT INTO agent_configs (id, organization_id, name, description, mode, is_active, created_at, updated_at)
                VALUES (:id, :org_id, 'Apex Support Specialist', 'Autonomous AI customer support agent grounded with company knowledge base', 'autonomous', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (organization_id, name) DO NOTHING;
                """
            ),
            {"id": AGENT_CONFIG_ID, "org_id": ORG_ID},
        )

        if gpt_model_id:
            await conn.execute(
                text(
                    """
                    INSERT INTO agent_versions (id, organization_id, agent_config_id, version_number, system_prompt, model_id, temperature, max_tokens, is_published, published_at, created_at, updated_at)
                    VALUES (:id, :org_id, :config_id, 1, :prompt, :model_id, 0.5, 1024, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (agent_config_id, version_number) DO NOTHING;
                    """
                ),
                {
                    "id": AGENT_VERSION_ID,
                    "org_id": ORG_ID,
                    "config_id": AGENT_CONFIG_ID,
                    "prompt": "You are the Apex AI Customer Operations Specialist for Acme Global Tech. You respond courteously and accurately, grounding your answers in company documentation.",
                    "model_id": gpt_model_id,
                },
            )
            await conn.execute(
                text("UPDATE agent_configs SET current_version_id = :ver_id WHERE id = :id;"),
                {"ver_id": AGENT_VERSION_ID, "id": AGENT_CONFIG_ID},
            )
        print("✓ AI Agent Studio configured.")

        # Step 9: Knowledge Base & RAG Documents
        if embedding_model_id:
            await conn.execute(
                text(
                    """
                    INSERT INTO knowledge_bases (id, organization_id, name, description, embedding_model_id, distance_metric, is_active, created_at, updated_at)
                    VALUES (:id, :org_id, 'Acme Product & Shipping Knowledge Base', 'Global delivery times, refund policy, and warranty terms', :model_id, 'cosine', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (organization_id, name) DO NOTHING;
                    """
                ),
                {"id": KB_ID, "org_id": ORG_ID, "model_id": embedding_model_id},
            )

            # Link KB to Agent
            await conn.execute(
                text(
                    """
                    INSERT INTO agent_knowledge_bases (id, organization_id, agent_config_id, knowledge_base_id, created_at, updated_at)
                    VALUES (gen_random_uuid(), :org_id, :agent_id, :kb_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT DO NOTHING;
                    """
                ),
                {"org_id": ORG_ID, "agent_id": AGENT_CONFIG_ID, "kb_id": KB_ID},
            )

            # Document & Version
            await conn.execute(
                text(
                    """
                    INSERT INTO documents (id, organization_id, knowledge_base_id, title, source_type, mime_type, file_size_bytes, status, created_at, updated_at)
                    VALUES (:id, :org_id, :kb_id, 'Official Shipping & Return Guidelines 2026', 'file_upload', 'text/markdown', 4096, 'indexed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (id) DO NOTHING;
                    """
                ),
                {"id": DOC_ID, "org_id": ORG_ID, "kb_id": KB_ID},
            )

            await conn.execute(
                text(
                    """
                    INSERT INTO document_versions (id, organization_id, document_id, version_number, content_hash, raw_text, created_at, updated_at)
                    VALUES (:id, :org_id, :doc_id, 1, 'sha256_mock_hash_for_policy', 'Orders are delivered in 1-2 business days in Dhaka. International shipments take 3-5 days via DHL.', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (document_id, version_number) DO NOTHING;
                    """
                ),
                {"id": DOC_VERSION_ID, "org_id": ORG_ID, "doc_id": DOC_ID},
            )

            # Document Chunk with pgvector 1536-dim embedding
            dummy_vector = "[" + ",".join(["0.025"] * 1536) + "]"
            await conn.execute(
                text(
                    """
                    INSERT INTO document_chunks (id, organization_id, document_id, document_version_id, chunk_index, content_text, token_count, embedding, metadata_json, created_at, updated_at)
                    VALUES (gen_random_uuid(), :org_id, :doc_id, :ver_id, 0, 'Orders are delivered in 1-2 business days in Dhaka. Express couriers notify the recipient before delivery.', 28, CAST(:emb AS vector), CAST('{"section": "delivery"}' AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (id) DO NOTHING;
                    """
                ),
                {"org_id": ORG_ID, "doc_id": DOC_ID, "ver_id": DOC_VERSION_ID, "emb": dummy_vector},
            )
        print("✓ RAG Knowledge Base and pgvector embeddings seeded.")

        # Step 10: CRM Contacts
        contacts_data = [
            (CONTACT_1_ID, "Rahim", "Chowdhury", "rahim@example.com", "+8801711223344", "customer", json.dumps({"city": "Dhaka", "tier": "VIP"})),
            (CONTACT_2_ID, "Sarah", "Jenkins", "sarah.j@example.com", "+14155552671", "opportunity", json.dumps({"company": "Fintech Solutions", "seats": "25"})),
            (CONTACT_3_ID, "Michael", "Zhang", "michael.z@example.com", "+447911123456", "customer", json.dumps({"tier": "Enterprise", "region": "EMEA"})),
        ]
        for cid, fn, ln, em, ph, stage, attrs in contacts_data:
            await conn.execute(
                text(
                    """
                    INSERT INTO contacts (id, organization_id, first_name, last_name, email, phone_number, lifecycle_stage, custom_attributes, created_at, updated_at)
                    VALUES (:id, :org_id, :fn, :ln, :em, :ph, :stage, CAST(:attrs AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (id) DO NOTHING;
                    """
                ),
                {"id": cid, "org_id": ORG_ID, "fn": fn, "ln": ln, "em": em, "ph": ph, "stage": stage, "attrs": attrs},
            )
        print("✓ CRM Contacts seeded.")

        # Step 11: Conversations & Messages
        # Thread 1: Rahim Chowdhury (WhatsApp)
        await conn.execute(
            text(
                """
                INSERT INTO conversations (id, organization_id, contact_id, channel_account_id, assigned_user_id, status, priority, subject, unread_count, created_at, updated_at)
                VALUES (:id, :org_id, :cid, :chid, :uid, 'open', 'high', 'Order #ORD-8821 delivery status inquiry', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO NOTHING;
                """
            ),
            {"id": CONV_1_ID, "org_id": ORG_ID, "cid": CONTACT_1_ID, "chid": WHATSAPP_ACC_ID, "uid": USER_ID},
        )
        # Messages for Thread 1
        await conn.execute(
            text(
                """
                INSERT INTO messages (id, organization_id, conversation_id, sender_type, content_type, text_content, delivery_status, created_at, updated_at) VALUES
                (gen_random_uuid(), :org_id, :conv_id, 'contact', 'text', 'Hi, I placed order #ORD-8821 yesterday. Can you tell me when it will arrive in Dhaka?', 'read', CURRENT_TIMESTAMP - INTERVAL '30 minutes', CURRENT_TIMESTAMP),
                (gen_random_uuid(), :org_id, :conv_id, 'bot', 'text', 'Hello Rahim! Your order #ORD-8821 has been processed and dispatched via Express Courier. Expected delivery is tomorrow between 2 PM - 6 PM. Is there anything else I can help with?', 'delivered', CURRENT_TIMESTAMP - INTERVAL '29 minutes', CURRENT_TIMESTAMP),
                (gen_random_uuid(), :org_id, :conv_id, 'contact', 'text', 'Thank you! That was fast and clear.', 'read', CURRENT_TIMESTAMP - INTERVAL '10 minutes', CURRENT_TIMESTAMP),
                (gen_random_uuid(), :org_id, :conv_id, 'bot', 'text', 'You are very welcome! Have a wonderful day ahead.', 'delivered', CURRENT_TIMESTAMP - INTERVAL '9 minutes', CURRENT_TIMESTAMP);
                """
            ),
            {"org_id": ORG_ID, "conv_id": CONV_1_ID},
        )

        # Thread 2: Sarah Jenkins (Webchat)
        await conn.execute(
            text(
                """
                INSERT INTO conversations (id, organization_id, contact_id, channel_account_id, assigned_user_id, status, priority, subject, unread_count, created_at, updated_at)
                VALUES (:id, :org_id, :cid, :chid, :uid, 'open', 'medium', 'Enterprise Multi-Tenancy & SLA inquiries', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO NOTHING;
                """
            ),
            {"id": CONV_2_ID, "org_id": ORG_ID, "cid": CONTACT_2_ID, "chid": WEBCHAT_ACC_ID, "uid": USER_ID},
        )
        await conn.execute(
            text(
                """
                INSERT INTO messages (id, organization_id, conversation_id, sender_type, content_type, text_content, delivery_status, created_at, updated_at) VALUES
                (gen_random_uuid(), :org_id, :conv_id, 'contact', 'text', 'Hello, does Gabster AI offer row-level database isolation and automated SLA escalations?', 'read', CURRENT_TIMESTAMP - INTERVAL '15 minutes', CURRENT_TIMESTAMP),
                (gen_random_uuid(), :org_id, :conv_id, 'bot', 'text', 'Yes Sarah! Gabster AI enforces PostgreSQL Row-Level Security (RLS) across all tenant tables and offers real-time SLA breach monitoring.', 'delivered', CURRENT_TIMESTAMP - INTERVAL '14 minutes', CURRENT_TIMESTAMP),
                (gen_random_uuid(), :org_id, :conv_id, 'contact', 'text', 'Wonderful! Could you provide an estimate for 25 agent seats?', 'sent', CURRENT_TIMESTAMP - INTERVAL '2 minutes', CURRENT_TIMESTAMP);
                """
            ),
            {"org_id": ORG_ID, "conv_id": CONV_2_ID},
        )

        # Thread 3: Michael Zhang (WhatsApp)
        await conn.execute(
            text(
                """
                INSERT INTO conversations (id, organization_id, contact_id, channel_account_id, assigned_user_id, status, priority, subject, unread_count, created_at, updated_at)
                VALUES (:id, :org_id, :cid, :chid, :uid, 'waiting_for_agent', 'urgent', 'Billing adjustment request - INV-2026-004', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO NOTHING;
                """
            ),
            {"id": CONV_3_ID, "org_id": ORG_ID, "cid": CONTACT_3_ID, "chid": WHATSAPP_ACC_ID, "uid": USER_ID},
        )
        await conn.execute(
            text(
                """
                INSERT INTO messages (id, organization_id, conversation_id, sender_type, content_type, text_content, delivery_status, created_at, updated_at) VALUES
                (gen_random_uuid(), :org_id, :conv_id, 'contact', 'text', 'Urgent: We noticed an unexpected billing item on invoice INV-2026-004. Can an agent please review?', 'sent', CURRENT_TIMESTAMP - INTERVAL '5 minutes', CURRENT_TIMESTAMP);
                """
            ),
            {"org_id": ORG_ID, "conv_id": CONV_3_ID},
        )
        print("✓ Omnichannel Conversations & Messages seeded.")

        # Step 12: Credit Balances & Double-entry Ledger
        await conn.execute(
            text(
                """
                INSERT INTO credit_balances (id, organization_id, balance_credits, lifetime_granted_credits, lifetime_consumed_credits, created_at, updated_at)
                VALUES (gen_random_uuid(), :org_id, 10000.0, 10000.0, 15.0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (organization_id) DO UPDATE SET balance_credits = 10000.0;
                """
            ),
            {"org_id": ORG_ID},
        )

        await conn.execute(
            text(
                """
                INSERT INTO credit_ledger (id, organization_id, transaction_type, amount, balance_after, description, created_at, updated_at) VALUES
                (gen_random_uuid(), :org_id, 'subscription_grant', 10000.0, 10000.0, 'Enterprise Subscription Monthly Grant', CURRENT_TIMESTAMP - INTERVAL '1 day', CURRENT_TIMESTAMP),
                (gen_random_uuid(), :org_id, 'usage_deduction', -15.0, 9985.0, 'AI Copilot RAG Inference for Order Query', CURRENT_TIMESTAMP - INTERVAL '30 minutes', CURRENT_TIMESTAMP);
                """
            ),
            {"org_id": ORG_ID},
        )
        print("✓ Credit Ledger & Balances initialized.")

        await conn.commit()

    print("\n🎉 Demo Tenant Seeding Completed Successfully!")
    print("==================================================================")
    print("Organization: Acme Global Tech (ID: a0000000-0000-0000-0000-000000000001)")
    print("Login Email:  admin@gabster.ai")
    print("Password:     Password123!")
    print("API Endpoint: http://localhost:8000")
    print("Swagger Docs: http://localhost:8000/docs")
    print("Web Dashboard:http://localhost:8000/")
    print("==================================================================")


if __name__ == "__main__":
    asyncio.run(seed_demo_tenant())
