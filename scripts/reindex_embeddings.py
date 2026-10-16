"""Rebuild chunks and embeddings for documents that lack current-model embeddings.

Covers documents ingested before real embeddings existed (placeholder vectors and
unbounded paragraph chunks) and documents stored while the embedding provider was
unavailable. Each document is re-chunked from its stored source text with the current
chunker, then embedded. Safe to re-run; fully indexed documents are skipped.

Usage:
    python -m scripts.reindex_embeddings            # all organizations
    python -m scripts.reindex_embeddings --dry-run  # report only
"""

import argparse
import asyncio

from sqlalchemy import delete, or_, select

import app.common.all_models  # noqa: F401  (registers every table for ORM flushes)
from app.constants import IngestionJobStatus
from app.database import admin_session_factory
from app.domains.ai.embedding_service import EMBEDDING_MODEL, embed_texts
from app.domains.rag.models import Document, DocumentChunk, DocumentVersion
from app.domains.rag.schemas import MAX_DOCUMENT_CHARS
from app.domains.rag.service import chunk_text


async def main(dry_run: bool) -> None:
    async with admin_session_factory() as session:
        stale = or_(
            DocumentChunk.embedding.is_(None),
            DocumentChunk.metadata_json["embedding_model"].astext.is_distinct_from(EMBEDDING_MODEL),
        )
        doc_ids = (
            await session.execute(
                select(DocumentChunk.document_id)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(stale, Document.status != IngestionJobStatus.FAILED.value)
                .distinct()
            )
        ).scalars().all()
        print(f"{len(doc_ids)} document(s) need re-indexing.")
        if dry_run:
            return

        done = failed = 0
        for doc_id in doc_ids:
            doc = await session.get(Document, doc_id)
            version = (
                await session.execute(
                    select(DocumentVersion)
                    .where(DocumentVersion.document_id == doc_id)
                    .order_by(DocumentVersion.version_number.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not version or len(version.raw_text) > MAX_DOCUMENT_CHARS:
                doc.status = IngestionJobStatus.FAILED.value
                doc.error_message = "Source text missing or over the size limit; re-upload in smaller files"
                await session.commit()
                print(f"  SKIP {doc.title[:60]!r}: source text missing or too large")
                failed += 1
                continue

            chunks = chunk_text(version.raw_text)
            vectors = await embed_texts([f"{doc.title}\n{c}" for c in chunks])
            if vectors is None:
                raise SystemExit(f"Embedding provider unavailable at {doc.title!r}; earlier documents were saved.")

            await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
            for idx, (content, vec) in enumerate(zip(chunks, vectors)):
                session.add(
                    DocumentChunk(
                        organization_id=doc.organization_id,
                        document_id=doc.id,
                        document_version_id=version.id,
                        chunk_index=idx,
                        content_text=content,
                        token_count=len(content.split()),
                        embedding=vec,
                        metadata_json={"embedding_model": EMBEDDING_MODEL},
                    )
                )
            doc.status = IngestionJobStatus.INDEXED.value
            doc.error_message = None
            await session.commit()
            done += 1
            print(f"  OK   {doc.title[:60]!r}: {len(chunks)} chunk(s)")

        print(f"Done. {done} re-indexed, {failed} skipped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    asyncio.run(main(parser.parse_args().dry_run))
