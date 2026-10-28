"""Membership plans, prices and included products (Batch 10.1).

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
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .base import TimestampMixin
from .types import JSONType, UTCDateTime, utcnow

PLAN_STATUSES = ("draft", "published", "archived")
PRICE_INTERVALS = ("month", "year")
PRICE_STATUSES = ("active", "retired")


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
