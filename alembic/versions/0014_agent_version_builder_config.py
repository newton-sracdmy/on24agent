"""0014: Store Instruction Builder Studio form state on each agent version.

Without it the Studio could only show preset template fields after a reload, so editing
and redeploying silently replaced the live prompt with template content.

Revision ID: 0014_builder_config
Revises: 0013_drop_unused_tables
Create Date: 2026-10-16 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0014_builder_config"
down_revision: Union[str, None] = "0013_drop_unused_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_versions", sa.Column("builder_config", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_versions", "builder_config")
