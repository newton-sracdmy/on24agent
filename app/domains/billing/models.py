"""SQLAlchemy models for Subscription Plans, Pricing, Stripe Subscriptions, and Invoices."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
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
from app.constants import (
    BillingInterval,
    InvoiceStatus,
    PlanTier,
    SubscriptionStatus,
)


class Plan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """System-level tier catalog (Free, Solo, Standard, Business, Enterprise)."""
    __tablename__ = "plans"

    tier: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    monthly_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    annual_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    included_monthly_credits: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    max_seats: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_channels: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    features: Mapped[List["PlanFeature"]] = relationship(
        "PlanFeature", back_populates="plan", cascade="all, delete-orphan"
    )


class PlanFeature(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "plan_features"

    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feature_key: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_value: Mapped[str] = mapped_column(String(100), default="true", nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    plan: Mapped["Plan"] = relationship("Plan", back_populates="features")

    __table_args__ = (
        UniqueConstraint("plan_id", "feature_key", name="uq_plan_feature"),
    )


class Subscription(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Active commercial subscription for a tenant workspace."""
    __tablename__ = "subscriptions"

    plan_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=SubscriptionStatus.ACTIVE.value,
        server_default=text("'active'"),
        nullable=False,
        index=True,
    )
    billing_interval: Mapped[str] = mapped_column(
        String(50),
        default=BillingInterval.MONTHLY.value,
        server_default=text("'monthly'"),
        nullable=False,
    )
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(100), unique=True, index=True, nullable=True
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)

    plan: Mapped["Plan"] = relationship("Plan")
    invoices: Mapped[List["Invoice"]] = relationship(
        "Invoice", back_populates="subscription", cascade="all, delete-orphan"
    )


class Invoice(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    __tablename__ = "invoices"

    subscription_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50),
        default=InvoiceStatus.PAID.value,
        server_default=text("'paid'"),
        nullable=False,
    )
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    tax: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    invoice_pdf_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    subscription: Mapped[Optional["Subscription"]] = relationship("Subscription", back_populates="invoices")
    items: Mapped[List["InvoiceItem"]] = relationship(
        "InvoiceItem", back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceItem(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    __tablename__ = "invoice_items"

    invoice_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="items")


class PaymentEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    __tablename__ = "payment_events"

    invoice_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
    )
    stripe_payment_intent_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    event_payload_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
