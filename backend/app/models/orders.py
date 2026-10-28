"""Orders, payment attempts, verified transactions, provider events, receipts and refunds.

Every amount is an integer in the currency's minor unit, with an explicit
ISO 4217 code. Orders keep an exact snapshot of each item's price and currency.
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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .base import TimestampMixin
from .types import JSONType, UTCDateTime, utcnow

ORDER_STATUSES = (
    "pending",
    "awaiting_payment",
    "paid",
    "failed",
    "cancelled",
    "partially_refunded",
    "refunded",
)
PAYMENT_MODES = ("test", "live")
ORDER_KINDS = ("purchase", "subscription")
ATTEMPT_STATUSES = ("created", "initialized", "succeeded", "failed", "abandoned", "mismatch")
TRANSACTION_KINDS = ("charge", "refund")
EVENT_STATUSES = ("received", "processed", "ignored", "rejected", "deferred", "error")
REFUND_STATUSES = (
    "manual_review",
    "pending_provider",
    "processed",
    "failed",
    "rejected",
)
EMAIL_STATUSES = ("sent", "development_console", "memory", "not_configured", "failed")


class Order(TimestampMixin, db.Model):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(f"status IN {ORDER_STATUSES}", name="status_valid"),
        CheckConstraint(f"mode IN {PAYMENT_MODES}", name="mode_valid"),
        CheckConstraint(f"kind IN {ORDER_KINDS}", name="kind_valid"),
        CheckConstraint("subtotal_minor >= 0 AND total_minor >= 0", name="amounts_non_negative"),
        CheckConstraint(
            "refunded_minor >= 0 AND refunded_minor <= total_minor", name="refund_within_total"
        ),
        UniqueConstraint("customer_id", "idempotency_key", name="uq_orders_idempotency"),
        Index("ix_orders_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # Snapshot kept for accounting even if the customer account is later anonymised.
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    tax_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    refunded_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    cart_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    terms_version: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    # Guest checkout: placed without signing in. Its purchases show in an account only once
    # that account's email is confirmed; the browser that placed it holds an order token.
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Batch 10.2: "subscription" orders are membership payments (no downloads granted).
    kind: Mapped[str] = mapped_column(
        String(20), default="purchase", server_default="purchase", nullable=False
    )
    guest_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)

    customer = relationship("Customer", lazy="joined")
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    attempts: Mapped[list[PaymentAttempt]] = relationship(
        back_populates="order", lazy="selectin", order_by="PaymentAttempt.id"
    )


class OrderItem(db.Model):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id", name="uq_order_items_product"),
        CheckConstraint("quantity = 1", name="single_licence"),
        CheckConstraint("unit_amount_minor >= 0", name="amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    product_public_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    product_type: Mapped[str] = mapped_column(String(40), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    unit_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    compare_at_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    quantity: Mapped[int] = mapped_column(default=1, nullable=False)
    line_total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_prices.id", ondelete="SET NULL"), nullable=True
    )
    # Products included at the time of sale (bundles); composition changes later
    # never change what this order granted.
    bundle_contents: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType, default=list, nullable=False
    )

    order: Mapped[Order] = relationship(back_populates="items")


class PaymentAttempt(db.Model):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        CheckConstraint(f"status IN {ATTEMPT_STATUSES}", name="status_valid"),
        CheckConstraint(f"mode IN {PAYMENT_MODES}", name="mode_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    # Our reference, sent to the provider; unique across all attempts.
    reference: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="created", nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    authorization_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    access_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_status: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    failure_reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    order: Mapped[Order] = relationship(back_populates="attempts")


class PaymentTransaction(db.Model):
    """A provider-verified money movement (charge or refund)."""

    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("provider", "kind", "provider_id", name="uq_payment_transactions_id"),
        CheckConstraint(f"kind IN {TRANSACTION_KINDS}", name="kind_valid"),
        CheckConstraint(f"mode IN {PAYMENT_MODES}", name="mode_valid"),
        CheckConstraint("amount_minor >= 0", name="amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_attempts.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(100), nullable=False)
    reference: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Payment channel only (card, mobile_money, bank...); never card numbers.
    channel: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class PaymentEvent(db.Model):
    """Every provider webhook received, with its verification and processing outcome."""

    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("provider", "dedupe_key", name="uq_payment_events_dedupe"),
        CheckConstraint(f"status IN {EVENT_STATUSES}", name="status_valid"),
        Index("ix_payment_events_reference", "reference"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), index=True, nullable=True
    )
    mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="received", nullable=False)
    result: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    # Sanitised copy (identifiers, amounts, status); no customer authorisation data.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    received_count: Mapped[int] = mapped_column(default=1, nullable=False)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Receipt(db.Model):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)


class Refund(db.Model):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint(f"status IN {REFUND_STATUSES}", name="status_valid"),
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        UniqueConstraint("order_id", "idempotency_key", name="uq_refunds_idempotency"),
        UniqueConstraint("provider", "provider_refund_id", name="uq_refunds_provider_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)  # provider | manual
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_refund_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    revoke_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    downloads_at_request: Mapped[int] = mapped_column(default=0, nullable=False)
    requested_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    requested_by = relationship("User", foreign_keys=[requested_by_id], lazy="joined")


class EmailDelivery(db.Model):
    """What actually happened to each transactional email (never claims unsent mail)."""

    __tablename__ = "email_deliveries"
    __table_args__ = (
        CheckConstraint(f"status IN {EMAIL_STATUSES}", name="status_valid"),
        Index("ix_email_deliveries_order", "order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    template: Mapped[str] = mapped_column(String(60), nullable=False)
    recipient: Mapped[str] = mapped_column(String(254), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), index=True, nullable=True
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
