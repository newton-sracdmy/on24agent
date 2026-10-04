"""0003: AI/LLM providers, models, and messaging channels schema.

Revision ID: 0003_ai_and_channels_schema
Revises: 0002_identity_schema
Create Date: 2026-10-04 01:23:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_ai_and_channels_schema"
down_revision: Union[str, None] = "0002_identity_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # LLM Providers table
    op.create_table(
        "llm_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(50), nullable=False),
        sa.Column("api_base_url", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_llm_providers_slug", "llm_providers", ["slug"])

    # LLM Models table
    op.create_table(
        "llm_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("model_identifier", sa.String(100), nullable=False),
        sa.Column("modality", sa.String(50), server_default=sa.text("'text_only'"), nullable=False),
        sa.Column("context_window", sa.Integer(), server_default=sa.text("128000"), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), server_default=sa.text("4096"), nullable=False),
        sa.Column("input_token_cost_per_million", sa.Numeric(10, 4), server_default=sa.text("0.0"), nullable=False),
        sa.Column("output_token_cost_per_million", sa.Numeric(10, 4), server_default=sa.text("0.0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["llm_providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_identifier"),
    )
    op.create_index("ix_llm_models_provider_id", "llm_models", ["provider_id"])
    op.create_index("ix_llm_models_identifier", "llm_models", ["model_identifier"])

    # Provider Configs (tenant-specific BYOK)
    op.create_table(
        "provider_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("custom_base_url", sa.String(255), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["llm_providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "provider_id", name="uq_org_provider_config"),
    )
    op.create_index("ix_provider_configs_org_id", "provider_configs", ["organization_id"])

    # Model Configs (tenant-specific model defaults)
    op.create_table(
        "model_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_default_for_chat", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_default_for_voice", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_default_for_embedding", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("default_temperature", sa.Float(), server_default=sa.text("0.7"), nullable=False),
        sa.Column("default_max_tokens", sa.Integer(), server_default=sa.text("1024"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["llm_models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "model_id", name="uq_org_model_config"),
    )
    op.create_index("ix_model_configs_org_id", "model_configs", ["organization_id"])

    # Channels registry table
    op.create_table(
        "channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("icon_url", sa.String(1024), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("type"),
    )
    op.create_index("ix_channels_type", "channels", ["type"])

    # Channel Accounts table (tenant connected accounts)
    op.create_table(
        "channel_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("account_identifier", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), server_default=sa.text("'connected'"), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False),
        sa.Column("webhook_secret", sa.String(255), nullable=True),
        sa.Column("phone_number", sa.String(50), nullable=True),
        sa.Column("settings", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "channel_id", "account_identifier", name="uq_org_channel_account"),
    )
    op.create_index("ix_channel_accounts_org_id", "channel_accounts", ["organization_id"])
    op.create_index("ix_channel_accounts_phone", "channel_accounts", ["phone_number"])
    op.create_index("ix_channel_accounts_org_status", "channel_accounts", ["organization_id", "status"])

    # Channel Account Capabilities table
    op.create_table(
        "channel_account_capabilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capability", sa.String(100), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("configuration", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["channel_account_id"], ["channel_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_account_id", "capability", name="uq_channel_capability"),
    )
    op.create_index("ix_channel_account_capabilities_account", "channel_account_capabilities", ["channel_account_id"])


def downgrade() -> None:
    op.drop_table("channel_account_capabilities")
    op.drop_table("channel_accounts")
    op.drop_table("channels")
    op.drop_table("model_configs")
    op.drop_table("provider_configs")
    op.drop_table("llm_models")
    op.drop_table("llm_providers")
