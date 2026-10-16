"""FastAPI router endpoints for Knowledge Bases, RAG retrieval, and Knowledge Gap Resolution."""

from typing import List, Optional
from uuid import UUID

import csv
import io

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common import llm_rate_limit
from app.common.schemas import APIResponse
from app.constants import ChunkingStrategy, DocumentSourceType
from app.dependencies import AuthenticatedUserContext, get_db, require_tenant
from app.domains.rag.models import KnowledgeBase
from app.domains.rag.schemas import (
    DocumentChunkResponse,
    DocumentCreate,
    DocumentResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeGapCreate,
    KnowledgeGapListResponse,
    KnowledgeGapResolveRequest,
    KnowledgeGapResponse,
    KnowledgeGapStatusUpdate,
    MAX_DOCUMENT_CHARS,
    SemanticSearchRequest,
)
from app.domains.rag.service import RAGService
from app.exceptions import GabsterException, ValidationError

router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
UPLOAD_MIME_TYPES = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md": "text/markdown",
    "csv": "text/csv",
}


# ==============================================================================
# Knowledge Gap Detection & Resolution Endpoints (Defined before /{kb_id})
# ==============================================================================

@router.get("/gaps", response_model=APIResponse[KnowledgeGapListResponse])
async def list_knowledge_gaps(
    status: str = Query("all", pattern="^(all|unresolved|resolved|ignored)$", description="Filter by status"),
    channel: str = Query("all", max_length=50, description="Filter by channel: whatsapp, messenger, instagram, all"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[KnowledgeGapListResponse]:
    """List customer questions lacking knowledge documentation, with aggregate resolution statistics."""
    service = RAGService(db)
    result = await service.list_knowledge_gaps(
        user_context.organization_id, status=status, channel=channel, limit=limit, offset=offset
    )
    return APIResponse.ok(data=result)


@router.post("/gaps/record", status_code=status.HTTP_201_CREATED, response_model=APIResponse[KnowledgeGapResponse])
async def record_knowledge_gap(
    payload: KnowledgeGapCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[KnowledgeGapResponse]:
    """Manually or programmatically register an unanswered customer question."""
    service = RAGService(db)
    if payload.knowledge_base_id:
        await service.get_knowledge_base(user_context.organization_id, payload.knowledge_base_id)
    gap, _ = await service.record_knowledge_gap(
        db,
        user_context.organization_id,
        question=payload.question,
        channel=payload.channel or "manual",
        kb_id=payload.knowledge_base_id,
    )
    if not gap:
        raise ValidationError("Question must contain at least one word")
    return APIResponse.ok(data=KnowledgeGapResponse.model_validate(gap))


@router.post("/gaps/scan", response_model=APIResponse[dict])
async def scan_inbox_for_gaps(
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[dict]:
    """Scan recent conversation history to automatically discover customer questions lacking answers."""
    await llm_rate_limit.ensure_llm_call_allowed(user_context.organization_id, "gap_scan")
    service = RAGService(db)
    discovered = await service.scan_inbox_for_gaps(user_context.organization_id)
    return APIResponse.ok(data={"discovered_gaps": discovered, "message": f"Scan completed. Discovered {discovered} new knowledge gap(s)."})


@router.post("/gaps/{gap_id}/suggest", response_model=APIResponse[dict])
async def generate_suggested_answer(
    gap_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[dict]:
    """Draft an AI-generated FAQ answer for this knowledge gap using Google Gemini."""
    await llm_rate_limit.ensure_llm_call_allowed(user_context.organization_id, "gap_suggest")
    service = RAGService(db)
    answer = await service.generate_gap_suggested_answer(user_context.organization_id, gap_id)
    return APIResponse.ok(data={"suggested_answer": answer})


@router.post("/gaps/{gap_id}/resolve", response_model=APIResponse[KnowledgeGapResponse])
async def resolve_knowledge_gap(
    gap_id: UUID,
    payload: KnowledgeGapResolveRequest,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[KnowledgeGapResponse]:
    """1-Click Ingestion: Automatically indexes the verified answer into pgvector and marks gap as resolved."""
    service = RAGService(db)
    gap = await service.resolve_knowledge_gap(user_context.organization_id, gap_id, payload)
    return APIResponse.ok(data=KnowledgeGapResponse.model_validate(gap))


@router.patch("/gaps/{gap_id}/status", response_model=APIResponse[KnowledgeGapResponse])
async def update_gap_status(
    gap_id: UUID,
    payload: KnowledgeGapStatusUpdate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[KnowledgeGapResponse]:
    """Update status of a knowledge gap (unresolved, resolved, ignored)."""
    service = RAGService(db)
    gap = await service.update_gap_status(user_context.organization_id, gap_id, payload.status)
    return APIResponse.ok(data=KnowledgeGapResponse.model_validate(gap))


@router.delete("/gaps/{gap_id}", response_model=APIResponse[dict])
async def delete_knowledge_gap(
    gap_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[dict]:
    """Delete a knowledge gap record."""
    service = RAGService(db)
    await service.delete_knowledge_gap(user_context.organization_id, gap_id)
    return APIResponse.ok(data={"message": "Knowledge gap successfully deleted."})


# ==============================================================================
# Knowledge Base Root Collection Endpoints
# ==============================================================================

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=APIResponse[KnowledgeBaseResponse])
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[KnowledgeBaseResponse]:
    """Create a new knowledge base collection."""
    service = RAGService(db)
    kb = await service.create_knowledge_base(user_context.organization_id, payload)
    return APIResponse.ok(data=KnowledgeBaseResponse.model_validate(kb))


@router.get("/", response_model=APIResponse[List[KnowledgeBaseResponse]])
async def list_knowledge_bases(
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[List[KnowledgeBaseResponse]]:
    """List knowledge bases in current workspace."""
    query = select(KnowledgeBase).where(KnowledgeBase.organization_id == user_context.organization_id)
    res = await db.execute(query)
    kbs = res.scalars().all()
    return APIResponse.ok(data=[KnowledgeBaseResponse.model_validate(k) for k in kbs])


# ==============================================================================
# Knowledge Base Document & Vector Endpoints
# ==============================================================================

@router.get("/{kb_id}/documents", response_model=APIResponse[List[dict]])
async def list_documents(
    kb_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[List[dict]]:
    """List documents for a given knowledge base."""
    service = RAGService(db)
    docs = await service.list_documents(user_context.organization_id, kb_id)
    return APIResponse.ok(data=docs)


@router.post("/{kb_id}/upload", status_code=status.HTTP_201_CREATED, response_model=APIResponse[DocumentResponse])
async def upload_document_file(
    kb_id: UUID,
    file: UploadFile = File(...),
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[DocumentResponse]:
    """Upload and ingest a document file (PDF, TXT, MD, CSV) into the knowledge base."""
    filename = (file.filename or "uploaded_document").strip()
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in UPLOAD_MIME_TYPES:
        raise GabsterException(
            f"Unsupported file type '.{ext}'. Allowed: {', '.join(sorted(UPLOAD_MIME_TYPES))}",
            code="UNSUPPORTED_MEDIA_TYPE",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    content_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content_bytes) > MAX_UPLOAD_BYTES:
        raise GabsterException(
            f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit",
            code="PAYLOAD_TOO_LARGE",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    extracted_text = await run_in_threadpool(_extract_text, ext, content_bytes)
    if not extracted_text:
        raise ValidationError("Document content is empty or unreadable (scanned PDFs need OCR first)")
    if len(extracted_text) > MAX_DOCUMENT_CHARS:
        raise GabsterException(
            f"Document text exceeds {MAX_DOCUMENT_CHARS:,} characters; please split it into smaller files",
            code="PAYLOAD_TOO_LARGE",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    service = RAGService(db)
    doc_create = DocumentCreate(
        title=filename[:255],
        source_type=DocumentSourceType.FILE_UPLOAD,
        source_uri=f"upload://{filename}"[:1024],
        raw_text=extracted_text,
        chunking_strategy=ChunkingStrategy.PARAGRAPH_AWARE,
    )
    doc = await service.ingest_document(
        user_context.organization_id, kb_id, doc_create, mime_type=UPLOAD_MIME_TYPES[ext]
    )
    return APIResponse.ok(data=DocumentResponse.model_validate(doc))


def _extract_text(ext: str, content: bytes) -> str:
    if ext == "pdf":
        import pypdf

        try:
            reader = pypdf.PdfReader(io.BytesIO(content))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception as e:
            raise ValidationError(f"Could not read PDF file: {e}")

    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("Text files must be UTF-8 encoded")

    if ext == "csv":
        # One paragraph per row with column labels, so each row becomes a self-describing chunk
        rows = list(csv.reader(io.StringIO(decoded)))
        if len(rows) < 2:
            return decoded.strip()
        header = [h.strip() for h in rows[0]]
        lines = []
        for row in rows[1:]:
            pairs = [f"{h}: {v.strip()}" for h, v in zip(header, row) if v.strip()]
            if pairs:
                lines.append("; ".join(pairs))
        return "\n\n".join(lines)
    return decoded.strip()


@router.post("/{kb_id}/documents", status_code=status.HTTP_201_CREATED, response_model=APIResponse[DocumentResponse])
async def ingest_document(
    kb_id: UUID,
    payload: DocumentCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[DocumentResponse]:
    """Ingest, parse, chunk, and embed a source document into the knowledge base."""
    service = RAGService(db)
    doc = await service.ingest_document(user_context.organization_id, kb_id, payload)
    return APIResponse.ok(data=DocumentResponse.model_validate(doc))


@router.post("/{kb_id}/search", response_model=APIResponse[List[dict]])
async def semantic_search(
    kb_id: UUID,
    payload: SemanticSearchRequest,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[List[dict]]:
    """Semantic (pgvector cosine) search over a knowledge base's chunks."""
    service = RAGService(db)
    hits = await service.search(
        user_context.organization_id, kb_id, payload.query, top_k=payload.top_k, score_threshold=payload.score_threshold
    )
    return APIResponse.ok(data=hits)


@router.delete("/{kb_id}/documents/{doc_id}", response_model=APIResponse[dict])
async def delete_document(
    kb_id: UUID,
    doc_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> APIResponse[dict]:
    """Delete a document and its vector chunks; bots stop using it immediately."""
    service = RAGService(db)
    await service.delete_document(user_context.organization_id, kb_id, doc_id)
    return APIResponse.ok(data={"message": "Document deleted."})
