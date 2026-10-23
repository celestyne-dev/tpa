"""The Positive Reset newsletter: subscribers, consent, suppression, campaigns, the email
outbox, automations and lead magnets.

Newsletter consent is independent of customer accounts and purchases: nothing here
is created when someone registers or buys, and a subscriber row never grants
access to anything but email preferences.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .base import TimestampMixin
from .types import JSONType, UTCDateTime, utcnow

# pending: waiting for double opt-in; quarantined: imported/unverified, never mailed.
SUBSCRIBER_STATUSES = (
    "pending",
    "subscribed",
    "unsubscribed",
    "bounced",
    "complained",
    "quarantined",
)
SIGNUP_SOURCES = (
    "homepage",
    "footer",
    "newsletter_page",
    "article",
    "page_section",
    "lead_magnet",
    "resource_page",
    "import",
    "admin",
    "other",
)
SUPPRESSION_REASONS = ("unsubscribed", "bounced", "complained", "manual", "erased")
CAMPAIGN_STATUSES = ("draft", "approved", "scheduled", "sending", "sent", "cancelled")
MESSAGE_KINDS = ("campaign", "automation", "confirmation", "lead_magnet", "notice", "test")
MESSAGE_STATUSES = (
    "queued",
    "sending",
    "accepted",  # the provider (e.g. SMTP relay) accepted it: not proof of delivery
    "delivered",  # only from provider delivery evidence
    "bounced",
    "complained",
    "failed",
    "unknown",  # worker stopped mid-send: not retried automatically (no duplicates)
    "cancelled",
    "suppressed",
    "skipped",
)
AUTOMATION_TRIGGERS = (
    "subscription_confirmed",
    "lead_magnet_claimed",
    "article_published",
    "product_published",
    "inactive",
)
AUTOMATION_STATUSES = ("draft", "active", "paused")
ENROLLMENT_STATUSES = ("active", "completed", "exited")
LEAD_MAGNET_STATUSES = ("draft", "active", "archived")
LEAD_MAGNET_OPTINS = ("optional", "required")

subscriber_tag_links = Table(
    "subscriber_tag_links",
    db.metadata,
    Column(
        "subscriber_id",
        ForeignKey("subscribers.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("tag_id", ForeignKey("subscriber_tags.id", ondelete="CASCADE"), primary_key=True),
)


class Subscriber(TimestampMixin, db.Model):
    __tablename__ = "subscribers"
    __table_args__ = (
        CheckConstraint(f"status IN {SUBSCRIBER_STATUSES}", name="status_valid"),
        Index("ix_subscribers_status_source", "status", "source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    # Normalised (trimmed, lower-cased): one row per address.
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="other", nullable=False)
    source_detail: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    # Consent evidence for the current subscription (refreshed on every re-subscribe).
    consent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    consent_text: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    consent_version: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    consent_ip_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    confirmation_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    unsubscribe_reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    notice_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    preferences: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    interests: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    # Engagement we legitimately observe (confirming, updating preferences, claiming a
    # resource). No open or click tracking.
    last_engaged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    import_batch: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    # Bumped to invalidate every previously emailed manage/unsubscribe link.
    token_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    tags: Mapped[list[SubscriberTag]] = relationship(
        secondary=subscriber_tag_links, lazy="selectin", order_by="SubscriberTag.name"
    )

    @property
    def is_marketable(self) -> bool:
        return self.status == "subscribed" and self.confirmed_at is not None


class SubscriberTag(db.Model):
    __tablename__ = "subscriber_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class SubscriberEvent(db.Model):
    """Activity and consent audit trail (subscribe, confirm, unsubscribe, bounce ...)."""

    __tablename__ = "subscriber_events"
    __table_args__ = (Index("ix_subscriber_events_subscriber", "subscriber_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False
    )
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class EmailSuppression(db.Model):
    """Addresses that must never be mailed. Only a SHA-256 of the address is kept, so the
    list survives erasure requests without retaining the address itself."""

    __tablename__ = "email_suppressions"
    __table_args__ = (CheckConstraint(f"reason IN {SUPPRESSION_REASONS}", name="reason_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class SubscriberSegment(TimestampMixin, db.Model):
    __tablename__ = "subscriber_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    # Validated rule list (services/newsletter/segments.py); always ANDed with consent.
    rules: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class EmailTemplate(TimestampMixin, db.Model):
    __tablename__ = "email_templates"
    __table_args__ = (CheckConstraint("kind IN ('campaign', 'automation')", name="kind_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="campaign", nullable=False)
    description: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    subject: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    preheader: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    is_starter: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class Campaign(TimestampMixin, db.Model):
    __tablename__ = "email_campaigns"
    __table_args__ = (
        CheckConstraint(f"status IN {CAMPAIGN_STATUSES}", name="status_valid"),
        Index("ix_email_campaigns_status_scheduled", "status", "scheduled_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    preheader: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    from_name: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    reply_to: Mapped[str] = mapped_column(String(254), default="", nullable=False)
    template_key: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    article_ids: Mapped[list[int]] = mapped_column(JSONType, default=list, nullable=False)
    product_ids: Mapped[list[int]] = mapped_column(JSONType, default=list, nullable=False)
    ctas: Mapped[list[dict[str, str]]] = mapped_column(JSONType, default=list, nullable=False)
    segment_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriber_segments.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    queued_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Frozen at queue time: subject, html/text with per-recipient placeholders, sender.
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    send_mode: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    eligible_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    segment: Mapped[SubscriberSegment | None] = relationship(lazy="joined")


class EmailMessage(db.Model):
    """One outgoing email (the queue and the per-recipient delivery record)."""

    __tablename__ = "email_messages"
    __table_args__ = (
        CheckConstraint(f"kind IN {MESSAGE_KINDS}", name="kind_valid"),
        CheckConstraint(f"status IN {MESSAGE_STATUSES}", name="status_valid"),
        Index("ix_email_messages_due", "status", "next_attempt_at"),
        Index("ix_email_messages_campaign_status", "campaign_id", "status"),
        Index("ix_email_messages_provider_id", "provider_message_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # Idempotency: one message per (campaign, subscriber), (enrolment, step), etc.
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("email_campaigns.id", ondelete="CASCADE"), nullable=True
    )
    enrollment_id: Mapped[int | None] = mapped_column(
        ForeignKey("email_automation_enrollments.id", ondelete="SET NULL"), nullable=True
    )
    subscriber_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscribers.id", ondelete="SET NULL"), nullable=True
    )
    to_email: Mapped[str] = mapped_column(String(254), nullable=False)
    # Empty for campaign messages: those render from the campaign snapshot.
    subject: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    html: Mapped[str] = mapped_column(Text, default="", nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    send_mode: Mapped[str] = mapped_column(String(10), default="live", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    claimed_by: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    attempt_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    provider: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    error: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    bounced_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    complained_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class EmailAutomation(TimestampMixin, db.Model):
    __tablename__ = "email_automations"
    __table_args__ = (
        CheckConstraint(f"trigger IN {AUTOMATION_TRIGGERS}", name="trigger_valid"),
        CheckConstraint(f"status IN {AUTOMATION_STATUSES}", name="status_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    segment_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriber_segments.id", ondelete="RESTRICT"), nullable=True
    )
    # Only subscribers who opted into this preference (e.g. "products") are enrolled.
    required_preference: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    # lead_magnet_id, inactive_days, exit_tag ...
    settings: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    steps: Mapped[list[EmailAutomationStep]] = relationship(
        back_populates="automation",
        order_by="EmailAutomationStep.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class EmailAutomationStep(db.Model):
    __tablename__ = "email_automation_steps"
    __table_args__ = (UniqueConstraint("automation_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_id: Mapped[int] = mapped_column(
        ForeignKey("email_automations.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    preheader: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)

    automation: Mapped[EmailAutomation] = relationship(back_populates="steps")


class EmailAutomationEnrollment(db.Model):
    __tablename__ = "email_automation_enrollments"
    __table_args__ = (
        CheckConstraint(f"status IN {ENROLLMENT_STATUSES}", name="status_valid"),
        # Duplicate-send prevention: one enrolment per subscriber per trigger context.
        UniqueConstraint("automation_id", "subscriber_id", "context_key"),
        Index("ix_email_automation_enrollments_due", "status", "next_run_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_id: Mapped[int] = mapped_column(
        ForeignKey("email_automations.id", ondelete="CASCADE"), nullable=False
    )
    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False
    )
    context_key: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    next_position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    enrolled_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    exit_reason: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    automation: Mapped[EmailAutomation] = relationship(lazy="joined")
    subscriber: Mapped[Subscriber] = relationship(lazy="joined")


class EmailAutomationEvent(db.Model):
    """Trigger queue (e.g. an article was published). Expanded by the email worker, never
    inside a web request. Unique per trigger and context, so each article or product is
    announced at most once."""

    __tablename__ = "email_automation_events"
    __table_args__ = (UniqueConstraint("trigger", "context_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)
    context_key: Mapped[str] = mapped_column(String(120), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    enrolled_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class LeadMagnet(TimestampMixin, db.Model):
    """A free resource (a free product with real private files) offered in exchange for an
    email address. Newsletter opt-in is optional unless clearly stated as required."""

    __tablename__ = "lead_magnets"
    __table_args__ = (
        CheckConstraint(f"status IN {LEAD_MAGNET_STATUSES}", name="status_valid"),
        CheckConstraint(f"newsletter_optin IN {LEAD_MAGNET_OPTINS}", name="optin_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(600), default="", nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    newsletter_optin: Mapped[str] = mapped_column(String(20), default="optional", nullable=False)
    # Shown next to the form whenever subscribing is part of the offer.
    optin_notice: Mapped[str] = mapped_column(String(600), default="", nullable=False)
    link_ttl_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_downloads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    product = relationship("Product", lazy="joined")


class LeadMagnetClaim(db.Model):
    __tablename__ = "lead_magnet_claims"
    __table_args__ = (Index("ix_lead_magnet_claims_email", "lead_magnet_id", "email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_magnet_id: Mapped[int] = mapped_column(
        ForeignKey("lead_magnets.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    subscriber_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscribers.id", ondelete="SET NULL"), nullable=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_downloads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_download_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    lead_magnet: Mapped[LeadMagnet] = relationship(lazy="joined")
