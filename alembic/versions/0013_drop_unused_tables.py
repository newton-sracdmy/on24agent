"""0013: Drop tables that have no models or application code referencing them.

These tables were scaffolded for features that were never implemented (workflow engine,
outgoing webhooks, invoicing, audit/security logging, LLM request tracing, etc.).
Recreate them in a new migration when the corresponding feature is actually built.

Revision ID: 0013_drop_unused_tables
Revises: 0012_seed_data
Create Date: 2026-10-16 00:00:00.000000
"""

from typing import Sequence, Union
from alembic import op

revision: str = "0013_drop_unused_tables"
down_revision: Union[str, None] = "0012_seed_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Ordered children-first so no CASCADE is needed; an unexpected dependency fails loudly.
UNUSED_TABLES = [
    # Workflows
    "execution_steps",
    "workflow_executions",
    "workflow_triggers",
    "workflow_edges",
    "workflow_nodes",
    "workflow_versions",
    "workflows",
    # Outgoing webhooks
    "webhook_deliveries",
    "webhook_events",
    "webhook_endpoints",
    "webhook_event_types",
    # Billing & usage
    "payment_events",
    "invoice_items",
    "invoices",
    "plan_features",
    "usage_records",
    "usage_aggregates",
    # Audit, security & outbox
    "audit_logs",
    "security_events",
    "api_keys",
    "idempotency_keys",
    "outbox_events",
    "login_attempts",
    # AI / LLM tracing
    "llm_request_attempts",
    "llm_requests",
    "tool_executions",
    "model_configs",
    "provider_configs",
    "agent_guardrails",
    # RAG ingestion
    "ingestion_errors",
    "ingestion_jobs",
    # Inbox & misc
    "message_reactions",
    "notifications",
    "routing_rules",
    "business_hours",
    "team_members",
    "invitations",
    "campaign_recipients",
    "channel_account_capabilities",
    "integration_actions",
    "integration_events",
]


def upgrade() -> None:
    for table in UNUSED_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")


def downgrade() -> None:
    raise NotImplementedError(
        "0013 dropped unused tables irreversibly; recreate any needed table in a new migration."
    )
