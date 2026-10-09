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

        src_type = data.source_type.value if hasattr(data.source_type, "value") else str(data.source_type)
        doc = Document(
            organization_id=org_id,
            knowledge_base_id=kb_id,
            title=data.title,
            source_type=src_type,
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

    async def list_documents(self, org_id: UUID, kb_id: UUID) -> List[dict]:
        """List all documents for a knowledge base with chunk count."""
        from sqlalchemy import func
        query = (
            select(
                Document.id,
                Document.knowledge_base_id,
                Document.title,
                Document.source_type,
                Document.mime_type,
                Document.file_size_bytes,
                Document.status,
                Document.created_at,
                func.count(DocumentChunk.id).label("chunk_count")
            )
            .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
            .where(
                Document.knowledge_base_id == kb_id,
                Document.organization_id == org_id,
                Document.is_deleted == False
            )
            .group_by(Document.id)
            .order_by(Document.created_at.desc())
        )
        res = await self.session.execute(query)
        docs = []
        for r in res.all():
            docs.append({
                "id": r.id,
                "knowledge_base_id": r.knowledge_base_id,
                "title": r.title,
                "source_type": r.source_type,
                "mime_type": r.mime_type,
                "file_size_bytes": r.file_size_bytes,
                "status": r.status,
                "created_at": r.created_at,
                "chunk_count": r.chunk_count,
            })
        return docs

    async def vector_search(
        self, org_id: UUID, kb_id: UUID, query_embedding: List[float], top_k: int = 5, query_text: Optional[str] = None
    ) -> List[dict]:
        """Perform semantic retrieval against knowledge base chunks using pgvector and keyword match."""
        query = (
            select(
                DocumentChunk.id,
                DocumentChunk.content_text,
                DocumentChunk.token_count,
                Document.title.label("document_title"),
                DocumentChunk.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.knowledge_base_id == kb_id,
                DocumentChunk.organization_id == org_id,
            )
        )
        res = await self.session.execute(query)
        all_chunks = res.all()

        scored_hits = []
        q_tokens = set(query_text.lower().split()) if query_text else set()

        for row in all_chunks:
            # Base vector score from cosine distance
            base_score = max(0.0, round(1.0 - float(row.distance or 0.5), 4))
            
            # Keyword relevance boost
            if q_tokens:
                text_lower = row.content_text.lower()
                matched_words = sum(1 for w in q_tokens if w in text_lower)
                if matched_words > 0:
                    boost = (matched_words / len(q_tokens)) * 0.5
                    base_score = min(0.99, base_score + boost)

            scored_hits.append({
                "id": row.id,
                "content_text": row.content_text,
                "token_count": row.token_count,
                "document_title": row.document_title,
                "score": round(base_score, 4),
            })

        scored_hits.sort(key=lambda x: x["score"], reverse=True)
        return scored_hits[:top_k]
