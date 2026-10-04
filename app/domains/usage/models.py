"""SQLAlchemy models for Double-Entry Credit Ledger, Materialized Balances, and Usage Aggregates."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.constants import CreditTransactionType


class CreditBalance(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Materialized snapshot of available tenant credits enforced with non-negative constraints."""
    __tablename__ = "credit_balances"

    balance_credits: Mapped[float] = mapped_column(
        Numeric(14, 4), default=0.0, server_default=text("0.0"), nullable=False
    )
    lifetime_granted_credits: Mapped[float] = mapped_column(
        Numeric(14, 4), default=0.0, server_default=text("0.0"), nullable=False
    )
    lifetime_consumed_credits: Mapped[float] = mapped_column(
        Numeric(14, 4), default=0.0, server_default=text("0.0"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_org_credit_balance"),
        CheckConstraint("balance_credits >= 0", name="chk_positive_credit_balance"),
    )


class CreditLedger(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Double-entry style financial transaction ledger tracking every credit deposit and burn."""
    __tablename__ = "credit_ledger"

    transaction_type: Mapped[str] = mapped_column(
        String(50),
        default=CreditTransactionType.SUBSCRIPTION_GRANT.value,
        server_default=text("'subscription_grant'"),
        nullable=False,
        index=True,
    )
    amount: Mapped[float] = mapped_column(
        Numeric(14, 4), nullable=False, comment="Positive for grants/purchases, negative for deductions"
    )
    balance_after: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, comment="E.g. agent_run_id, conversation_id, invoice_id"
    )
    reference_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="agent_run, voice_call, whatsapp_conversation"
    )

    __table_args__ = (
        Index("ix_credit_ledger_org_time", "organization_id", "created_at"),
    )


class UsageRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Raw usage metric datapoint (e.g. LLM tokens, TTS audio duration, API hits)."""
    __tablename__ = "usage_records"

    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    dimensions_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_usage_records_org_metric_time", "organization_id", "metric_name", "recorded_at"),
    )


class UsageAggregate(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Aggregated usage metrics roll-up for high-speed dashboard analytics and billing calculation."""
    __tablename__ = "usage_aggregates"

    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    period_type: Mapped[str] = mapped_column(String(20), default="daily", nullable=False)  # hourly, daily, monthly
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_quantity: Mapped[float] = mapped_column(Numeric(14, 4), default=0.0, nullable=False)
    total_cost: Mapped[float] = mapped_column(Numeric(14, 4), default=0.0, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "metric_name",
            "period_type",
            "period_start",
            name="uq_org_usage_aggregate",
        ),
    )
