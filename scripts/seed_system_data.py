"""Seed baseline system catalog data into PostgreSQL database.

Seeds:
- Communication channels (WhatsApp, Instagram, Telegram, Email, Webchat, Voice)
- System subscription tiers (Free, Solo, Standard, Business, Enterprise)
- System AI providers and models (OpenAI GPT-4o, Anthropic Claude 3.5, Google Gemini)
- System RBAC permissions
"""

import asyncio
from sqlalchemy import text
from app.database import admin_engine


async def seed() -> None:
    print("Starting system catalog data seed...")
    async with admin_engine.connect() as conn:
        # Channels
        await conn.execute(
            text(
                """
                INSERT INTO channels (id, type, name, description, is_active, created_at, updated_at) VALUES
                    (gen_random_uuid(), 'whatsapp', 'WhatsApp Cloud API', 'Official Meta WhatsApp Business API integration', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'instagram', 'Instagram Direct', 'Meta Graph API for Instagram messaging', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'telegram', 'Telegram Bot', 'Official Telegram Bot API gateway', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'messenger', 'Facebook Messenger', 'Meta Facebook Page messaging API', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'email', 'Omnichannel Email', 'Inbound & outbound SMTP/IMAP integration', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'webchat', 'Live Web Widget', 'Embeddable real-time customer web widget', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'voice', 'AI Voice Telephony', 'Sub-second real-time streaming voice agent telephony', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (type) DO NOTHING;
                """
            )
        )
        print("✓ Communication channels seeded.")

        # Permissions
        await conn.execute(
            text(
                """
                INSERT INTO permissions (id, slug, name, module, description, created_at, updated_at) VALUES
                    (gen_random_uuid(), 'conversations:read', 'View Conversations', 'inbox', 'Read inbox threads and messages', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'conversations:write', 'Send Messages', 'inbox', 'Reply to contacts and assign tickets', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'conversations:resolve', 'Resolve Conversations', 'inbox', 'Close and resolve customer conversations', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'contacts:manage', 'Manage CRM Contacts', 'contacts', 'Create, edit, and tag contacts', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'campaigns:manage', 'Manage Campaigns', 'campaigns', 'Create and schedule WhatsApp broadcasts', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'agents:configure', 'Configure AI Agents', 'ai', 'Create and publish AI agent versions', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'rag:manage', 'Manage Knowledge Bases', 'rag', 'Upload and index company documentation', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'workflows:build', 'Build Automations', 'workflows', 'Create and publish workflow automation DAGs', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'billing:view', 'View Financials', 'billing', 'View invoices and credit ledger', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'workspace:admin', 'Workspace Administration', 'admin', 'Manage workspace members and settings', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (slug) DO NOTHING;
                """
            )
        )
        print("✓ RBAC permissions seeded.")

        # Plans
        await conn.execute(
            text(
                """
                INSERT INTO plans (id, tier, name, description, monthly_price, annual_price, included_monthly_credits, max_seats, max_channels, is_active, created_at, updated_at) VALUES
                    (gen_random_uuid(), 'free', 'Free Starter', 'Explore AI customer operations with basic capabilities', 0.00, 0.00, 500, 1, 1, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'solo', 'Solo Operator', 'For growing single-operator businesses and creators', 39.00, 390.00, 5000, 2, 2, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'standard', 'Standard Team', 'Full omnichannel support with AI Copilot and RAG', 149.00, 1490.00, 25000, 5, 5, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'business', 'Business Scale', 'High-volume WhatsApp broadcasts, voice agents, and workflows', 529.00, 5290.00, 100000, 15, 10, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (gen_random_uuid(), 'enterprise', 'Enterprise Custom', 'Dedicated VPC, SLA guarantees, and tailored integrations', 1499.00, 14990.00, 500000, 100, 50, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (tier) DO NOTHING;
                """
            )
        )
        print("✓ Subscription plans seeded.")

        await conn.commit()
    print("Seed completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
