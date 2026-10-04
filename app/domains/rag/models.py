"""SQLAlchemy models for RAG, Knowledge Bases, Documents, pgvector Chunks, and Ingestion Jobs."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import (
    Base,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.constants import (
    ChunkingStrategy,
    DocumentSourceType,
    IngestionJobStatus,
    VectorDistanceMetric,
)


class KnowledgeBase(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Container for vector-searchable domain documents and grounding materials."""
    __tablename__ = "knowledge_bases"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    embedding_model_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("llm_models.id", ondelete="RESTRICT"),
        nullable=False,
    )
    distance_metric: Mapped[str] = mapped_column(
        String(50),
        default=VectorDistanceMetric.COSINE.value,
        server_default=text("'cosine'"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="knowledge_base", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_org_kb_name"),
    )


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, SoftDeleteMixin):
    """Source file, webpage, or article ingested into knowledge base."""
    __tablename__ = "documents"

    knowledge_base_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(50),
        default=DocumentSourceType.FILE_UPLOAD.value,
        server_default=text("'file_upload'"),
        nullable=False,
    )
    source_uri: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(100), default="text/plain", nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50),
        default=IngestionJobStatus.PENDING.value,
        server_default=text("'pending'"),
        nullable=False,
        index=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    knowledge_base: Mapped["KnowledgeBase"] = relationship("KnowledgeBase", back_populates="documents")
    versions: Mapped[List["DocumentVersion"]] = relationship(
        "DocumentVersion", back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Historical version of extracted document text content."""
    __tablename__ = "document_versions"

    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    document: Mapped["Document"] = relationship("Document", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_doc_version"),
    )


class DocumentChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Segmented text chunk with dense embedding vector for semantic search."""
    __tablename__ = "document_chunks"

    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding = mapped_column(Vector(1536), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_org_doc", "organization_id", "document_id"),
    )


class IngestionJob(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Async background worker job parsing, chunking, and embedding documents."""
    __tablename__ = "ingestion_jobs"

    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=IngestionJobStatus.PENDING.value,
        server_default=text("'pending'"),
        nullable=False,
    )
    chunking_strategy: Mapped[str] = mapped_column(
        String(50),
        default=ChunkingStrategy.PARAGRAPH_AWARE.value,
        server_default=text("'paragraph_aware'"),
        nullable=False,
    )
    chunk_size: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    errors: Mapped[List["IngestionError"]] = relationship(
        "IngestionError", back_populates="ingestion_job", cascade="all, delete-orphan"
    )


class IngestionError(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    __tablename__ = "ingestion_errors"

    ingestion_job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    error_phase: Mapped[str] = mapped_column(String(50), nullable=False)  # extraction, chunking, embedding
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    ingestion_job: Mapped["IngestionJob"] = relationship("IngestionJob", back_populates="errors")
