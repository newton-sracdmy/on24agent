"""Business logic service for Knowledge Bases, Document Ingestion, Semantic pgvector Search, and Knowledge Gap Resolution."""

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import enum_value
from app.constants import ChunkingStrategy, DocumentSourceType, IngestionJobStatus
from app.domains.ai.embedding_service import EMBEDDING_MODEL, embed_query, embed_texts
from app.domains.ai.gemini_service import generate_gemini_response
from app.domains.ai.models import LLMModel
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
    KnowledgeGapListResponse,
    KnowledgeGapResolveRequest,
    KnowledgeGapResponse,
)
from app.exceptions import AIProviderError, ResourceConflictError, ResourceNotFoundError, ValidationError

logger = logging.getLogger("rag_service")

# Chunks above this are split on sentence boundaries; keeps each embedding focused on one topic
CHUNK_MAX_WORDS = 180
# Paragraphs this short (headings, labels) are merged into the following paragraph
CHUNK_MERGE_BELOW_WORDS = 8
# Retrieval similarity below this, with no LLM verdict available, counts as "not covered by the KB"
GAP_FALLBACK_SIMILARITY = 0.55
DEFAULT_FAQ_KB_NAME = "Resolved FAQs"

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+")
_QUESTION_WORDS = {
    "what", "how", "when", "where", "why", "who", "which", "do", "does", "did", "can", "could", "is", "are",
    "will", "would", "should", "any", "price", "cost",
    "কি", "কী", "কত", "কেন", "কোথায়", "কখন", "কিভাবে", "কীভাবে", "কোন", "কে", "আছে", "পাবো", "যাবে", "দাম",
}


def chunk_text(raw_text: str) -> List[str]:
    """Paragraph-aware chunking with a hard size cap so no chunk exceeds CHUNK_MAX_WORDS."""
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", normalized) if p.strip()]

    merged: List[str] = []
    pending = ""
    for para in paragraphs:
        para = f"{pending}\n{para}" if pending else para
        pending = ""
        if len(para.split()) < CHUNK_MERGE_BELOW_WORDS:
            pending = para
        else:
            merged.append(para)
    if pending:
        merged.append(pending)

    chunks: List[str] = []
    for para in merged:
        if len(para.split()) <= CHUNK_MAX_WORDS:
            chunks.append(para)
            continue
        current: List[str] = []
        for sentence in _SENTENCE_SPLIT_RE.split(para):
            words = sentence.split()
            # A single run-on "sentence" longer than the cap is split on word boundaries
            while len(words) > CHUNK_MAX_WORDS:
                if current:
                    chunks.append(" ".join(current))
                    current = []
                chunks.append(" ".join(words[:CHUNK_MAX_WORDS]))
                words = words[CHUNK_MAX_WORDS:]
            if len(current) + len(words) > CHUNK_MAX_WORDS:
                chunks.append(" ".join(current))
                current = []
            current.extend(words)
        if current:
            chunks.append(" ".join(current))
    return chunks


def _tokens(value: str) -> List[str]:
    return [t for t in RAGService.normalize_query(value).split() if len(t) > 1]


def is_question_like(message: str) -> bool:
    """Cheap filter so greetings and thanks are not logged as knowledge gaps."""
    if "?" in message or "？" in message:
        return True
    return any(t in _QUESTION_WORDS for t in _tokens(message))


@dataclass
class RetrievalResult:
    chunks: List[dict] = field(default_factory=list)  # {"id", "title", "content_text", "token_count", "score"}
    # Best cosine similarity, or None when retrieval fell back to keyword matching
    top_score: Optional[float] = None

    def as_context(self) -> str:
        return "\n\n".join(f"[{c['title']}]: {c['content_text']}" for c in self.chunks)


class RAGService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ==========================================================================
    # Knowledge Bases & Documents
    # ==========================================================================

    async def _default_embedding_model_id(self) -> UUID:
        res = await self.session.execute(
            select(LLMModel.id).where(LLMModel.model_identifier == EMBEDDING_MODEL)
        )
        model_id = res.scalar()
        if not model_id:
            raise ResourceNotFoundError("LLMModel", EMBEDDING_MODEL)
        return model_id

    async def create_knowledge_base(
        self, org_id: UUID, data: KnowledgeBaseCreate
    ) -> KnowledgeBase:
        if data.embedding_model_id:
            if not await self.session.get(LLMModel, data.embedding_model_id):
                raise ValidationError(f"Unknown embedding_model_id {data.embedding_model_id}")
            model_id = data.embedding_model_id
        else:
            model_id = await self._default_embedding_model_id()

        existing = await self.session.execute(
            select(KnowledgeBase.id).where(KnowledgeBase.organization_id == org_id, KnowledgeBase.name == data.name)
        )
        if existing.first():
            raise ResourceConflictError(f"A knowledge base named '{data.name}' already exists")

        kb = KnowledgeBase(
            organization_id=org_id,
            name=data.name,
            description=data.description,
            embedding_model_id=model_id,
            distance_metric=enum_value(data.distance_metric),
        )
        self.session.add(kb)
        await self.session.flush()
        return kb

    async def get_knowledge_base(self, org_id: UUID, kb_id: UUID) -> KnowledgeBase:
        kb = await self.session.get(KnowledgeBase, kb_id)
        if not kb or kb.organization_id != org_id:
            raise ResourceNotFoundError("KnowledgeBase", kb_id)
        return kb

    async def ingest_document(
        self, org_id: UUID, kb_id: UUID, data: DocumentCreate, mime_type: str = "text/plain"
    ) -> Document:
        await self.get_knowledge_base(org_id, kb_id)

        chunks = chunk_text(data.raw_text)
        if not chunks:
            raise ValidationError("Document has no readable text content")

        # Embed before writing anything so a provider outage never leaves half-written rows
        embeddings = await embed_texts([f"{data.title}\n{c}" for c in chunks])

        src_type = data.source_type.value if hasattr(data.source_type, "value") else str(data.source_type)
        doc = Document(
            organization_id=org_id,
            knowledge_base_id=kb_id,
            title=data.title,
            source_type=src_type,
            source_uri=data.source_uri,
            mime_type=mime_type,
            status=IngestionJobStatus.INDEXED.value if embeddings else IngestionJobStatus.PENDING.value,
            error_message=None if embeddings else "Embedding provider unavailable; keyword search only until re-indexed",
            file_size_bytes=len(data.raw_text.encode("utf-8")),
        )
        self.session.add(doc)
        await self.session.flush()

        version = DocumentVersion(
            organization_id=org_id,
            document_id=doc.id,
            version_number=1,
            content_hash=hashlib.sha256(data.raw_text.encode("utf-8")).hexdigest(),
            raw_text=data.raw_text,
        )
        self.session.add(version)
        await self.session.flush()

        for idx, content in enumerate(chunks):
            self.session.add(
                DocumentChunk(
                    organization_id=org_id,
                    document_id=doc.id,
                    document_version_id=version.id,
                    chunk_index=idx,
                    content_text=content,
                    token_count=len(content.split()),
                    embedding=embeddings[idx] if embeddings else None,
                    metadata_json={"embedding_model": EMBEDDING_MODEL} if embeddings else {},
                )
            )

        await self.session.flush()
        return doc

    async def delete_document(self, org_id: UUID, kb_id: UUID, doc_id: UUID) -> None:
        """Hard-delete a document and its chunks so bots stop using it immediately."""
        doc = await self.session.get(Document, doc_id)
        if not doc or doc.organization_id != org_id or doc.knowledge_base_id != kb_id:
            raise ResourceNotFoundError("Document", doc_id)

        # Gaps answered by this document are no longer answered
        await self.session.execute(
            update(KnowledgeGap)
            .where(KnowledgeGap.organization_id == org_id, KnowledgeGap.resolved_document_id == doc_id)
            .values(status="unresolved", resolved_document_id=None)
        )
        await self.session.execute(delete(Document).where(Document.id == doc_id))
        await self.session.flush()

    async def list_documents(self, org_id: UUID, kb_id: UUID) -> List[dict]:
        """List all documents for a knowledge base with chunk count."""
        await self.get_knowledge_base(org_id, kb_id)
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
                Document.is_deleted.is_(False),
            )
            .group_by(Document.id)
            .order_by(Document.created_at.desc())
        )
        res = await self.session.execute(query)
        return [dict(r._mapping) for r in res.all()]

    # ==========================================================================
    # Retrieval
    # ==========================================================================

    @staticmethod
    async def retrieve_context(
        session: AsyncSession,
        org_id: UUID,
        query: str,
        top_k: int = 8,
        kb_id: Optional[UUID] = None,
    ) -> RetrievalResult:
        """Return the chunks most relevant to `query` from the org's active knowledge bases.

        Uses pgvector cosine search; falls back to keyword overlap when the query cannot be
        embedded or no chunks have embeddings yet.
        """
        base_filters = [
            DocumentChunk.organization_id == org_id,
            Document.is_deleted.is_(False),
            Document.status != IngestionJobStatus.FAILED.value,
            KnowledgeBase.is_active.is_(True),
        ]
        if kb_id:
            base_filters.append(Document.knowledge_base_id == kb_id)

        query_vector = await embed_query(query)
        if query_vector:
            # Keep scanning the HNSW index until enough rows survive the tenant filter
            await session.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed_order'"))
            distance = DocumentChunk.embedding.cosine_distance(query_vector)
            res = await session.execute(
                select(
                    DocumentChunk.id, DocumentChunk.content_text, DocumentChunk.token_count,
                    Document.title, distance.label("distance"),
                )
                .join(Document, Document.id == DocumentChunk.document_id)
                .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
                .where(
                    *base_filters,
                    DocumentChunk.embedding.is_not(None),
                    DocumentChunk.metadata_json["embedding_model"].astext == EMBEDDING_MODEL,
                )
                .order_by(distance)
                .limit(top_k)
            )
            rows = res.all()
            if rows:
                chunks = [
                    {"id": r.id, "title": r.title, "content_text": r.content_text, "token_count": r.token_count,
                     "score": round(max(0.0, 1.0 - float(r.distance)), 4)}
                    for r in rows
                ]
                return RetrievalResult(chunks=chunks, top_score=chunks[0]["score"])

        # Keyword fallback
        q_tokens = set(_tokens(query))
        res = await session.execute(
            select(DocumentChunk.id, DocumentChunk.content_text, DocumentChunk.token_count, Document.title)
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .where(*base_filters)
            .order_by(DocumentChunk.created_at.desc())
            .limit(2000)
        )
        scored = []
        for r in res.all():
            chunk_tokens = set(_tokens(r.content_text))
            overlap = len(q_tokens & chunk_tokens) / len(q_tokens) if q_tokens else 0.0
            if overlap > 0:
                scored.append({"id": r.id, "title": r.title, "content_text": r.content_text,
                               "token_count": r.token_count, "score": round(overlap, 4)})
        scored.sort(key=lambda c: c["score"], reverse=True)
        return RetrievalResult(chunks=scored[:top_k], top_score=None)

    async def search(
        self, org_id: UUID, kb_id: UUID, query: str, top_k: int = 5, score_threshold: Optional[float] = None
    ) -> List[dict]:
        """Semantic search within one knowledge base."""
        await self.get_knowledge_base(org_id, kb_id)
        result = await self.retrieve_context(self.session, org_id, query, top_k=top_k, kb_id=kb_id)
        hits = [
            {"id": c["id"], "content_text": c["content_text"], "token_count": c["token_count"],
             "document_title": c["title"], "score": c["score"],
             "match_type": "semantic" if result.top_score is not None else "keyword"}
            for c in result.chunks
        ]
        if score_threshold is not None:
            hits = [h for h in hits if h["score"] >= score_threshold]
        return hits

    # ==========================================================================
    # Knowledge Gap Detection & Resolution Engine
    # ==========================================================================

    @staticmethod
    def normalize_query(query: str) -> str:
        """Lowercase and drop punctuation/symbols for deduplication.

        Removes characters by Unicode category instead of `[^\\w\\s]`, which also stripped
        Bengali vowel signs (দাম -> দম) and merged unrelated questions.
        """
        lowered = unicodedata.normalize("NFC", query.lower())
        cleaned = "".join(" " if unicodedata.category(ch)[0] in ("P", "S") else ch for ch in lowered)
        return " ".join(cleaned.split())[:500]

    @staticmethod
    def should_record_gap(message: str, kb_covered: Optional[bool], retrieval: RetrievalResult) -> bool:
        """Decide whether an inbound customer message exposed missing knowledge."""
        if kb_covered is not None:
            # The model judged coverage and was told to ignore greetings/small talk
            return not kb_covered
        if not is_question_like(message):
            return False
        if retrieval.top_score is None:
            # Keyword fallback: only a total miss counts
            return not retrieval.chunks
        return retrieval.top_score < GAP_FALLBACK_SIMILARITY

    @classmethod
    async def record_knowledge_gap(
        cls,
        session: AsyncSession,
        org_id: UUID,
        question: str,
        channel: str = "whatsapp",
        kb_id: Optional[UUID] = None,
        count_repeat: bool = True,
    ) -> Tuple[Optional[KnowledgeGap], bool]:
        """Record an unanswered question, or bump its frequency if already known.

        Uses an upsert so concurrent webhooks for the same question cannot collide on the
        unique constraint. Returns (gap, created).
        """
        cleaned_q = question.strip()[:1000]
        normalized = cls.normalize_query(cleaned_q)
        if len(cleaned_q) < 2 or not normalized:
            return None, False

        now = datetime.now(timezone.utc)
        table = KnowledgeGap.__table__
        stmt = pg_insert(KnowledgeGap).values(
            organization_id=org_id,
            knowledge_base_id=kb_id,
            question=cleaned_q,
            normalized_query=normalized,
            channel=channel[:50],
            frequency_count=1,
            status="unresolved",
            last_asked_at=now,
        )
        if count_repeat:
            stmt = stmt.on_conflict_do_update(
                constraint="uq_org_gap_query",
                set_={
                    "frequency_count": table.c.frequency_count + 1,
                    "last_asked_at": now,
                    "channel": channel[:50],
                    "knowledge_base_id": func.coalesce(table.c.knowledge_base_id, kb_id),
                },
            )
        else:
            stmt = stmt.on_conflict_do_nothing(constraint="uq_org_gap_query")
        res = await session.execute(stmt.returning(KnowledgeGap.id, KnowledgeGap.frequency_count))
        row = res.first()

        if row:
            gap_id, created = row.id, row.frequency_count == 1
        else:
            existing = await session.execute(
                select(KnowledgeGap.id).where(
                    KnowledgeGap.organization_id == org_id, KnowledgeGap.normalized_query == normalized
                )
            )
            gap_id, created = existing.scalar_one(), False

        gap = await session.get(KnowledgeGap, gap_id, populate_existing=True)
        return gap, created

    async def get_gap(self, org_id: UUID, gap_id: UUID) -> KnowledgeGap:
        gap = await self.session.get(KnowledgeGap, gap_id)
        if not gap or gap.organization_id != org_id:
            raise ResourceNotFoundError("KnowledgeGap", gap_id)
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

        q_items = (
            select(KnowledgeGap)
            .where(*base_conds)
            .order_by(KnowledgeGap.frequency_count.desc(), KnowledgeGap.last_asked_at.desc(), KnowledgeGap.id)
            .limit(limit)
            .offset(offset)
        )
        items = (await self.session.execute(q_items)).scalars().all()

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
        """Draft an FAQ answer grounded in the org's knowledge base, with placeholders for unknown facts."""
        gap = await self.get_gap(org_id, gap_id)
        retrieval = await self.retrieve_context(self.session, org_id, gap.question, top_k=5)

        system_prompt = (
            "You are a knowledge editor drafting an official FAQ answer for a business owner to review. "
            "Write a concise, polite 2-4 sentence answer to the customer question in the customer's language "
            "(Bengali or English). Use ONLY facts found in the knowledge base context. Where a needed fact "
            "(price, date, policy, location, yes/no availability) is not in the context, insert a clear "
            "placeholder in square brackets such as [price] or [yes/no] for the owner to fill in. "
            "Never guess or invent facts, and never say whether something is or is not offered unless the "
            "context states it; write the sentence around a placeholder instead "
            "(e.g. 'Gift cards are [available/not available] ...')."
        )
        draft_answer = await generate_gemini_response(
            user_query=gap.question,
            system_prompt=system_prompt,
            kb_context=retrieval.as_context(),
        )
        if not draft_answer:
            raise AIProviderError("gemini", "Could not draft an answer right now. Please try again shortly.")

        gap.suggested_answer = draft_answer.strip()
        await self.session.flush()
        return gap.suggested_answer

    async def _get_or_create_faq_kb(self, org_id: UUID) -> UUID:
        res = await self.session.execute(
            select(KnowledgeBase.id)
            .where(KnowledgeBase.organization_id == org_id, KnowledgeBase.is_active.is_(True))
            .order_by(KnowledgeBase.created_at.desc())
            .limit(1)
        )
        kb_id = res.scalar()
        if kb_id:
            return kb_id
        kb = KnowledgeBase(
            organization_id=org_id,
            name=DEFAULT_FAQ_KB_NAME,
            description="Answers added from Knowledge Gap resolution",
            embedding_model_id=await self._default_embedding_model_id(),
        )
        self.session.add(kb)
        await self.session.flush()
        return kb.id

    async def resolve_knowledge_gap(
        self, org_id: UUID, gap_id: UUID, data: KnowledgeGapResolveRequest
    ) -> KnowledgeGap:
        """Ingest the verified answer into the Knowledge Base (pgvector) and mark the gap as resolved.

        Re-resolving replaces the previous FAQ document instead of adding a conflicting one.
        """
        gap = await self.get_gap(org_id, gap_id)

        if data.knowledge_base_id:
            kb_id = (await self.get_knowledge_base(org_id, data.knowledge_base_id)).id
        elif gap.knowledge_base_id:
            kb_id = gap.knowledge_base_id
        else:
            kb_id = await self._get_or_create_faq_kb(org_id)

        previous_doc_id = gap.resolved_document_id

        doc_title = data.doc_title or f"FAQ: {gap.question[:240]}"
        doc_create = DocumentCreate(
            title=doc_title,
            source_type=DocumentSourceType.MANUAL_ENTRY,
            source_uri=f"faq://gap/{gap.id}",
            # Single newline keeps question and answer in one chunk so retrieval returns both
            raw_text=f"Q: {gap.question}\nA: {data.answer_text}",
            chunking_strategy=ChunkingStrategy.PARAGRAPH_AWARE,
        )
        doc = await self.ingest_document(org_id, kb_id, doc_create)

        if previous_doc_id:
            await self.session.execute(
                delete(Document).where(Document.id == previous_doc_id, Document.organization_id == org_id)
            )

        gap.status = "resolved"
        gap.suggested_answer = data.answer_text
        gap.resolved_document_id = doc.id
        gap.knowledge_base_id = kb_id

        await self.session.flush()
        await self.session.refresh(gap)
        return gap

    async def update_gap_status(
        self, org_id: UUID, gap_id: UUID, new_status: str
    ) -> KnowledgeGap:
        """Update gap status (unresolved, resolved, ignored)."""
        gap = await self.get_gap(org_id, gap_id)
        gap.status = new_status
        await self.session.flush()
        return gap

    async def delete_knowledge_gap(self, org_id: UUID, gap_id: UUID) -> bool:
        """Delete a knowledge gap record."""
        gap = await self.get_gap(org_id, gap_id)
        await self.session.delete(gap)
        await self.session.flush()
        return True

    async def scan_inbox_for_gaps(self, org_id: UUID) -> int:
        """Scan recent customer questions and record those the knowledge base cannot answer.

        Each question is checked against its own retrieved chunks by the LLM; if the LLM is
        unavailable, a conservative similarity threshold is used instead. Re-scanning the same
        messages does not inflate frequency counts.
        """
        q_msgs = await self.session.execute(
            text(
                """
                SELECT DISTINCT ON (lower(text_content)) text_content
                FROM messages
                WHERE organization_id = :org_id AND sender_type = 'contact' AND length(text_content) > 8
                ORDER BY lower(text_content), created_at DESC
                LIMIT 200;
                """
            ),
            {"org_id": org_id},
        )
        questions = [m["text_content"].strip() for m in q_msgs.mappings().all()]
        questions = [q for q in questions if is_question_like(q)][:50]
        if not questions:
            return 0

        retrievals = [await self.retrieve_context(self.session, org_id, q, top_k=3) for q in questions]
        verdicts = await self._judge_coverage(questions, retrievals)

        new_gaps_count = 0
        for question, retrieval, covered in zip(questions, retrievals, verdicts):
            if self.should_record_gap(question, covered, retrieval):
                _, created = await self.record_knowledge_gap(
                    self.session, org_id, question, channel="inbox_scan", count_repeat=False
                )
                new_gaps_count += int(created)
        return new_gaps_count

    @staticmethod
    async def _judge_coverage(questions: List[str], retrievals: List[RetrievalResult]) -> List[Optional[bool]]:
        """Ask the LLM, in one call, whether each question is answered by its retrieved context."""
        items = [
            {"i": i, "question": q, "context": [c["content_text"][:600] for c in r.chunks]}
            for i, (q, r) in enumerate(zip(questions, retrievals))
        ]
        reply = await generate_gemini_response(
            user_query=json.dumps(items, ensure_ascii=False),
            system_prompt=(
                "You audit a customer-support knowledge base. For each item, decide whether its 'context' "
                "contains the facts needed to answer its 'question'. Respond ONLY with a JSON array of booleans "
                "in item order, e.g. [true,false]. No prose."
            ),
        )
        if reply:
            match = re.search(r"\[[\s\S]*\]", reply)
            try:
                verdicts = json.loads(match.group(0)) if match else None
                if isinstance(verdicts, list) and len(verdicts) == len(questions):
                    return [bool(v) for v in verdicts]
            except ValueError:
                pass
            logger.warning("Coverage judgement returned unparseable output; using similarity fallback.")
        return [None] * len(questions)
