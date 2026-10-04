"""0010: PostgreSQL Row-Level Security (RLS) policies across all tenant-owned tables.

Enforces tenant isolation by binding every tenant query to `app.current_org_id`.
Revision ID: 0010_rls_policies
Revises: 0009_audit_security_and_outbox_schema
Create Date: 2026-10-04 01:30:00.000000
"""

from typing import Sequence, Union
from alembic import op

revision: str = "0010_rls_policies"
down_revision: Union[str, None] = "0009_audit_security_and_outbox_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_TABLES = [
    "memberships",
    "provider_configs",
    "model_configs",
    "channel_accounts",
    "channel_account_capabilities",
    "contacts",
    "contact_identities",
    "tags",
    "contact_tags",
    "custom_fields",
    "contact_events",
    "contact_notes",
    "teams",
    "team_members",
    "business_hours",
    "sla_policies",
    "routing_rules",
    "conversations",
    "messages",
    "message_attachments",
    "message_reactions",
    "canned_responses",
    "satisfaction_ratings",
    "notifications",
    "agent_configs",
    "agent_versions",
    "agent_tools",
    "agent_knowledge_bases",
    "agent_guardrails",
    "agent_runs",
    "llm_requests",
    "llm_request_attempts",
    "tool_executions",
    "knowledge_bases",
    "documents",
    "document_versions",
    "document_chunks",
    "ingestion_jobs",
    "ingestion_errors",
    "message_templates",
    "campaign_segments",
    "campaigns",
    "campaign_recipients",
    "workflows",
    "workflow_versions",
    "workflow_nodes",
    "workflow_edges",
    "workflow_triggers",
    "workflow_executions",
    "execution_steps",
    "integrations",
    "integration_actions",
    "integration_events",
    "webhook_endpoints",
    "webhook_events",
    "webhook_deliveries",
    "subscriptions",
    "invoices",
    "invoice_items",
    "payment_events",
    "credit_balances",
    "credit_ledger",
    "usage_records",
    "usage_aggregates",
    "audit_logs",
    "security_events",
    "api_keys",
    "outbox_events",
    "idempotency_keys",
]


def upgrade() -> None:
    for table in TENANT_TABLES:
        # Enable and force Row-Level Security
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")

        # Tenant isolation policy: matching against session variable 'app.current_org_id'
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_policy ON {table}
                FOR ALL
                USING (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
                WITH CHECK (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
            """
        )


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
