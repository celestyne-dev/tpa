"""Partnerships, sponsorships, advertising inventory, affiliate marketing and the media kit.

Commercial values are integer minor units with an explicit ISO currency (never
converted). Audience figures are administrator-entered measurements with a source and
a measurement date; nothing here is estimated or generated.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from ..extensions import db
from .base import TimestampMixin
from .types import JSONType, UTCDateTime, utcnow

PARTNER_STATUSES = ("prospect", "active", "inactive", "archived")
PARTNERSHIP_TYPES = (
    "sponsorship",
    "advertising",
    "affiliate",
    "content_collaboration",
    "newsletter_sponsorship",
    "event",
    "other",
)
INQUIRY_STATUSES = ("new", "reviewed", "converted", "declined", "spam")
OPPORTUNITY_STAGES = (
    "new_inquiry",
    "qualification",
    "proposal",
    "negotiation",
    "approved",
    "contracted",
    "active",
    "completed",
    "lost",
    "cancelled",
)
CAMPAIGN_STATUSES = (
    "draft",
    "internal_review",
    "sponsor_review",
    "approved",
    "scheduled",
    "active",
    "completed",
    "cancelled",
)
REVIEW_STATUSES = ("draft", "internal_review", "sponsor_review", "approved")
PLACEMENT_TYPES = (
    "homepage_sponsor",
    "article_sponsor",
    "in_article_banner",
    "sidebar",
    "footer_promotion",
    "newsletter_sponsor",
    "sponsored_article",
    "brand_spotlight",
    "landing_page",
)
CHANNELS = ("website", "newsletter", "social", "other")
PRICING_MODELS = ("fixed_fee", "per_placement", "package", "cpm")
BOOKING_STATUSES = ("pending", "approved", "paused", "stopped", "cancelled")
FINANCE_KINDS = ("invoiced", "received")
AFFILIATE_ACCOUNT_STATUSES = ("not_applied", "applied", "approved", "rejected", "paused", "closed")
COMMISSION_STATUSES = ("reported", "approved", "paid", "reversed")


def _money_check(column: str) -> CheckConstraint:
    return CheckConstraint(f"{column} IS NULL OR {column} >= 0", name=f"{column}_nonnegative")


class Partner(TimestampMixin, db.Model):
    __tablename__ = "partners"
    __table_args__ = (
        CheckConstraint(f"status IN {PARTNER_STATUSES}", name="status_valid"),
        CheckConstraint(f"partnership_type IN {PARTNERSHIP_TYPES}", name="type_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    website: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    logo_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    industry: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    description: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    country: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    partnership_type: Mapped[str] = mapped_column(String(40), default="other", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="prospect", nullable=False)
    source: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    internal_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    contacts: Mapped[list[PartnerContact]] = relationship(
        back_populates="partner", cascade="all, delete-orphan", lazy="selectin"
    )
    logo = relationship("MediaAsset", lazy="joined")
    owner = relationship("User", lazy="joined")


class PartnerContact(db.Model):
    """Business contact details only (name, work email, role)."""

    __tablename__ = "partner_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_id: Mapped[int] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), default="", nullable=False)
    role: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    partner: Mapped[Partner] = relationship(back_populates="contacts")


class PartnershipInquiry(db.Model):
    __tablename__ = "partnership_inquiries"
    __table_args__ = (
        CheckConstraint(f"status IN {INQUIRY_STATUSES}", name="status_valid"),
        Index("ix_partnership_inquiries_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization: Mapped[str] = mapped_column(String(160), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    website: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    collaboration_type: Mapped[str] = mapped_column(String(40), nullable=False)
    budget_range: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    objectives: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    message: Mapped[str] = mapped_column(String(4000), default="", nullable=False)
    privacy_notice_version: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    notification_status: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    partner_id: Mapped[int | None] = mapped_column(
        ForeignKey("partners.id", ondelete="SET NULL"), nullable=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("partnership_opportunities.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Opportunity(TimestampMixin, db.Model):
    __tablename__ = "partnership_opportunities"
    __table_args__ = (
        CheckConstraint(f"stage IN {OPPORTUNITY_STAGES}", name="stage_valid"),
        _money_check("expected_value_minor"),
        Index("ix_partnership_opportunities_stage", "stage", "follow_up_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_id: Mapped[int] = mapped_column(
        ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    stage: Mapped[str] = mapped_column(String(20), default="new_inquiry", nullable=False)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expected_value_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    follow_up_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    internal_reference: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    proposal_reference: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    lost_reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)

    partner: Mapped[Partner] = relationship(lazy="joined")
    owner = relationship("User", lazy="joined")


class CommercialEvent(db.Model):
    """History for opportunities, campaigns and bookings: stage changes, interactions,
    approvals. Complements the global audit log."""

    __tablename__ = "commercial_events"
    __table_args__ = (
        Index("ix_commercial_events_entity", "entity_type", "entity_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    from_state: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    to_state: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    summary: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    occurred_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class SponsorshipCampaign(TimestampMixin, db.Model):
    __tablename__ = "sponsorship_campaigns"
    __table_args__ = (
        CheckConstraint(f"status IN {CAMPAIGN_STATUSES}", name="status_valid"),
        CheckConstraint(
            "starts_on IS NULL OR ends_on IS NULL OR ends_on >= starts_on", name="dates_ordered"
        ),
        _money_check("contracted_fee_minor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_id: Mapped[int] = mapped_column(
        ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("partnership_opportunities.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    contracted_fee_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    disclosure_text: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    partner: Mapped[Partner] = relationship(lazy="joined")


class ArticleSponsorship(TimestampMixin, db.Model):
    """Sponsorship details for an article. The article itself keeps its normal editor,
    revisions, approvals, SEO and publishing; publishing is refused until the disclosure
    is set and the sponsorship review is approved."""

    __tablename__ = "article_sponsorships"
    __table_args__ = (CheckConstraint(f"review_status IN {REVIEW_STATUSES}", name="review_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    partner_id: Mapped[int | None] = mapped_column(
        ForeignKey("partners.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("sponsorship_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    sponsor_name: Mapped[str] = mapped_column(String(160), nullable=False)
    label: Mapped[str] = mapped_column(String(60), default="Sponsored Content", nullable=False)
    disclosure_text: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    sponsor_approval_notes: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    sponsored_links: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    sponsor_media_ids: Mapped[list[int]] = mapped_column(JSONType, default=list, nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    article = relationship(
        "Article", backref=backref("sponsorship", uselist=False, lazy="selectin")
    )


class NewsletterSponsorship(TimestampMixin, db.Model):
    """Sponsor disclosure for a newsletter campaign (edited in the campaign editor)."""

    __tablename__ = "newsletter_sponsorships"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("email_campaigns.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    sponsorship_campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("sponsorship_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    sponsor_name: Mapped[str] = mapped_column(String(160), nullable=False)
    disclosure_text: Mapped[str] = mapped_column(String(400), nullable=False)

    newsletter = relationship(
        "Campaign", backref=backref("sponsorship", uselist=False, lazy="selectin")
    )


class AdPlacement(TimestampMixin, db.Model):
    __tablename__ = "ad_placements"
    __table_args__ = (
        CheckConstraint(f"placement_type IN {PLACEMENT_TYPES}", name="type_valid"),
        CheckConstraint(f"channel IN {CHANNELS}", name="channel_valid"),
        CheckConstraint(f"pricing_model IN {PRICING_MODELS}", name="pricing_valid"),
        CheckConstraint("capacity >= 1", name="capacity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    placement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default="website", nullable=False)
    dimensions: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    creative_formats: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    # Exclusive placements allow one booking at a time; otherwise up to ``capacity``.
    exclusive: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    pricing_model: Mapped[str] = mapped_column(String(20), default="fixed_fee", nullable=False)
    default_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    # CPM pricing is only allowed where impressions are reliably measured.
    impressions_measured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    restrictions: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    internal_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RateCard(TimestampMixin, db.Model):
    """Indicative published rates. Final fees live on bookings and campaigns."""

    __tablename__ = "rate_cards"
    __table_args__ = (
        CheckConstraint(f"pricing_model IN {PRICING_MODELS}", name="pricing_valid"),
        CheckConstraint("amount_minor >= 0", name="amount_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    placement_id: Mapped[int | None] = mapped_column(
        ForeignKey("ad_placements.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    pricing_model: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    unit_label: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    description: Mapped[str] = mapped_column(String(600), default="", nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    placement: Mapped[AdPlacement | None] = relationship(lazy="joined")


class Booking(TimestampMixin, db.Model):
    __tablename__ = "ad_bookings"
    __table_args__ = (
        CheckConstraint(f"status IN {BOOKING_STATUSES}", name="status_valid"),
        CheckConstraint("ends_at > starts_at", name="window_valid"),
        _money_check("agreed_fee_minor"),
        Index("ix_ad_bookings_placement_window", "placement_id", "starts_at", "ends_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    placement_id: Mapped[int] = mapped_column(
        ForeignKey("ad_placements.id", ondelete="RESTRICT"), nullable=False
    )
    partner_id: Mapped[int] = mapped_column(
        ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("sponsorship_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    agreed_fee_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    # Creative (rendered only while the booking is approved and live).
    headline: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    body: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    image_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    link_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    link_label: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    notes: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    placement: Mapped[AdPlacement] = relationship(lazy="joined")
    partner: Mapped[Partner] = relationship(lazy="joined")
    image = relationship("MediaAsset", lazy="joined")


class PartnershipFinanceEntry(db.Model):
    """Manually recorded invoices and verified/reconciled payments. Nothing here issues an
    invoice or moves money."""

    __tablename__ = "partnership_finance_entries"
    __table_args__ = (
        CheckConstraint(f"kind IN {FINANCE_KINDS}", name="kind_valid"),
        CheckConstraint("amount_minor > 0", name="amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    partner_id: Mapped[int] = mapped_column(
        ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("sponsorship_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    entered_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class AffiliateProgram(TimestampMixin, db.Model):
    __tablename__ = "affiliate_programs"
    __table_args__ = (
        CheckConstraint(f"account_status IN {AFFILIATE_ACCOUNT_STATUSES}", name="status_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    merchant: Mapped[str] = mapped_column(String(160), nullable=False)
    network: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    website: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    commission_model: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    # Entered only when confirmed by the merchant/network (free text such as "8%").
    commission_rate: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    payout_threshold_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    account_status: Mapped[str] = mapped_column(String(20), default="not_applied", nullable=False)
    # Private identifiers: only visible with affiliates.manage.
    account_identifier: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    terms_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    last_verified_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class AffiliateLink(TimestampMixin, db.Model):
    __tablename__ = "affiliate_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    program_id: Mapped[int | None] = mapped_column(
        ForeignKey("affiliate_programs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    merchant: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    target_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    campaign: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("articles.id", ondelete="SET NULL"), nullable=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    utm_source: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    utm_medium: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    utm_campaign: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    disclosure_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    program: Mapped[AffiliateProgram | None] = relationship(lazy="joined")


class AffiliateClickDaily(db.Model):
    """Aggregated outbound clicks per link, day and source page. No IPs, cookies or
    user identifiers are stored."""

    __tablename__ = "affiliate_click_daily"
    __table_args__ = (UniqueConstraint("link_id", "day", "source_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    link_id: Mapped[int] = mapped_column(
        ForeignKey("affiliate_links.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    source_path: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AffiliateCommission(TimestampMixin, db.Model):
    """Commissions as reported by the network (import) or entered manually (labelled).
    Never derived from clicks."""

    __tablename__ = "affiliate_commissions"
    __table_args__ = (
        CheckConstraint(f"status IN {COMMISSION_STATUSES}", name="status_valid"),
        CheckConstraint("source IN ('import', 'manual')", name="source_valid"),
        UniqueConstraint("program_id", "external_reference"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("affiliate_programs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    link_id: Mapped[int | None] = mapped_column(
        ForeignKey("affiliate_links.id", ondelete="SET NULL"), nullable=True
    )
    external_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="reported", nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    import_batch: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    notes: Mapped[str] = mapped_column(String(600), default="", nullable=False)
    entered_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    program: Mapped[AffiliateProgram] = relationship(lazy="joined")


class AudienceMetric(TimestampMixin, db.Model):
    """A dated, attributed audience measurement entered by an administrator."""

    __tablename__ = "audience_metrics"
    __table_args__ = (CheckConstraint("value >= 0", name="value_nonnegative"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_type: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[Any] = mapped_column(Numeric(16, 2), nullable=False)
    platform: Mapped[str] = mapped_column(String(80), nullable=False)
    period_label: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(300), nullable=False)
    measured_on: Mapped[date] = mapped_column(Date, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str] = mapped_column(String(600), default="", nullable=False)
    entered_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
