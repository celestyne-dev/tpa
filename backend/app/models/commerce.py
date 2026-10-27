"""Digital product catalogue: products, prices, private files, bundles and revisions.

Money is always stored as integer minor units plus an ISO 4217 currency code.
Private deliverable files live in a separate storage area (``app/storage/private``)
and are never registered in the public media library.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
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

PRODUCT_STATUSES = ("draft", "published", "archived")
# coming_soon: shown as an honest preview, never purchasable.
# on_sale: purchasable once every readiness check passes (files, price, schedule).
SALES_STATUSES = ("coming_soon", "on_sale")
PRICING_MODELS = ("paid", "free")
PRICE_KINDS = ("regular", "promotional")
FILE_STATUSES = ("active", "inactive")
SCAN_STATUSES = ("not_configured", "pending", "clean", "infected", "error")
PRODUCT_REVISION_KINDS = ("draft", "publish", "restore", "system")


product_categories = Table(
    "product_category_links",
    db.metadata,
    Column("product_id", Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "category_id",
        Integer,
        ForeignKey("product_categories.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Index("ix_product_category_links_category_id", "category_id"),
)

# Related resources shown on a resource page (ordered, one direction: product -> related).
product_related = Table(
    "product_related",
    db.metadata,
    Column("product_id", Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("related_id", Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("position", Integer, nullable=False, default=0),
    CheckConstraint("product_id <> related_id", name="not_self"),
    Index("ix_product_related_related_id", "related_id"),
)

product_tags = Table(
    "product_tags",
    db.metadata,
    Column("product_id", Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="RESTRICT"), primary_key=True),
    Index("ix_product_tags_tag_id", "tag_id"),
)


class ProductCategory(TimestampMixin, db.Model):
    __tablename__ = "product_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ProductCollection(TimestampMixin, db.Model):
    __tablename__ = "product_collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(600), default="", nullable=False)
    cover_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    seo_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    items: Mapped[list[ProductCollectionItem]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
        order_by="ProductCollectionItem.position",
        lazy="selectin",
    )


class ProductCollectionItem(db.Model):
    __tablename__ = "product_collection_items"
    __table_args__ = (
        UniqueConstraint("collection_id", "product_id", name="uq_product_collection_items_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("product_collections.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(default=0, nullable=False)

    collection: Mapped[ProductCollection] = relationship(back_populates="items")


class Product(TimestampMixin, db.Model):
    """A digital product. Public pages read ``published_snapshot`` (content) plus the
    live price and availability; draft edits never reach the public site."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(f"status IN {PRODUCT_STATUSES}", name="status_valid"),
        CheckConstraint(f"sales_status IN {SALES_STATUSES}", name="sales_status_valid"),
        CheckConstraint(f"pricing_model IN {PRICING_MODELS}", name="pricing_model_valid"),
        CheckConstraint("page_count IS NULL OR page_count > 0", name="page_count_positive"),
        CheckConstraint(
            "download_limit IS NULL OR download_limit > 0", name="download_limit_positive"
        ),
        CheckConstraint("access_days IS NULL OR access_days > 0", name="access_days_positive"),
        Index("ix_products_status_featured", "status", "is_featured"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stable public identifier (cart items, orders); never changes when the slug does.
    public_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    published_slug: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    product_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    short_description: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    description: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    benefits: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    # [{"title", "description", "format"}] — what the buyer receives (shown publicly).
    included: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    faq: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    audience: Mapped[str] = mapped_column(String(600), default="", nullable=False)
    format_label: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    language: Mapped[str] = mapped_column(String(35), default="en", nullable=False)
    edition: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    # Only shown when an editor enters the real figure; never estimated.
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("authors.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    cover_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=True
    )
    # Design-token artwork used while no cover image has been uploaded.
    cover_theme: Mapped[str] = mapped_column(String(20), default="sage", nullable=False)
    gallery: Mapped[list[int]] = mapped_column(JSONType, default=list, nullable=False)
    social_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    seo_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    noindex: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tax_category: Mapped[str] = mapped_column(String(40), default="digital_goods", nullable=False)
    # ---- Batch 08: resource access rules (applied when access is granted) ----
    # Downloads per buyer; None uses the store-wide setting (payments.download_limit).
    download_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Access ends this many days after it is granted; None means lifetime access.
    access_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A future membership may unlock this resource (no effect until memberships exist).
    membership_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    sales_status: Mapped[str] = mapped_column(String(20), default="coming_soon", nullable=False)
    pricing_model: Mapped[str] = mapped_column(String(10), default="paid", nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    featured_order: Mapped[int] = mapped_column(default=0, nullable=False)
    # Purchasing opens at this time (optional); the page itself is public once published.
    available_from: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    available_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    first_published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    published_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    lock_version: Mapped[int] = mapped_column(default=1, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    author = relationship("Author", lazy="joined")
    categories: Mapped[list[ProductCategory]] = relationship(
        secondary=product_categories, lazy="selectin", order_by=ProductCategory.sort_order
    )
    tags = relationship("Tag", secondary=product_tags, lazy="selectin")
    prices: Mapped[list[ProductPrice]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )
    files: Mapped[list[ProductFile]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductFile.position",
    )
    # Ordered related resources. Written through product_admin.set_related (keeps the order).
    related: Mapped[list[Product]] = relationship(
        "Product",
        secondary=product_related,
        primaryjoin=lambda: Product.id == product_related.c.product_id,
        secondaryjoin=lambda: Product.id == product_related.c.related_id,
        order_by=product_related.c.position,
        lazy="selectin",
        viewonly=True,
    )
    bundle_items: Mapped[list[BundleItem]] = relationship(
        foreign_keys="BundleItem.bundle_id",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="BundleItem.position",
    )

    @property
    def is_bundle(self) -> bool:
        return self.product_type == "bundle"


class ProductPrice(db.Model):
    """One regular and at most one promotional price per product and currency."""

    __tablename__ = "product_prices"
    __table_args__ = (
        UniqueConstraint("product_id", "currency", "kind", name="uq_product_prices_kind"),
        CheckConstraint("amount_minor >= 0", name="amount_non_negative"),
        CheckConstraint(
            "compare_at_minor IS NULL OR compare_at_minor > amount_minor",
            name="compare_at_greater",
        ),
        CheckConstraint(f"kind IN {PRICE_KINDS}", name="kind_valid"),
        CheckConstraint("length(currency) = 3", name="currency_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="regular", nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    compare_at_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    product: Mapped[Product] = relationship(back_populates="prices")


class ProductFile(TimestampMixin, db.Model):
    """A deliverable (e.g. "Workbook PDF"). Its content lives in numbered versions."""

    __tablename__ = "product_files"
    __table_args__ = (CheckConstraint(f"status IN {FILE_STATUSES}", name="status_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(600), default="", nullable=False)
    position: Mapped[int] = mapped_column(default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_file_versions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    product: Mapped[Product] = relationship(back_populates="files")
    versions: Mapped[list[ProductFileVersion]] = relationship(
        back_populates="file",
        foreign_keys="ProductFileVersion.file_id",
        order_by="ProductFileVersion.version",
        lazy="selectin",
    )

    @property
    def current_version(self) -> ProductFileVersion | None:
        return next((v for v in self.versions if v.id == self.current_version_id), None)


class ProductFileVersion(db.Model):
    """An immutable uploaded file. Versions referenced by purchases are never deleted."""

    __tablename__ = "product_file_versions"
    __table_args__ = (
        UniqueConstraint("file_id", "version", name="uq_product_file_versions_number"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint(f"scan_status IN {SCAN_STATUSES}", name="scan_status_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(
        ForeignKey("product_files.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    # Random private storage key; never derived from the uploaded file name.
    storage_key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_format: Mapped[str] = mapped_column(String(20), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    scan_status: Mapped[str] = mapped_column(String(20), default="not_configured", nullable=False)
    scanned_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    notes: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    file: Mapped[ProductFile] = relationship(back_populates="versions", foreign_keys=[file_id])

    @property
    def deliverable(self) -> bool:
        return self.scan_status in ("not_configured", "clean")


class BundleItem(db.Model):
    __tablename__ = "bundle_items"
    __table_args__ = (
        UniqueConstraint("bundle_id", "product_id", name="uq_bundle_items_pair"),
        CheckConstraint("bundle_id <> product_id", name="not_self"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bundle_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(default=0, nullable=False)

    product: Mapped[Product] = relationship(foreign_keys=[product_id], lazy="joined")


class ProductRevision(db.Model):
    __tablename__ = "product_revisions"
    __table_args__ = (
        UniqueConstraint("product_id", "number", name="uq_product_revisions_number"),
        CheckConstraint(f"kind IN {PRODUCT_REVISION_KINDS}", name="kind_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False
    )
    number: Mapped[int] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    created_by = relationship("User", lazy="joined")
