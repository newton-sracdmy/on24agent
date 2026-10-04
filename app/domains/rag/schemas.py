"""Pydantic schemas for RAG, Knowledge Bases, and Document Ingestion."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import Field

from app.common.schemas import BaseSchema
from app.constants import ChunkingStrategy, DocumentSourceType, IngestionJobStatus, VectorDistanceMetric


class KnowledgeBaseCreate(BaseSchema):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    embedding_model_id: UUID
    distance_metric: VectorDistanceMetric = VectorDistanceMetric.COSINE


class KnowledgeBaseResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    name: str
    description: Optional[str] = None
    embedding_model_id: UUID
    distance_metric: str
    is_active: bool
    created_at: datetime


class DocumentCreate(BaseSchema):
    title: str = Field(..., min_length=1, max_length=255)
    source_type: DocumentSourceType = DocumentSourceType.FILE_UPLOAD
    source_uri: Optional[str] = None
    raw_text: str = Field(..., min_length=1)
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.PARAGRAPH_AWARE


class DocumentChunkResponse(BaseSchema):
    id: UUID
    chunk_index: int
    content_text: str
    token_count: int
    score: Optional[float] = None


class DocumentResponse(BaseSchema):
    id: UUID
    knowledge_base_id: UUID
    title: str
    source_type: str
    mime_type: str
    file_size_bytes: int
    status: str
    created_at: datetime


class SemanticSearchRequest(BaseSchema):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)
    score_threshold: Optional[float] = Field(0.7, ge=0.0, le=1.0)
