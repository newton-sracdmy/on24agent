"""SQLAlchemy models for LLM Providers, Models, and Tenant Provider Configurations."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.constants import AIProviderType, ModelModality


class LLMProvider(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "llm_providers"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    api_base_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    models: Mapped[list["LLMModel"]] = relationship(
        "LLMModel", back_populates="provider", cascade="all, delete-orphan"
    )


class LLMModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "llm_models"

    provider_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("llm_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    modality: Mapped[str] = mapped_column(
        String(50),
        default=ModelModality.TEXT_ONLY.value,
        server_default=text("'text_only'"),
        nullable=False,
    )
    context_window: Mapped[int] = mapped_column(Integer, default=128000, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    input_token_cost_per_million: Mapped[float] = mapped_column(
        Numeric(10, 4), default=0.0, nullable=False
    )
    output_token_cost_per_million: Mapped[float] = mapped_column(
        Numeric(10, 4), default=0.0, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    provider: Mapped["LLMProvider"] = relationship("LLMProvider", back_populates="models")
