"""SQLAlchemy models for Subscription Plans, Pricing, Stripe Subscriptions, and Invoices."""

from datetime import datetime
from typing import Optional
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
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.constants import (
    BillingInterval,
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
