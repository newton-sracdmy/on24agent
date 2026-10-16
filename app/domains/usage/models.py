"""SQLAlchemy models for Double-Entry Credit Ledger, Materialized Balances, and Usage Aggregates."""

from typing import Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
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
