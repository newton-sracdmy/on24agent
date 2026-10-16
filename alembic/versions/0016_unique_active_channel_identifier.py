"""0016: One active channel account per channel identifier across all workspaces.

Inbound webhooks are routed by (channel type, account identifier) alone, so two workspaces holding
the same WhatsApp number / Page / Instagram account would split or leak each other's messages.
The application-level check cannot enforce this on its own: it races under concurrent requests and
cannot see other tenants' rows when Row-Level Security is enforced.

Placeholder identifiers (e.g. ``instagram_default``, ``webchat-default``) are exempt because they
are bound to a real identifier later.

Revision ID: 0016_unique_channel_ident
Revises: 0015_rag_embeddings
Create Date: 2026-10-16 00:00:00.000000
"""

from typing import Sequence, Union
from alembic import op

revision: str = "0016_unique_channel_ident"
down_revision: Union[str, None] = "0015_rag_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PLACEHOLDER_PREDICATE = "account_identifier !~ '[-_]default$'"


def upgrade() -> None:
    # The workspace that connected the account first keeps it, matching what the conflict check
    # would have enforced had it worked; later duplicates are soft-disconnected, not deleted.
    op.execute(
        f"""
        UPDATE channel_accounts ca
        SET is_deleted = true, status = 'disconnected', deleted_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY channel_id, account_identifier ORDER BY created_at ASC, id ASC
            ) AS rn
            FROM channel_accounts
            WHERE is_deleted = false AND {PLACEHOLDER_PREDICATE}
        ) ranked
        WHERE ca.id = ranked.id AND ranked.rn > 1;
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_active_channel_identifier
        ON channel_accounts (channel_id, account_identifier)
        WHERE is_deleted = false AND {PLACEHOLDER_PREDICATE};
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_active_channel_identifier;")
