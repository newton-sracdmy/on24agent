"""FastAPI router endpoints for Knowledge Bases, RAG retrieval, and Knowledge Gap Resolution."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import APIResponse
from app.constants import ChunkingStrategy, DocumentSourceType
from app.dependencies import AuthenticatedUserContext, get_db, require_tenant
from app.domains.rag.models import Document, KnowledgeBase
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
    SemanticSearchRequest,
)
from app.domains.rag.service import RAGService

router = APIRouter()


# ==============================================================================
# Knowledge Gap Detection & Resolution Endpoints (Defined before /{kb_id})
# ==============================================================================

@router.get("/gaps", response_model=APIResponse[KnowledgeGapListResponse])
async def list_knowledge_gaps(
    status: Optional[str] = Query("all", description="Filter by status: unresolved, resolved, ignored, all"),
    channel: Optional[str] = Query("all", description="Filter by channel: whatsapp, messenger, instagram, all"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
) -> APIResponse[KnowledgeGapResponse]:
    """Manually or programmatically register an unanswered customer question."""
    service = RAGService(db)
    gap = await service.record_knowledge_gap(
        db,
        user_context.organization_id,
        question=payload.question,
        channel=payload.channel or "manual",
        kb_id=payload.knowledge_base_id,
    )
    if not gap:
        raise HTTPException(status_code=400, detail="Invalid question text.")
    return APIResponse.ok(data=KnowledgeGapResponse.model_validate(gap))


@router.post("/gaps/scan", response_model=APIResponse[dict])
async def scan_inbox_for_gaps(
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Scan recent conversation history to automatically discover customer questions lacking answers."""
    service = RAGService(db)
    discovered = await service.scan_inbox_for_gaps(user_context.organization_id)
    return APIResponse.ok(data={"discovered_gaps": discovered, "message": f"Scan completed. Discovered {discovered} new knowledge gap(s)."})


@router.post("/gaps/{gap_id}/suggest", response_model=APIResponse[dict])
async def generate_suggested_answer(
    gap_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Draft an AI-generated FAQ answer for this knowledge gap using Google Gemini."""
    service = RAGService(db)
    answer = await service.generate_gap_suggested_answer(user_context.organization_id, gap_id)
    return APIResponse.ok(data={"suggested_answer": answer})


@router.post("/gaps/{gap_id}/resolve", response_model=APIResponse[KnowledgeGapResponse])
async def resolve_knowledge_gap(
    gap_id: UUID,
    payload: KnowledgeGapResolveRequest,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
) -> APIResponse[KnowledgeGapResponse]:
    """Update status of a knowledge gap (unresolved, resolved, ignored)."""
    service = RAGService(db)
    gap = await service.update_gap_status(user_context.organization_id, gap_id, payload.status)
    return APIResponse.ok(data=KnowledgeGapResponse.model_validate(gap))


@router.delete("/gaps/{gap_id}", response_model=APIResponse[dict])
async def delete_knowledge_gap(
    gap_id: UUID,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
) -> APIResponse[KnowledgeBaseResponse]:
    """Create a new knowledge base collection."""
    service = RAGService(db)
    kb = await service.create_knowledge_base(user_context.organization_id, payload)
    return APIResponse.ok(data=KnowledgeBaseResponse.model_validate(kb))


@router.get("/", response_model=APIResponse[List[KnowledgeBaseResponse]])
async def list_knowledge_bases(
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
) -> APIResponse[DocumentResponse]:
    """Upload and ingest a document file (PDF, TXT, MD, CSV) into the knowledge base."""
    content_bytes = await file.read()
    filename = file.filename or "uploaded_document"
    ext = filename.lower().split(".")[-1]

    extracted_text = ""
    if ext == "pdf":
        try:
            import io
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content_bytes))
            extracted_text = "\n\n".join([page.extract_text() or "" for page in reader.pages]).strip()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse PDF file: {str(e)}")
    else:
        extracted_text = content_bytes.decode("utf-8", errors="ignore").strip()

    if not extracted_text:
        raise HTTPException(status_code=400, detail="Document content is empty or unreadable.")

    service = RAGService(db)
    doc_create = DocumentCreate(
        title=filename,
        source_type=DocumentSourceType.FILE_UPLOAD,
        source_uri=f"upload://{filename}",
        raw_text=extracted_text,
        chunking_strategy=ChunkingStrategy.PARAGRAPH_AWARE,
    )
    doc = await service.ingest_document(user_context.organization_id, kb_id, doc_create)
    return APIResponse.ok(data=DocumentResponse.model_validate(doc))


@router.post("/{kb_id}/documents", status_code=status.HTTP_201_CREATED, response_model=APIResponse[DocumentResponse])
async def ingest_document(
    kb_id: UUID,
    payload: DocumentCreate,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
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
    db: AsyncSession = Depends(get_db),
) -> APIResponse[List[dict]]:
    """Perform dense vector retrieval against knowledge base chunks using pgvector."""
    service = RAGService(db)
    mock_query_embedding = [0.0] * 1536
    mock_query_embedding[0] = 1.0
    hits = await service.vector_search(
        user_context.organization_id, kb_id, mock_query_embedding, top_k=payload.top_k, query_text=payload.query
    )
    return APIResponse.ok(data=hits)
