"""Business logic service for Knowledge Bases, Document Ingestion, Semantic pgvector Search, and Knowledge Gap Resolution."""

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ChunkingStrategy, DocumentSourceType, IngestionJobStatus
from app.domains.ai.gemini_service import generate_gemini_response
from app.domains.rag.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    KnowledgeBase,
    KnowledgeGap,
)
from app.domains.rag.schemas import (
    DocumentCreate,
    KnowledgeBaseCreate,
    KnowledgeGapCreate,
    KnowledgeGapListResponse,
    KnowledgeGapResolveRequest,
    KnowledgeGapResponse,
)
from app.exceptions import ResourceNotFoundError

logger = logging.getLogger("rag_service")


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
                func.count(DocumentChunk.id).label("chunk_count"),
            )
            .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
            .where(
                Document.knowledge_base_id == kb_id,
                Document.organization_id == org_id,
                Document.is_deleted == False,
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

    # ==========================================================================
    # Knowledge Gap Detection & Resolution Engine
    # ==========================================================================

    @staticmethod
    def normalize_query(query: str) -> str:
        """Sanitize and normalize query string for deduplication and grouping."""
        cleaned = re.sub(r"[^\w\s]", "", query.lower())
        return " ".join(cleaned.split())[:500]

    @classmethod
    async def record_knowledge_gap(
        cls,
        session: AsyncSession,
        org_id: UUID,
        question: str,
        channel: str = "whatsapp",
        kb_id: Optional[UUID] = None,
    ) -> Optional[KnowledgeGap]:
        """Record an unanswered customer question or increment frequency count if recurring."""
        cleaned_q = question.strip()
        if len(cleaned_q) < 2:
            return None

        normalized = cls.normalize_query(cleaned_q)
        if not normalized:
            return None

        now = datetime.now(timezone.utc)

        # Check if gap already exists for this tenant & normalized query
        query = select(KnowledgeGap).where(
            KnowledgeGap.organization_id == org_id,
            KnowledgeGap.normalized_query == normalized,
        )
        res = await session.execute(query)
        gap = res.scalar_one_or_none()

        if gap:
            gap.frequency_count += 1
            gap.last_asked_at = now
            gap.channel = channel
            if kb_id and not gap.knowledge_base_id:
                gap.knowledge_base_id = kb_id
        else:
            gap = KnowledgeGap(
                organization_id=org_id,
                knowledge_base_id=kb_id,
                question=cleaned_q,
                normalized_query=normalized,
                channel=channel,
                frequency_count=1,
                status="unresolved",
                last_asked_at=now,
            )
            session.add(gap)

        await session.flush()
        return gap

    async def list_knowledge_gaps(
        self,
        org_id: UUID,
        status: Optional[str] = None,
        channel: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> KnowledgeGapListResponse:
        """List knowledge gaps with aggregate statistics for the organization."""
        base_conds = [KnowledgeGap.organization_id == org_id]
        if status and status != "all":
            base_conds.append(KnowledgeGap.status == status)
        if channel and channel != "all":
            base_conds.append(KnowledgeGap.channel == channel)

        # Query items
        q_items = (
            select(KnowledgeGap)
            .where(*base_conds)
            .order_by(KnowledgeGap.frequency_count.desc(), KnowledgeGap.last_asked_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res_items = await self.session.execute(q_items)
        items = res_items.scalars().all()

        # Aggregate counts
        q_counts = await self.session.execute(
            select(
                func.count(KnowledgeGap.id).label("total"),
                func.count(KnowledgeGap.id).filter(KnowledgeGap.status == "unresolved").label("unresolved"),
                func.count(KnowledgeGap.id).filter(KnowledgeGap.status == "resolved").label("resolved"),
                func.count(KnowledgeGap.id).filter(KnowledgeGap.status == "ignored").label("ignored"),
            ).where(KnowledgeGap.organization_id == org_id)
        )
        counts = q_counts.one()
        total = counts.total or 0
        resolved = counts.resolved or 0
        res_rate = round((resolved / total * 100), 1) if total > 0 else 0.0

        return KnowledgeGapListResponse(
            items=[KnowledgeGapResponse.model_validate(g) for g in items],
            total_count=total,
            unresolved_count=counts.unresolved or 0,
            resolved_count=resolved,
            ignored_count=counts.ignored or 0,
            resolution_rate=res_rate,
        )

    async def generate_gap_suggested_answer(self, org_id: UUID, gap_id: UUID) -> str:
        """Auto-generate an accurate, professional FAQ answer for this knowledge gap using Google Gemini."""
        gap = await self.session.get(KnowledgeGap, gap_id)
        if not gap or gap.organization_id != org_id:
            raise ResourceNotFoundError("KnowledgeGap", gap_id)

        system_prompt = (
            "You are an expert customer service knowledge editor for an AI customer operations platform. "
            "Write a concise, accurate, and polite 2-4 sentence official FAQ response "
            "answering the customer inquiry. Match the customer's language (Bengali or English)."
        )

        draft_answer = await generate_gemini_response(
            user_query=gap.question,
            system_prompt=system_prompt,
        )

        if not draft_answer:
            draft_answer = (
                f"Regarding your query on '{gap.question}': "
                "Our team provides full assistance for this. Please feel free to reach out to our representatives "
                "or consult our official guidelines for detailed assistance."
            )

        gap.suggested_answer = draft_answer.strip()
        await self.session.flush()
        return gap.suggested_answer

    async def resolve_knowledge_gap(
        self, org_id: UUID, gap_id: UUID, data: KnowledgeGapResolveRequest
    ) -> KnowledgeGap:
        """Ingest the verified answer into the Knowledge Base (pgvector) and mark the gap as resolved."""
        gap = await self.session.get(KnowledgeGap, gap_id)
        if not gap or gap.organization_id != org_id:
            raise ResourceNotFoundError("KnowledgeGap", gap_id)

        kb_id = data.knowledge_base_id or gap.knowledge_base_id
        if not kb_id:
            res_kb = await self.session.execute(
                select(KnowledgeBase.id)
                .where(KnowledgeBase.organization_id == org_id, KnowledgeBase.is_active.is_(True))
                .order_by(KnowledgeBase.created_at.desc())
                .limit(1)
            )
            kb_id = res_kb.scalar()

        if not kb_id:
            raise ResourceNotFoundError("KnowledgeBase", "Active Knowledge Base")

        # Ingest document
        doc_title = data.doc_title.strip() if data.doc_title else f"FAQ: {gap.question[:70]}"
        doc_create = DocumentCreate(
            title=doc_title,
            source_type=DocumentSourceType.MANUAL_ENTRY,
            source_uri=f"faq://gap/{gap.id}",
            raw_text=f"Q: {gap.question}\n\nA: {data.answer_text.strip()}",
            chunking_strategy=ChunkingStrategy.PARAGRAPH_AWARE,
        )
        doc = await self.ingest_document(org_id, kb_id, doc_create)

        # Mark gap as resolved
        gap.status = "resolved"
        gap.suggested_answer = data.answer_text.strip()
        gap.resolved_document_id = doc.id
        gap.knowledge_base_id = kb_id

        await self.session.flush()
        return gap

    async def update_gap_status(
        self, org_id: UUID, gap_id: UUID, new_status: str
    ) -> KnowledgeGap:
        """Update gap status (unresolved, resolved, ignored)."""
        gap = await self.session.get(KnowledgeGap, gap_id)
        if not gap or gap.organization_id != org_id:
            raise ResourceNotFoundError("KnowledgeGap", gap_id)

        gap.status = new_status
        await self.session.flush()
        return gap

    async def delete_knowledge_gap(self, org_id: UUID, gap_id: UUID) -> bool:
        """Delete a knowledge gap record."""
        gap = await self.session.get(KnowledgeGap, gap_id)
        if not gap or gap.organization_id != org_id:
            raise ResourceNotFoundError("KnowledgeGap", gap_id)

        await self.session.delete(gap)
        await self.session.flush()
        return True

    async def scan_inbox_for_gaps(self, org_id: UUID) -> int:
        """Scan recent contact messages from the inbox to discover questions lacking documentation."""
        q_msgs = await self.session.execute(
            text(
                """
                SELECT text_content
                FROM messages
                WHERE organization_id = :org_id AND sender_type = 'contact' AND length(text_content) > 8
                ORDER BY created_at DESC
                LIMIT 50;
                """
            ),
            {"org_id": org_id},
        )
        msgs = q_msgs.mappings().all()

        q_chunks = await self.session.execute(
            text(
                """
                SELECT content_text
                FROM document_chunks
                WHERE organization_id = :org_id
                LIMIT 50;
                """
            ),
            {"org_id": org_id},
        )
        chunks_text = " ".join([r["content_text"].lower() for r in q_chunks.mappings().all()])

        new_gaps_count = 0
        for m in msgs:
            text_content = m["text_content"].strip()
            words = [w.lower() for w in re.sub(r"[^\w\s]", "", text_content).split() if len(w) > 2]
            if not words:
                continue
            matched = sum(1 for w in words if w in chunks_text)
            if matched == 0 or (matched / len(words)) < 0.25:
                gap = await self.record_knowledge_gap(self.session, org_id, text_content, channel="inbox_scan")
                if gap and gap.frequency_count == 1:
                    new_gaps_count += 1

        return new_gaps_count
