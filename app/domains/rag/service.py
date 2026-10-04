"""Business logic service for Knowledge Bases, Document Ingestion, and Semantic pgvector Search."""

import hashlib
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import IngestionJobStatus
from app.domains.rag.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    KnowledgeBase,
)
from app.domains.rag.schemas import DocumentCreate, KnowledgeBaseCreate
from app.exceptions import ResourceNotFoundError


class RAGService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_knowledge_base(
        self, org_id: UUID, data: KnowledgeBaseCreate
    ) -> KnowledgeBase:
        kb = KnowledgeBase(
            organization_id=org_id,
            name=data.name,
            description=data.description,
            embedding_model_id=data.embedding_model_id,
            distance_metric=data.distance_metric.value,
        )
        self.session.add(kb)
        await self.session.flush()
        return kb

    async def ingest_document(
        self, org_id: UUID, kb_id: UUID, data: DocumentCreate
    ) -> Document:
        kb = await self.session.get(KnowledgeBase, kb_id)
        if not kb or kb.organization_id != org_id:
            raise ResourceNotFoundError("KnowledgeBase", kb_id)

        doc = Document(
            organization_id=org_id,
            knowledge_base_id=kb_id,
            title=data.title,
            source_type=data.source_type.value,
            source_uri=data.source_uri,
            status=IngestionJobStatus.INDEXED.value,
            file_size_bytes=len(data.raw_text.encode("utf-8")),
        )
        self.session.add(doc)
        await self.session.flush()

        content_hash = hashlib.sha256(data.raw_text.encode("utf-8")).hexdigest()
        version = DocumentVersion(
            organization_id=org_id,
            document_id=doc.id,
            version_number=1,
            content_hash=content_hash,
            raw_text=data.raw_text,
        )
        self.session.add(version)
        await self.session.flush()

        # Paragraph-aware chunking
        paragraphs = [p.strip() for p in data.raw_text.split("\n\n") if p.strip()]
        for idx, para in enumerate(paragraphs):
            # 1536-dimensional mock embedding for default text-embedding-3-small
            mock_embedding = [0.0] * 1536
            mock_embedding[idx % 1536] = 1.0

            chunk = DocumentChunk(
                organization_id=org_id,
                document_id=doc.id,
                document_version_id=version.id,
                chunk_index=idx,
                content_text=para,
                token_count=len(para.split()),
                embedding=mock_embedding,
            )
            self.session.add(chunk)

        await self.session.flush()
        return doc

    async def vector_search(
        self, org_id: UUID, kb_id: UUID, query_embedding: List[float], top_k: int = 5
    ) -> List[dict]:
        """Perform sub-second vector similarity search using pgvector cosine distance."""
        query = (
            select(
                DocumentChunk.id,
                DocumentChunk.content_text,
                DocumentChunk.token_count,
                DocumentChunk.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.knowledge_base_id == kb_id,
                DocumentChunk.organization_id == org_id,
            )
            .order_by("distance")
            .limit(top_k)
        )
        res = await self.session.execute(query)
        hits = []
        for row in res.all():
            hits.append(
                {
                    "id": row.id,
                    "content_text": row.content_text,
                    "token_count": row.token_count,
                    "score": round(1.0 - float(row.distance), 4),
                }
            )
        return hits
