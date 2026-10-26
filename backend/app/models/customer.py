"""Customer accounts, sessions, entitlements and download activity.

Customers are a separate table from administrators (``users``): no customer can
ever hold an administrative role, and customer sessions are opaque database
tokens that the admin API does not recognise.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .base import TimestampMixin
from .types import JSONType, UTCDateTime, utcnow

# "guest": a buyer record created by guest checkout (no password, can't sign in). It becomes
# an account when someone registers with that email and confirms it.
CUSTOMER_STATUSES = ("active", "disabled", "deleted", "guest")
# "guest_access": emailed link to purchases made with guest checkout (reusable until expiry).
CUSTOMER_TOKEN_PURPOSES = ("verify_email", "password_reset", "guest_access")
ENTITLEMENT_SOURCES = ("purchase", "bundle", "free", "manual")
ENTITLEMENT_STATUSES = ("active", "revoked")
DOWNLOAD_STATUSES = ("authorized", "served", "denied")


class Customer(TimestampMixin, db.Model):
    __tablename__ = "customers"
    __table_args__ = (CheckConstraint(f"status IN {CUSTOMER_STATUSES}", name="status_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    # Stored lower-cased; uniqueness is therefore case-insensitive.
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Staff-marked accounts that may use checkout while payments are in test mode.
    is_test_account: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    support_notes: Mapped[str] = mapped_column(String(2000), default="", nullable=False)

    @property
    def is_active(self) -> bool:
        return self.status == "active"


class CustomerSession(db.Model):
    """Opaque session token (only its SHA-256 hash is stored) plus a CSRF secret hash."""

    __tablename__ = "customer_sessions"
    __table_args__ = (Index("ix_customer_sessions_customer_active", "customer_id", "revoked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    customer: Mapped[Customer] = relationship(lazy="joined")


class CustomerToken(db.Model):
    """Single-use, time-limited email verification and password reset tokens (hash only)."""

    __tablename__ = "customer_tokens"
    __table_args__ = (
        CheckConstraint(f"purpose IN {CUSTOMER_TOKEN_PURPOSES}", name="purpose_valid"),
        Index("ix_customer_tokens_customer_purpose", "customer_id", "purpose"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Entitlement(db.Model):
    """The right of one customer to download one product's files.

    ``grant_key`` is unique, so concurrent fulfilment of the same order item (or a
    repeated free claim) can never create duplicates. ``purchased_versions`` records
    which file versions existed when access was granted (see the version policy in
    ``app/services/commerce/entitlements.py``).
    """

    __tablename__ = "entitlements"
    __table_args__ = (
        CheckConstraint(f"source IN {ENTITLEMENT_SOURCES}", name="source_valid"),
        CheckConstraint(f"status IN {ENTITLEMENT_STATUSES}", name="status_valid"),
        CheckConstraint(
            "download_limit IS NULL OR download_limit > 0", name="download_limit_positive"
        ),
        Index("ix_entitlements_customer_status", "customer_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    grant_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    order_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("order_items.id", ondelete="RESTRICT"), nullable=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("entitlements.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    purchased_versions: Mapped[dict[str, Any]] = mapped_column(
        JSONType, default=dict, nullable=False
    )
    download_count: Mapped[int] = mapped_column(default=0, nullable=False)
    download_limit: Mapped[int | None] = mapped_column(nullable=True)
    granted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    granted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)

    customer: Mapped[Customer] = relationship(lazy="joined")
    product = relationship("Product", lazy="joined")


class EntitlementEvent(db.Model):
    """Grant, revoke and restore history (who, when, why)."""

    __tablename__ = "entitlement_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    entitlement_id: Mapped[int] = mapped_column(
        ForeignKey("entitlements.id", ondelete="CASCADE"), index=True, nullable=False
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    actor = relationship("User", lazy="joined")


class DownloadGrant(db.Model):
    """Short-lived download authorisation. Only the token hash is stored."""

    __tablename__ = "download_grants"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    entitlement_id: Mapped[int] = mapped_column(
        ForeignKey("entitlements.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    file_version_id: Mapped[int] = mapped_column(
        ForeignKey("product_file_versions.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    use_count: Mapped[int] = mapped_column(default=0, nullable=False)
    # Issued through a guest access token (no customer session to match when serving).
    guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class DownloadEvent(db.Model):
    __tablename__ = "download_events"
    __table_args__ = (
        CheckConstraint(f"status IN {DOWNLOAD_STATUSES}", name="status_valid"),
        Index("ix_download_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), index=True, nullable=True
    )
    entitlement_id: Mapped[int | None] = mapped_column(
        ForeignKey("entitlements.id", ondelete="SET NULL"), index=True, nullable=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True, nullable=True
    )
    file_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_file_versions.id", ondelete="SET NULL"), nullable=True
    )
    grant_id: Mapped[int | None] = mapped_column(
        ForeignKey("download_grants.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
