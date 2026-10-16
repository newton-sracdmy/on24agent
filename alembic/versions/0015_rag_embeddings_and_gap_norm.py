"""0015: Register the Gemini embedding model and re-normalize knowledge gap queries.

- Knowledge bases now embed with gemini-embedding-001 (1536 dims), so it needs an llm_models row.
- normalize_query used to strip Bengali vowel signs (দাম -> দম); existing rows are recomputed
  with the fixed normalizer so new questions dedupe against them correctly.

Existing chunk embeddings are placeholders and must be rebuilt with
`python -m scripts.reindex_embeddings` (needs GOOGLE_API_KEY, so it is not run here).

Revision ID: 0015_rag_embeddings
Revises: 0014_builder_config
Create Date: 2026-10-16 00:00:00.000000
"""

import unicodedata
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_rag_embeddings"
down_revision: Union[str, None] = "0014_builder_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize(query: str) -> str:
    # Frozen copy of RAGService.normalize_query at this revision
    lowered = unicodedata.normalize("NFC", query.lower())
    cleaned = "".join(" " if unicodedata.category(ch)[0] in ("P", "S") else ch for ch in lowered)
    return " ".join(cleaned.split())[:500]


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO llm_models (id, provider_id, name, model_identifier, modality, context_window, max_output_tokens,
                                input_token_cost_per_million, output_token_cost_per_million, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), p.id, 'Gemini Embedding 001', 'gemini-embedding-001', 'embedding', 2048, 1536,
               0.1500, 0.0000, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM llm_providers p WHERE p.slug = 'google'
        ON CONFLICT (model_identifier) DO NOTHING;
        """
    )

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, organization_id, question, normalized_query FROM knowledge_gaps")).all()
    taken = {(r.organization_id, r.normalized_query) for r in rows}
    for r in rows:
        new_norm = _normalize(r.question)
        if new_norm == r.normalized_query or not new_norm or (r.organization_id, new_norm) in taken:
            continue
        conn.execute(
            sa.text("UPDATE knowledge_gaps SET normalized_query = :n WHERE id = :id"),
            {"n": new_norm, "id": r.id},
        )
        taken.discard((r.organization_id, r.normalized_query))
        taken.add((r.organization_id, new_norm))


def downgrade() -> None:
    # Gap normalization is not reverted; the old form was lossy.
    op.execute(
        """
        DELETE FROM llm_models m
        WHERE m.model_identifier = 'gemini-embedding-001'
          AND NOT EXISTS (SELECT 1 FROM knowledge_bases kb WHERE kb.embedding_model_id = m.id);
        """
    )
