"""0011: Production performance indexes, pgvector HNSW index, and trigram fuzzy search.

Revision ID: 0011_indexes_and_performance
Revises: 0010_rls_policies
Create Date: 2026-10-04 01:31:00.000000
"""

from typing import Sequence, Union
from alembic import op

revision: str = "0011_indexes_perf"
down_revision: Union[str, None] = "0010_rls_policies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. HNSW Vector Index for sub-second semantic retrieval across millions of chunks
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw
        ON document_chunks USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
        """
    )

    # 2. High-speed partial indexes for active inbox views
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_conversations_active_inbox
        ON conversations (organization_id, assigned_user_id, status, last_message_at DESC)
        WHERE is_deleted = false AND status IN ('open', 'waiting_for_agent', 'waiting_for_user');
        """
    )

    # 3. WhatsApp 24hr service window expiration queue index
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_conversations_active_service_window
        ON conversations (organization_id, service_window_expires_at)
        WHERE status != 'closed' AND service_window_expires_at IS NOT NULL;
        """
    )

    # 4. Trigram fuzzy text search indexes on contacts and knowledge base
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_contacts_name_trgm
        ON contacts USING gin ((first_name || ' ' || COALESCE(last_name, '')) gin_trgm_ops);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_documents_title_trgm
        ON documents USING gin (title gin_trgm_ops);
        """
    )

    # 5. Composite index for message chronological retrieval
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_messages_chronological
        ON messages (conversation_id, created_at ASC);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_messages_chronological;")
    op.execute("DROP INDEX IF EXISTS ix_documents_title_trgm;")
    op.execute("DROP INDEX IF EXISTS ix_contacts_name_trgm;")
    op.execute("DROP INDEX IF EXISTS ix_conversations_active_service_window;")
    op.execute("DROP INDEX IF EXISTS ix_conversations_active_inbox;")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw;")
