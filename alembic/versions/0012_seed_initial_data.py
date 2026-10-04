"""0012: Seed baseline system catalog data (channels, permissions, roles, providers, models, plans).

Revision ID: 0012_seed_initial_data
Revises: 0011_indexes_and_performance
Create Date: 2026-10-04 01:32:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0012_seed_initial_data"
down_revision: Union[str, None] = "0011_indexes_and_performance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Seed System Channels
    op.execute(
        """
        INSERT INTO channels (id, type, name, description, is_active, created_at, updated_at) VALUES
            (gen_random_uuid(), 'whatsapp', 'WhatsApp Cloud API', 'Official Meta WhatsApp Business API integration', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), 'instagram', 'Instagram Direct', 'Meta Graph API for Instagram messaging', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), 'telegram', 'Telegram Bot', 'Official Telegram Bot API gateway', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), 'messenger', 'Facebook Messenger', 'Meta Facebook Page messaging API', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), 'email', 'Omnichannel Email', 'Inbound & outbound SMTP/IMAP and Postmark/SES integration', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), 'webchat', 'Live Web Widget', 'Embeddable real-time customer web widget', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (gen_random_uuid(), 'voice', 'AI Voice Telephony', 'Sub-second real-time streaming voice agent telephony', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (type) DO NOTHING;
        """
    )

    # 2. Seed System Permissions
    op.execute(
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

    # 3. Seed System Subscription Plans
    op.execute(
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

    # 4. Seed Upstream AI Providers & Models
    op.execute(
        """
        DO $$
        DECLARE
            openai_id UUID := gen_random_uuid();
            anthropic_id UUID := gen_random_uuid();
            google_id UUID := gen_random_uuid();
        BEGIN
            INSERT INTO llm_providers (id, name, slug, api_base_url, is_active, created_at, updated_at)
            VALUES (openai_id, 'OpenAI', 'openai', 'https://api.openai.com/v1', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (slug) DO NOTHING;

            INSERT INTO llm_providers (id, name, slug, api_base_url, is_active, created_at, updated_at)
            VALUES (anthropic_id, 'Anthropic', 'anthropic', 'https://api.anthropic.com/v1', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (slug) DO NOTHING;

            INSERT INTO llm_providers (id, name, slug, api_base_url, is_active, created_at, updated_at)
            VALUES (google_id, 'Google Gemini', 'google', 'https://generativelanguage.googleapis.com/v1beta', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (slug) DO NOTHING;

            -- Models
            INSERT INTO llm_models (id, provider_id, name, model_identifier, modality, context_window, max_output_tokens, input_token_cost_per_million, output_token_cost_per_million, is_active, created_at, updated_at)
            VALUES
                (gen_random_uuid(), openai_id, 'GPT-4o', 'gpt-4o', 'multimodal_vision', 128000, 4096, 5.0000, 15.0000, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                (gen_random_uuid(), openai_id, 'GPT-4o-Mini', 'gpt-4o-mini', 'text_only', 128000, 4096, 0.1500, 0.6000, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                (gen_random_uuid(), openai_id, 'Text Embedding 3 Small', 'text-embedding-3-small', 'embedding', 8191, 1536, 0.0200, 0.0000, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                (gen_random_uuid(), anthropic_id, 'Claude 3.5 Sonnet', 'claude-3-5-sonnet-20240620', 'multimodal_vision', 200000, 8192, 3.0000, 15.0000, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                (gen_random_uuid(), google_id, 'Gemini 1.5 Pro', 'gemini-1.5-pro', 'multimodal_vision', 1000000, 8192, 3.5000, 10.5000, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (model_identifier) DO NOTHING;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM llm_models;")
    op.execute("DELETE FROM llm_providers;")
    op.execute("DELETE FROM plans;")
    op.execute("DELETE FROM permissions;")
    op.execute("DELETE FROM channels;")
