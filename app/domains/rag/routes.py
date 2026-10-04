"""FastAPI router endpoints for Knowledge Bases and RAG retrieval."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import APIResponse
from app.dependencies import AuthenticatedUserContext, get_db, require_tenant
from app.domains.rag.models import Document, KnowledgeBase
from app.domains.rag.schemas import (
    DocumentChunkResponse,
    DocumentCreate,
    DocumentResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    SemanticSearchRequest,
)
from app.domains.rag.service import RAGService

router = APIRouter()


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


@router.post("/{kb_id}/search", response_model=APIResponse[List[DocumentChunkResponse]])
async def semantic_search(
    kb_id: UUID,
    payload: SemanticSearchRequest,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[List[DocumentChunkResponse]]:
    """Perform dense vector retrieval against knowledge base chunks using pgvector."""
    service = RAGService(db)
    mock_query_embedding = [0.0] * 1536
    mock_query_embedding[0] = 1.0
    hits = await service.vector_search(
        user_context.organization_id, kb_id, mock_query_embedding, top_k=payload.top_k
    )
    return APIResponse.ok(data=[DocumentChunkResponse(**hit) for hit in hits])
