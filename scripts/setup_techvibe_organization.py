"""Setup TechVibe Members Club organization and Facebook Messenger channel."""

import asyncio
import json
from uuid import UUID
from sqlalchemy import text
from app.config import settings
from app.database import admin_engine
from app.security import encrypt_secret


TECHVIBE_ORG_ID = "00000000-0000-0000-0000-000000000200"
TECHVIBE_CHANNEL_ACC_ID = "00000000-0000-0000-0000-000000000210"
TECHVIBE_AGENT_CONFIG_ID = "00000000-0000-0000-0000-000000000220"
TECHVIBE_AGENT_VERSION_ID = "00000000-0000-0000-0000-000000000221"
TECHVIBE_KB_ID = "00000000-0000-0000-0000-000000000230"
TECHVIBE_DOC_ID = "00000000-0000-0000-0000-000000000231"
TECHVIBE_DOC_VER_ID = "00000000-0000-0000-0000-000000000232"

PAGE_ID = settings.FB_PAGE_ID or "1463059650215713"
PAGE_ACCESS_TOKEN = settings.FB_PAGE_ACCESS_TOKEN or ""


async def setup_techvibe():
    print(f"Setting up TechVibe Members Club ({TECHVIBE_ORG_ID})...")
    async with admin_engine.connect() as conn:
        # 1. Organization
        await conn.execute(
            text(
                """
                INSERT INTO organizations (id, name, slug, status, settings, default_locale, timezone, created_at, updated_at)
                VALUES (:id, 'TechVibe Members Club', 'techvibe-members-club', 'active', :settings, 'bn', 'Asia/Dhaka', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name;
                """
            ),
            {"id": TECHVIBE_ORG_ID, "settings": json.dumps({"brand": "TechVibe", "facebook_page_id": PAGE_ID})},
        )
        print("✓ Organization created: TechVibe Members Club")

        # 2. Set RLS context
        await conn.execute(text(f"SELECT set_config('app.current_org_id', '{TECHVIBE_ORG_ID}', true);"))

        # 3. Channel Account (Messenger)
        channel_row = (await conn.execute(text("SELECT id FROM channels WHERE type = 'messenger' LIMIT 1;"))).mappings().first()
        if channel_row:
            ch_id = channel_row["id"]
            creds = encrypt_secret(json.dumps({"page_id": PAGE_ID, "page_access_token": PAGE_ACCESS_TOKEN}))
            await conn.execute(
                text(
                    """
                    INSERT INTO channel_accounts (id, organization_id, channel_id, name, account_identifier, status, encrypted_credentials, settings, created_at, updated_at)
                    VALUES (:id, :org_id, :ch_id, 'TechVibe Facebook Messenger', :account_id, 'connected', :creds, :settings, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (organization_id, channel_id, account_identifier) DO UPDATE
                    SET encrypted_credentials = EXCLUDED.encrypted_credentials, status = 'connected';
                    """
                ),
                {
                    "id": TECHVIBE_CHANNEL_ACC_ID,
                    "org_id": TECHVIBE_ORG_ID,
                    "ch_id": ch_id,
                    "account_id": PAGE_ID,
                    "creds": creds,
                    "settings": json.dumps({"page_name": "TechVibe Members Club"}),
                },
            )
            print("✓ Facebook Messenger Channel Account linked.")

        # 4. AI Models lookup
        models = (await conn.execute(text("SELECT id, model_identifier FROM llm_models;"))).mappings().all()
        model_map = {m["model_identifier"]: m["id"] for m in models}
        gpt_model_id = model_map.get("gpt-4o-mini") or model_map.get("gpt-4o")
        embedding_model_id = model_map.get("text-embedding-3-small") or gpt_model_id

        # 5. AI Agent
        await conn.execute(
            text(
                """
                INSERT INTO agent_configs (id, organization_id, name, description, mode, is_active, created_at, updated_at)
                VALUES (:id, :org_id, 'TechVibe AI Care Specialist', 'Facebook Messenger AI Support for TechVibe Members Club', 'autonomous', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (organization_id, name) DO NOTHING;
                """
            ),
            {"id": TECHVIBE_AGENT_CONFIG_ID, "org_id": TECHVIBE_ORG_ID},
        )

        if gpt_model_id:
            await conn.execute(
                text(
                    """
                    INSERT INTO agent_versions (id, organization_id, agent_config_id, version_number, system_prompt, model_id, temperature, max_tokens, is_published, published_at, created_at, updated_at)
                    VALUES (:id, :org_id, :config_id, 1, :prompt, :model_id, 0.6, 1024, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (agent_config_id, version_number) DO NOTHING;
                    """
                ),
                {
                    "id": TECHVIBE_AGENT_VERSION_ID,
                    "org_id": TECHVIBE_ORG_ID,
                    "config_id": TECHVIBE_AGENT_CONFIG_ID,
                    "prompt": "You are the friendly, intelligent AI Community Assistant for TechVibe Members Club. You help members with community guidelines, event schedules, tech queries, and membership benefits. Always be polite, concise, and helpful. You can speak in Bengali or English based on the user's language.",
                    "model_id": gpt_model_id,
                },
            )
            await conn.execute(
                text("UPDATE agent_configs SET current_version_id = :ver_id WHERE id = :id;"),
                {"ver_id": TECHVIBE_AGENT_VERSION_ID, "id": TECHVIBE_AGENT_CONFIG_ID},
            )
            print("✓ AI Agent configured.")

        # 6. Knowledge Base & Guidelines
        if embedding_model_id:
            await conn.execute(
                text(
                    """
                    INSERT INTO knowledge_bases (id, organization_id, name, description, embedding_model_id, distance_metric, is_active, created_at, updated_at)
                    VALUES (:id, :org_id, 'TechVibe Community Guidelines & FAQ', 'Official group rules, events, membership and tech discussions FAQ', :model_id, 'cosine', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (organization_id, name) DO NOTHING;
                    """
                ),
                {"id": TECHVIBE_KB_ID, "org_id": TECHVIBE_ORG_ID, "model_id": embedding_model_id},
            )

            await conn.execute(
                text(
                    """
                    INSERT INTO agent_knowledge_bases (id, organization_id, agent_config_id, knowledge_base_id, created_at, updated_at)
                    VALUES (gen_random_uuid(), :org_id, :agent_id, :kb_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT DO NOTHING;
                    """
                ),
                {"org_id": TECHVIBE_ORG_ID, "agent_id": TECHVIBE_AGENT_CONFIG_ID, "kb_id": TECHVIBE_KB_ID},
            )

            await conn.execute(
                text(
                    """
                    INSERT INTO documents (id, organization_id, knowledge_base_id, title, source_type, mime_type, file_size_bytes, status, created_at, updated_at)
                    VALUES (:id, :org_id, :kb_id, 'TechVibe Community Rules & Welcome Guide', 'file_upload', 'text/markdown', 2048, 'indexed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (id) DO NOTHING;
                    """
                ),
                {"id": TECHVIBE_DOC_ID, "org_id": TECHVIBE_ORG_ID, "kb_id": TECHVIBE_KB_ID},
            )

            await conn.execute(
                text(
                    """
                    INSERT INTO document_versions (id, organization_id, document_id, version_number, content_hash, raw_text, created_at, updated_at)
                    VALUES (:id, :org_id, :doc_id, 1, 'hash_techvibe_rules', 'TechVibe Members Club Rules: 1. Be respectful to all members. 2. No spam or unauthorized promotional posts. 3. Weekly live AI sessions are held every Friday at 8 PM. 4. For VIP membership, contact admins.', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (document_id, version_number) DO NOTHING;
                    """
                ),
                {"id": TECHVIBE_DOC_VER_ID, "org_id": TECHVIBE_ORG_ID, "doc_id": TECHVIBE_DOC_ID},
            )

            dummy_vector = "[" + ",".join(["0.03"] * 1536) + "]"
            await conn.execute(
                text(
                    """
                    INSERT INTO document_chunks (id, organization_id, document_id, document_version_id, chunk_index, content_text, token_count, embedding, metadata_json, created_at, updated_at)
                    VALUES (gen_random_uuid(), :org_id, :doc_id, :ver_id, 0, 'TechVibe Members Club Rules: 1. Be respectful. 2. Weekly live AI sessions are held every Friday at 8 PM.', 30, CAST(:emb AS vector), CAST('{\"section\": \"rules\"}' AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (id) DO NOTHING;
                    """
                ),
                {"org_id": TECHVIBE_ORG_ID, "doc_id": TECHVIBE_DOC_ID, "ver_id": TECHVIBE_DOC_VER_ID, "emb": dummy_vector},
            )
            print("✓ Community Knowledge Base & pgvector embeddings initialized.")

        # 7. Credit Balance & Ledger
        await conn.execute(
            text(
                """
                INSERT INTO credit_balances (id, organization_id, balance_credits, lifetime_granted_credits, lifetime_consumed_credits, created_at, updated_at)
                VALUES (gen_random_uuid(), :org_id, 10000.0, 10000.0, 0.0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (organization_id) DO UPDATE SET balance_credits = 10000.0;
                """
            ),
            {"org_id": TECHVIBE_ORG_ID},
        )
        print("✓ 10,000 Credits allocated.")

        await conn.commit()

    print("\n🎉 TechVibe Members Club Setup Complete!")


if __name__ == "__main__":
    asyncio.run(setup_techvibe())
