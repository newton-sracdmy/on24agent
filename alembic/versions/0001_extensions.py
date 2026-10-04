"""0001: Enable PostgreSQL required extensions (pgvector, uuid-ossp, pg_trgm, pgcrypto).

Revision ID: 0001_extensions
Revises: None
Create Date: 2026-10-04 01:21:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001_extensions"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions required for UUID generation, vector embeddings, and full-text fuzzy matching
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm";')


def downgrade() -> None:
    op.execute('DROP EXTENSION IF EXISTS "vector";')
    op.execute('DROP EXTENSION IF EXISTS "pg_trgm";')
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto";')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp";')
