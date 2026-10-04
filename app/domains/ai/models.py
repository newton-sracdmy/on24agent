"""SQLAlchemy models for LLM Providers, Models, and Tenant Provider Configurations."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import (
    Base,
    TenantMixin,
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


class ProviderConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Tenant-specific credentials for upstream AI providers (BYOK - Bring Your Own Key)."""
    __tablename__ = "provider_configs"

    provider_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("llm_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    custom_base_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    provider: Mapped["LLMProvider"] = relationship("LLMProvider")

    __table_args__ = (
        UniqueConstraint("organization_id", "provider_id", name="uq_org_provider_config"),
    )


class ModelConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Tenant-specific defaults for model selection and generation parameters."""
    __tablename__ = "model_configs"

    model_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("llm_models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_default_for_chat: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    is_default_for_voice: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    is_default_for_embedding: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    default_temperature: Mapped[float] = mapped_column(
        Float, default=0.7, server_default=text("0.7"), nullable=False
    )
    default_max_tokens: Mapped[int] = mapped_column(
        Integer, default=1024, server_default=text("1024"), nullable=False
    )

    model: Mapped["LLMModel"] = relationship("LLMModel")

    __table_args__ = (
        UniqueConstraint("organization_id", "model_id", name="uq_org_model_config"),
    )
