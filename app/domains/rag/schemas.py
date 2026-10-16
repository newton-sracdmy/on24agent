"""Pydantic schemas for RAG, Knowledge Bases, and Document Ingestion."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import Field, field_validator

from app.common.schemas import BaseSchema
from app.constants import ChunkingStrategy, DocumentSourceType, IngestionJobStatus, VectorDistanceMetric


MAX_DOCUMENT_CHARS = 500_000


def _strip(v: Any) -> Any:
    return v.strip() if isinstance(v, str) else v


class KnowledgeBaseCreate(BaseSchema):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    # Omit to use the platform's default embedding model
    embedding_model_id: Optional[UUID] = None
    distance_metric: VectorDistanceMetric = VectorDistanceMetric.COSINE

    _strip_name = field_validator("name", mode="before")(_strip)


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
    source_uri: Optional[str] = Field(None, max_length=1024)
    raw_text: str = Field(..., min_length=1, max_length=MAX_DOCUMENT_CHARS)
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.PARAGRAPH_AWARE

    _strip_fields = field_validator("title", "raw_text", mode="before")(_strip)


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
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(5, ge=1, le=50)
    # Cosine similarity floor; relevant hits typically score 0.55-0.8 with the default embedding model
    score_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)

    _strip_query = field_validator("query", mode="before")(_strip)


# ==============================================================================
# Knowledge Gap Schemas
# ==============================================================================

class KnowledgeGapResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    knowledge_base_id: Optional[UUID] = None
    question: str
    normalized_query: str
    channel: str
    frequency_count: int
    status: str
    suggested_answer: Optional[str] = None
    resolved_document_id: Optional[UUID] = None
    last_asked_at: datetime
    created_at: datetime


class KnowledgeGapCreate(BaseSchema):
    question: str = Field(..., min_length=2, max_length=1000)
    channel: Optional[str] = Field("whatsapp", max_length=50)
    knowledge_base_id: Optional[UUID] = None

    _strip_question = field_validator("question", mode="before")(_strip)


class KnowledgeGapResolveRequest(BaseSchema):
    answer_text: str = Field(..., min_length=5, max_length=5000)
    doc_title: Optional[str] = Field(None, max_length=255)
    knowledge_base_id: Optional[UUID] = None

    _strip_fields = field_validator("answer_text", "doc_title", mode="before")(_strip)


class KnowledgeGapStatusUpdate(BaseSchema):
    status: str = Field(..., pattern="^(unresolved|resolved|ignored)$")


class KnowledgeGapListResponse(BaseSchema):
    items: List[KnowledgeGapResponse]
    total_count: int
    unresolved_count: int
    resolved_count: int
    ignored_count: int
    resolution_rate: float

