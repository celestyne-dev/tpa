"""Membership plans, prices and included products (Batch 10.1).

Batch 10.2 adds the provider plan for each price (``membership_provider_plans``), customer
subscriptions, their billing periods and an append-only event history. A subscription
becomes ``active`` only after its first payment is verified with the provider.

A plan is a membership tier (``tier_rank`` orders tiers for future upgrades and
downgrades). Its prices are append-only: a price row is never edited, so a price a
customer has seen (and, from Batch 10.2, subscribed at) never changes; a new price
replaces it by retiring the old row. ``membership_plan_access`` lists the products
(premium resources and course products) a plan unlocks; each must be marked
``membership_eligible``. Nothing here grants entitlements or takes payment yet.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .base import TimestampMixin
from .types import JSONType, UTCDateTime, utcnow

PLAN_STATUSES = ("draft", "published", "archived")
PRICE_INTERVALS = ("month", "year")
PRICE_STATUSES = ("active", "retired")
SUBSCRIPTION_STATUSES = ("pending", "active", "past_due", "grace", "incomplete", "ended")
# A customer has at most one subscription in these states (partial unique index).
LIVE_SUBSCRIPTION_STATUSES = ("pending", "active", "past_due", "grace")
PERIOD_STATUSES = ("pending", "paid", "failed", "refunded", "void")
EVENT_SOURCES = ("customer", "webhook", "verification", "admin", "job", "system")


class MembershipPlan(TimestampMixin, db.Model):
    __tablename__ = "membership_plans"
    __table_args__ = (
        CheckConstraint(f"status IN {PLAN_STATUSES}", name="status_valid"),
        CheckConstraint("tier_rank > 0", name="tier_rank_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    tagline: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    # Plain text; blank lines separate paragraphs.
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    benefits: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    # 1 = the first paid tier; higher ranks are higher tiers (future upgrades/downgrades).
    tier_rank: Mapped[int] = mapped_column(unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    first_published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    lock_version: Mapped[int] = mapped_column(default=1, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Batch 10.2: hidden backing product (type "membership") so subscription payments use
    # the existing orders, receipts and refunds. Never sold through the cart.
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=True
    )

    prices: Mapped[list[MembershipPlanPrice]] = relationship(
        back_populates="plan", order_by="MembershipPlanPrice.id", cascade="all, delete-orphan"
    )
    access: Mapped[list[MembershipPlanAccess]] = relationship(
        back_populates="plan", order_by="MembershipPlanAccess.id", cascade="all, delete-orphan"
    )

    @property
    def active_prices(self) -> list[MembershipPlanPrice]:
        return [p for p in self.prices if p.status == "active"]


class MembershipPlanPrice(db.Model):
    """Immutable: amounts are never edited. ``shown_at`` marks a price that has been
    public (published plan); such prices can only be retired, never deleted."""

    __tablename__ = "membership_plan_prices"
    __table_args__ = (
        CheckConstraint(f"interval IN {PRICE_INTERVALS}", name="interval_valid"),
        CheckConstraint(f"status IN {PRICE_STATUSES}", name="status_valid"),
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        # One active price per plan, interval and currency (PostgreSQL and SQLite).
        Index(
            "uq_membership_plan_prices_active",
            "plan_id",
            "interval",
            "currency",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("membership_plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    shown_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    plan: Mapped[MembershipPlan] = relationship(back_populates="prices")


class MembershipPlanAccess(db.Model):
    __tablename__ = "membership_plan_access"
    __table_args__ = (
        UniqueConstraint("plan_id", "product_id", name="uq_membership_plan_access_product"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("membership_plans.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    added_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    plan: Mapped[MembershipPlan] = relationship(back_populates="access")
    product: Mapped[Any] = relationship("Product")


class MembershipProviderPlan(db.Model):
    """The provider's recurring plan for one immutable price, per mode (test/live)."""

    __tablename__ = "membership_provider_plans"
    __table_args__ = (
        CheckConstraint("mode IN ('test', 'live')", name="mode_valid"),
        UniqueConstraint("provider", "mode", "price_id", name="uq_membership_provider_plans_price"),
        UniqueConstraint("provider", "plan_code", name="uq_membership_provider_plans_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    price_id: Mapped[int] = mapped_column(
        ForeignKey("membership_plan_prices.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    price: Mapped[MembershipPlanPrice] = relationship()


class CustomerSubscription(db.Model):
    """One customer's membership subscription. ``pending`` until the first payment is
    verified; ``incomplete`` when that checkout never completed."""

    __tablename__ = "customer_subscriptions"
    __table_args__ = (
        CheckConstraint(f"status IN {SUBSCRIPTION_STATUSES}", name="status_valid"),
        CheckConstraint("mode IN ('test', 'live')", name="mode_valid"),
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        UniqueConstraint("customer_id", "idempotency_key", name="uq_customer_subscriptions_key"),
        # Duplicate prevention: one live subscription per customer.
        Index(
            "uq_customer_subscriptions_live",
            "customer_id",
            unique=True,
            postgresql_where=text(f"status IN {LIVE_SUBSCRIPTION_STATUSES}"),
            sqlite_where=text(f"status IN {LIVE_SUBSCRIPTION_STATUSES}"),
        ),
        Index("ix_customer_subscriptions_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("membership_plans.id", ondelete="RESTRICT"), nullable=False
    )
    price_id: Mapped[int] = mapped_column(
        ForeignKey("membership_plan_prices.id", ondelete="RESTRICT"), nullable=False
    )
    provider_plan_id: Mapped[int] = mapped_column(
        ForeignKey("membership_provider_plans.id", ondelete="RESTRICT"), nullable=False
    )
    # The order of the first payment (existing orders/receipts/refunds infrastructure).
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), unique=True, nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    # Price snapshot at checkout (the price row is immutable too).
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Provider identifiers only: never card or authorisation details.
    provider_customer_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    provider_subscription_code: Mapped[str | None] = mapped_column(
        String(60), unique=True, nullable=True
    )
    # Paystack's token for managing the subscription by email (cancellation, Batch 10.3).
    provider_email_token: Mapped[str | None] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    access_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    end_reason: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    # Batch 10.3 lifecycle: cancellation takes effect at the end of the paid period;
    # past_due_since marks the first unpaid renewal of the current cycle.
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    past_due_since: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    lock_version: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    plan: Mapped[MembershipPlan] = relationship()
    price: Mapped[MembershipPlanPrice] = relationship()
    provider_plan: Mapped[MembershipProviderPlan] = relationship()
    periods: Mapped[list[SubscriptionPeriod]] = relationship(
        back_populates="subscription", order_by="SubscriptionPeriod.sequence"
    )


class SubscriptionPeriod(db.Model):
    __tablename__ = "subscription_periods"
    __table_args__ = (
        CheckConstraint(f"status IN {PERIOD_STATUSES}", name="status_valid"),
        UniqueConstraint("subscription_id", "sequence", name="uq_subscription_periods_sequence"),
        # One billing period per order (a renewal order pays exactly one period).
        Index("uq_subscription_periods_order", "order_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("customer_subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=True
    )
    provider_invoice_code: Mapped[str | None] = mapped_column(
        String(60), unique=True, nullable=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    subscription: Mapped[CustomerSubscription] = relationship(back_populates="periods")


class SubscriptionEvent(db.Model):
    """Append-only history of a subscription (shown to staff and the member)."""

    __tablename__ = "subscription_events"
    __table_args__ = (
        CheckConstraint(f"source IN {EVENT_SOURCES}", name="source_valid"),
        Index("ix_subscription_events_subscription", "subscription_id", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("customer_subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_events.id", ondelete="SET NULL"), nullable=True
    )
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


GRANT_STATUSES = ("active", "revoked")


class MembershipGrant(db.Model):
    """A complimentary membership (Batch 10.4): staff-granted access to a plan's included
    products until ``expires_at``. Never a payment, never counted as paid revenue or as a
    paid subscriber. Access comes from membership entitlements with reference
    ``grant-<id>`` that expire with the grant."""

    __tablename__ = "membership_grants"
    __table_args__ = (
        CheckConstraint(f"status IN {GRANT_STATUSES}", name="status_valid"),
        CheckConstraint("expires_at > starts_at", name="period_valid"),
        UniqueConstraint("customer_id", "idempotency_key", name="uq_membership_grants_key"),
        Index("ix_membership_grants_customer", "customer_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("membership_plans.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoke_reason: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    plan: Mapped[MembershipPlan] = relationship()
