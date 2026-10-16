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


class KnowledgeGap(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Tracks customer questions that lacked sufficient knowledge base grounding."""
    __tablename__ = "knowledge_gaps"

    knowledge_base_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_query: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(50), default="whatsapp", nullable=False)
    frequency_count: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="unresolved", server_default=text("'unresolved'"), nullable=False, index=True
    )  # unresolved, resolved, ignored
    suggested_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_document_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    knowledge_base: Mapped[Optional["KnowledgeBase"]] = relationship("KnowledgeBase")
    resolved_document: Mapped[Optional["Document"]] = relationship("Document")

    __table_args__ = (
        Index("ix_knowledge_gaps_org_status", "organization_id", "status"),
        UniqueConstraint("organization_id", "normalized_query", name="uq_org_gap_query"),
    )

