"""Partnerships, sponsorships, advertising inventory, affiliate marketing and media kit.

Incremental and non-destructive:
- new tables only: partners and contacts, partnership inquiries, opportunities,
  commercial history events, sponsorship campaigns, article and newsletter
  sponsorship details (side tables: existing articles and campaigns are not
  altered), ad placements, rate cards, bookings, manual finance entries,
  affiliate programs, links, aggregated daily clicks, commissions and audience
  metrics;
- permissions: partnerships.view/manage, advertising.view and affiliates.view/manage
  become available; sponsorships.*, advertising.manage_inventory/manage_bookings,
  media_kit.manage, affiliates.manage_links, partnership_finance.* and
  partnership_reports.export are added; advertising.manage stays unavailable
  (superseded). Grants go to existing Administrator, Partnerships Manager, Marketing
  Manager, Affiliate Manager, Editor-in-Chief and Finance Manager templates only.

Downgrade drops the new tables (partnership data included) and the new permissions.

Revision ID: 4a65b8174c82
Revises: 0ded798b0061
Create Date: 2026-10-26 06:21:07.635072

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text  # noqa: F401  (used by rendered JSONB types)
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "4a65b8174c82"
down_revision = "0ded798b0061"
branch_labels = None
depends_on = None

# Frozen snapshot of the Batch 07 permission changes.
# (key, label, description, group, module, available, sensitive)
CHANGED = [
    (
        "sponsorships.view",
        "View sponsorship campaigns",
        "",
        "Partnerships & sponsorships",
        "partnerships",
        True,
        False,
    ),
    (
        "sponsorships.manage",
        "Manage sponsorship campaigns",
        "Campaigns, sponsored article and newsletter details, review states.",
        "Partnerships & sponsorships",
        "partnerships",
        True,
        False,
    ),
    (
        "sponsorships.approve",
        "Approve sponsored content",
        "Approve sponsored articles, newsletters and campaigns for publication.",
        "Partnerships & sponsorships",
        "partnerships",
        True,
        False,
    ),
    (
        "advertising.manage_inventory",
        "Manage placements and rate cards",
        "",
        "Advertising",
        "advertising",
        True,
        False,
    ),
    (
        "advertising.manage_bookings",
        "Manage and approve bookings",
        "",
        "Advertising",
        "advertising",
        True,
        False,
    ),
    (
        "media_kit.manage",
        "Manage the media kit and audience data",
        "",
        "Advertising",
        "advertising",
        True,
        False,
    ),
    (
        "affiliates.manage_links",
        "Manage affiliate links",
        "",
        "Affiliates",
        "affiliates",
        True,
        False,
    ),
    (
        "partnership_finance.view",
        "View partnership finances",
        "Fees, invoiced and received amounts, outstanding balances.",
        "Partnerships & sponsorships",
        "partnerships",
        True,
        False,
    ),
    (
        "partnership_finance.manage",
        "Record partnership invoices and payments",
        "Manual records only: no invoices are issued and no payments initiated.",
        "Partnerships & sponsorships",
        "partnerships",
        True,
        False,
    ),
    (
        "partnership_reports.export",
        "Export partnership reports",
        "",
        "Partnerships & sponsorships",
        "partnerships",
        True,
        False,
    ),
    (
        "partnerships.view",
        "View partners and pipeline",
        "Partner profiles, contacts, inquiries and opportunities.",
        "Partnerships & sponsorships",
        "partnerships",
        True,
        False,
    ),
    (
        "partnerships.manage",
        "Manage partners and pipeline",
        "Create and edit partners, inquiries, opportunities and interactions.",
        "Partnerships & sponsorships",
        "partnerships",
        True,
        False,
    ),
    (
        "advertising.view",
        "View advertising inventory and bookings",
        "",
        "Advertising",
        "advertising",
        True,
        False,
    ),
    (
        "affiliates.view",
        "View affiliate programs and links",
        "",
        "Affiliates",
        "affiliates",
        True,
        False,
    ),
    (
        "affiliates.manage",
        "Manage affiliate programs",
        "Programs, private account identifiers, commission imports and disclosure wording.",
        "Affiliates",
        "affiliates",
        True,
        False,
    ),
    (
        "advertising.manage",
        "Manage advertising (superseded)",
        "Replaced in Batch 07 by manage_inventory and manage_bookings.",
        "Advertising",
        "advertising",
        False,
        False,
    ),
]
NEW_KEYS = [
    "sponsorships.view",
    "sponsorships.manage",
    "sponsorships.approve",
    "advertising.manage_inventory",
    "advertising.manage_bookings",
    "media_kit.manage",
    "affiliates.manage_links",
    "partnership_finance.view",
    "partnership_finance.manage",
    "partnership_reports.export",
]
NOW_AVAILABLE = [
    "partnerships.view",
    "partnerships.manage",
    "advertising.view",
    "affiliates.view",
    "affiliates.manage",
]
GRANTS = {
    "administrator": [
        "advertising.manage_bookings",
        "advertising.manage_inventory",
        "advertising.view",
        "affiliates.manage",
        "affiliates.manage_links",
        "affiliates.view",
        "media_kit.manage",
        "partnership_finance.view",
        "partnership_reports.export",
        "partnerships.manage",
        "partnerships.view",
        "sponsorships.approve",
        "sponsorships.manage",
        "sponsorships.view",
    ],
    "partnerships_manager": [
        "advertising.manage_bookings",
        "advertising.manage_inventory",
        "advertising.view",
        "articles.view",
        "media.view",
        "media_kit.manage",
        "partnerships.manage",
        "partnerships.view",
        "sponsorships.manage",
        "sponsorships.view",
    ],
    "marketing_manager": [
        "advertising.manage_bookings",
        "advertising.view",
        "affiliates.manage_links",
        "affiliates.view",
        "sponsorships.manage",
        "sponsorships.view",
    ],
    "affiliate_manager": [
        "affiliates.manage",
        "affiliates.manage_links",
        "affiliates.view",
        "articles.view",
        "products.view",
    ],
    "editor_in_chief": ["sponsorships.approve", "sponsorships.view"],
    "finance_manager": [
        "advertising.view",
        "affiliates.view",
        "partnership_finance.manage",
        "partnership_finance.view",
        "partnership_reports.export",
        "partnerships.view",
        "sponsorships.view",
    ],
}
# Catalogue order at this revision (permissions.sort_order).
ORDER = [
    "dashboard.view",
    "analytics.view",
    "articles.view",
    "articles.create",
    "articles.edit_own",
    "articles.edit_any",
    "articles.submit_review",
    "articles.approve",
    "articles.publish",
    "articles.unpublish",
    "articles.archive",
    "articles.delete",
    "articles.view_revisions",
    "articles.restore_revisions",
    "articles.preview",
    "topics.manage",
    "tags.manage",
    "authors.manage",
    "media.view",
    "media.upload",
    "media.edit",
    "media.replace",
    "media.delete",
    "homepage.view",
    "homepage.edit",
    "homepage.publish",
    "pages.view",
    "pages.edit",
    "pages.create",
    "pages.publish",
    "reusable_sections.manage",
    "branding.manage",
    "announcements.manage",
    "navigation.manage",
    "settings.manage",
    "settings.technical",
    "settings.security",
    "seo.manage",
    "seo.view",
    "redirects.manage",
    "publishing.view",
    "publishing.manage",
    "products.view",
    "products.create",
    "products.edit",
    "products.publish",
    "products.archive",
    "products.manage_prices",
    "products.manage_files",
    "products.manage_bundles",
    "products.manage",
    "orders.view",
    "orders.manage",
    "orders.export",
    "refunds.issue",
    "payments.view_events",
    "payments.configure",
    "customers.view",
    "customers.support",
    "customers.manage",
    "entitlements.view",
    "entitlements.manage",
    "downloads.audit",
    "partnerships.view",
    "partnerships.manage",
    "sponsorships.view",
    "sponsorships.manage",
    "sponsorships.approve",
    "advertising.view",
    "advertising.manage",
    "advertising.manage_inventory",
    "advertising.manage_bookings",
    "media_kit.manage",
    "affiliates.view",
    "affiliates.manage",
    "affiliates.manage_links",
    "partnership_finance.view",
    "partnership_finance.manage",
    "partnership_reports.export",
    "newsletters.manage",
    "subscribers.view",
    "subscribers.manage",
    "subscribers.export",
    "newsletters.view",
    "newsletters.create",
    "newsletters.edit",
    "newsletters.publish",
    "newsletters.send",
    "newsletters.schedule",
    "newsletters.reports",
    "email_templates.manage",
    "email_automations.manage",
    "lead_magnets.manage",
    "email_settings.manage",
    "courses.manage",
    "memberships.manage",
    "finance.view",
    "finance.export",
    "finance.manage",
    "users.view",
    "users.manage",
    "roles.manage",
    "roles.assign",
    "audit.view",
]


def _permissions_table():
    return sa.table(
        "permissions",
        sa.column("id", sa.Integer),
        sa.column("key", sa.String),
        sa.column("label", sa.String),
        sa.column("description", sa.String),
        sa.column("group", sa.String),
        sa.column("module", sa.String),
        sa.column("is_available", sa.Boolean),
        sa.column("is_sensitive", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )


def _sync_permissions():
    bind = op.get_bind()
    permissions = _permissions_table()
    roles = sa.table("roles", sa.column("id", sa.Integer), sa.column("name", sa.String))
    links = sa.table(
        "role_permissions", sa.column("role_id", sa.Integer), sa.column("permission_id", sa.Integer)
    )
    existing = dict(bind.execute(sa.select(permissions.c.key, permissions.c.id)).all())
    for key, label, desc, group, module, available, sensitive in CHANGED:
        values = {
            "label": label,
            "description": desc,
            "group": group,
            "module": module,
            "is_available": available,
            "is_sensitive": sensitive,
        }
        if key in existing:
            bind.execute(
                permissions.update().where(permissions.c.id == existing[key]).values(**values)
            )
        else:
            bind.execute(permissions.insert().values(key=key, sort_order=0, **values))
    for order, key in enumerate(ORDER):
        bind.execute(permissions.update().where(permissions.c.key == key).values(sort_order=order))
    perm_ids = dict(bind.execute(sa.select(permissions.c.key, permissions.c.id)).all())
    role_ids = dict(bind.execute(sa.select(roles.c.name, roles.c.id)).all())
    current = set(bind.execute(sa.select(links.c.role_id, links.c.permission_id)).all())
    wanted = set()
    for role, keys in GRANTS.items():
        if role in role_ids:  # templates deleted by an administrator stay deleted
            wanted |= {(role_ids[role], perm_ids[k]) for k in keys if k in perm_ids}
    rows = [{"role_id": r, "permission_id": p} for r, p in sorted(wanted - current)]
    if rows:
        op.bulk_insert(links, rows)


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "ad_placements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("placement_type", sa.String(length=30), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("dimensions", sa.String(length=60), nullable=False),
        sa.Column(
            "creative_formats",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("exclusive", sa.Boolean(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("pricing_model", sa.String(length=20), nullable=False),
        sa.Column("default_currency", sa.String(length=3), nullable=False),
        sa.Column("impressions_measured", sa.Boolean(), nullable=False),
        sa.Column("restrictions", sa.String(length=1000), nullable=False),
        sa.Column("internal_notes", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "channel IN ('website', 'newsletter', 'social', 'other')",
            name=op.f("ck_ad_placements_channel_valid"),
        ),
        sa.CheckConstraint(
            "placement_type IN ('homepage_sponsor', 'article_sponsor', 'in_article_banner', 'sidebar', 'footer_promotion', 'newsletter_sponsor', 'sponsored_article', 'brand_spotlight', 'landing_page')",
            name=op.f("ck_ad_placements_type_valid"),
        ),
        sa.CheckConstraint(
            "pricing_model IN ('fixed_fee', 'per_placement', 'package', 'cpm')",
            name=op.f("ck_ad_placements_pricing_valid"),
        ),
        sa.CheckConstraint("capacity >= 1", name=op.f("ck_ad_placements_capacity_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ad_placements")),
        sa.UniqueConstraint("key", name=op.f("uq_ad_placements_key")),
    )
    op.create_table(
        "affiliate_programs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("merchant", sa.String(length=160), nullable=False),
        sa.Column("network", sa.String(length=120), nullable=False),
        sa.Column("website", sa.String(length=300), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("commission_model", sa.String(length=80), nullable=False),
        sa.Column("commission_rate", sa.String(length=60), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("payout_threshold_minor", sa.BigInteger(), nullable=True),
        sa.Column("account_status", sa.String(length=20), nullable=False),
        sa.Column("account_identifier", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("terms_url", sa.String(length=500), nullable=False),
        sa.Column("last_verified_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "account_status IN ('not_applied', 'applied', 'approved', 'rejected', 'paused', 'closed')",
            name=op.f("ck_affiliate_programs_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_affiliate_programs")),
    )
    op.create_table(
        "audience_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_type", sa.String(length=40), nullable=False),
        sa.Column("value", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("platform", sa.String(length=80), nullable=False),
        sa.Column("period_label", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=300), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.String(length=600), nullable=False),
        sa.Column("entered_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("value >= 0", name=op.f("ck_audience_metrics_value_nonnegative")),
        sa.ForeignKeyConstraint(
            ["entered_by_id"],
            ["users.id"],
            name=op.f("fk_audience_metrics_entered_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audience_metrics")),
    )
    op.create_table(
        "commercial_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("from_state", sa.String(length=30), nullable=False),
        sa.Column("to_state", sa.String(length=30), nullable=False),
        sa.Column("summary", sa.String(length=2000), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_commercial_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_commercial_events")),
    )
    with op.batch_alter_table("commercial_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_commercial_events_entity", ["entity_type", "entity_id", "created_at"], unique=False
        )

    op.create_table(
        "rate_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("placement_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("pricing_model", sa.String(length=20), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("unit_label", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=600), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "pricing_model IN ('fixed_fee', 'per_placement', 'package', 'cpm')",
            name=op.f("ck_rate_cards_pricing_valid"),
        ),
        sa.CheckConstraint("amount_minor >= 0", name=op.f("ck_rate_cards_amount_nonnegative")),
        sa.ForeignKeyConstraint(
            ["placement_id"],
            ["ad_placements.id"],
            name=op.f("fk_rate_cards_placement_id_ad_placements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rate_cards")),
    )
    with op.batch_alter_table("rate_cards", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_rate_cards_placement_id"), ["placement_id"], unique=False
        )

    op.create_table(
        "partners",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("website", sa.String(length=300), nullable=False),
        sa.Column("logo_media_id", sa.Integer(), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("country", sa.String(length=80), nullable=False),
        sa.Column("partnership_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("internal_notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "partnership_type IN ('sponsorship', 'advertising', 'affiliate', 'content_collaboration', 'newsletter_sponsorship', 'event', 'other')",
            name=op.f("ck_partners_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('prospect', 'active', 'inactive', 'archived')",
            name=op.f("ck_partners_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["logo_media_id"],
            ["media_assets.id"],
            name=op.f("fk_partners_logo_media_id_media_assets"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_partners_owner_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partners")),
    )
    with op.batch_alter_table("partners", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_partners_owner_id"), ["owner_id"], unique=False)

    op.create_table(
        "partner_contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partners.id"],
            name=op.f("fk_partner_contacts_partner_id_partners"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partner_contacts")),
    )
    with op.batch_alter_table("partner_contacts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_partner_contacts_partner_id"), ["partner_id"], unique=False
        )

    op.create_table(
        "partnership_opportunities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("expected_value_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("follow_up_on", sa.Date(), nullable=True),
        sa.Column("internal_reference", sa.String(length=200), nullable=False),
        sa.Column("proposal_reference", sa.String(length=300), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("lost_reason", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "stage IN ('new_inquiry', 'qualification', 'proposal', 'negotiation', 'approved', 'contracted', 'active', 'completed', 'lost', 'cancelled')",
            name=op.f("ck_partnership_opportunities_stage_valid"),
        ),
        sa.CheckConstraint(
            "expected_value_minor IS NULL OR expected_value_minor >= 0",
            name=op.f("ck_partnership_opportunities_expected_value_minor_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_partnership_opportunities_owner_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partners.id"],
            name=op.f("fk_partnership_opportunities_partner_id_partners"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partnership_opportunities")),
    )
    with op.batch_alter_table("partnership_opportunities", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_partnership_opportunities_partner_id"), ["partner_id"], unique=False
        )
        batch_op.create_index(
            "ix_partnership_opportunities_stage", ["stage", "follow_up_on"], unique=False
        )

    op.create_table(
        "affiliate_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=True),
        sa.Column("merchant", sa.String(length=160), nullable=False),
        sa.Column("target_url", sa.String(length=1000), nullable=False),
        sa.Column("campaign", sa.String(length=120), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("utm_source", sa.String(length=80), nullable=False),
        sa.Column("utm_medium", sa.String(length=80), nullable=False),
        sa.Column("utm_campaign", sa.String(length=80), nullable=False),
        sa.Column("disclosure_required", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name=op.f("fk_affiliate_links_article_id_articles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_affiliate_links_product_id_products"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["affiliate_programs.id"],
            name=op.f("fk_affiliate_links_program_id_affiliate_programs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_affiliate_links")),
        sa.UniqueConstraint("slug", name=op.f("uq_affiliate_links_slug")),
    )
    with op.batch_alter_table("affiliate_links", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_affiliate_links_program_id"), ["program_id"], unique=False
        )

    op.create_table(
        "partnership_inquiries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization", sa.String(length=160), nullable=False),
        sa.Column("contact_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("website", sa.String(length=300), nullable=False),
        sa.Column("collaboration_type", sa.String(length=40), nullable=False),
        sa.Column("budget_range", sa.String(length=60), nullable=False),
        sa.Column("objectives", sa.String(length=2000), nullable=False),
        sa.Column("message", sa.String(length=4000), nullable=False),
        sa.Column("privacy_notice_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("notification_status", sa.String(length=30), nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('new', 'reviewed', 'converted', 'declined', 'spam')",
            name=op.f("ck_partnership_inquiries_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["partnership_opportunities.id"],
            name=op.f("fk_partnership_inquiries_opportunity_id_partnership_opportunities"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partners.id"],
            name=op.f("fk_partnership_inquiries_partner_id_partners"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partnership_inquiries")),
    )
    with op.batch_alter_table("partnership_inquiries", schema=None) as batch_op:
        batch_op.create_index(
            "ix_partnership_inquiries_status_created", ["status", "created_at"], unique=False
        )

    op.create_table(
        "sponsorship_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("contracted_fee_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("disclosure_text", sa.String(length=400), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("approved_by_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'internal_review', 'sponsor_review', 'approved', 'scheduled', 'active', 'completed', 'cancelled')",
            name=op.f("ck_sponsorship_campaigns_status_valid"),
        ),
        sa.CheckConstraint(
            "contracted_fee_minor IS NULL OR contracted_fee_minor >= 0",
            name=op.f("ck_sponsorship_campaigns_contracted_fee_minor_nonnegative"),
        ),
        sa.CheckConstraint(
            "starts_on IS NULL OR ends_on IS NULL OR ends_on >= starts_on",
            name=op.f("ck_sponsorship_campaigns_dates_ordered"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_id"],
            ["users.id"],
            name=op.f("fk_sponsorship_campaigns_approved_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["partnership_opportunities.id"],
            name=op.f("fk_sponsorship_campaigns_opportunity_id_partnership_opportunities"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partners.id"],
            name=op.f("fk_sponsorship_campaigns_partner_id_partners"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sponsorship_campaigns")),
    )
    with op.batch_alter_table("sponsorship_campaigns", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_sponsorship_campaigns_partner_id"), ["partner_id"], unique=False
        )

    op.create_table(
        "ad_bookings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("placement_id", sa.Integer(), nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("agreed_fee_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("headline", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=400), nullable=False),
        sa.Column("image_media_id", sa.Integer(), nullable=True),
        sa.Column("link_url", sa.String(length=500), nullable=False),
        sa.Column("link_label", sa.String(length=60), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=False),
        sa.Column("approved_by_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'paused', 'stopped', 'cancelled')",
            name=op.f("ck_ad_bookings_status_valid"),
        ),
        sa.CheckConstraint(
            "agreed_fee_minor IS NULL OR agreed_fee_minor >= 0",
            name=op.f("ck_ad_bookings_agreed_fee_minor_nonnegative"),
        ),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_ad_bookings_window_valid")),
        sa.ForeignKeyConstraint(
            ["approved_by_id"],
            ["users.id"],
            name=op.f("fk_ad_bookings_approved_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["sponsorship_campaigns.id"],
            name=op.f("fk_ad_bookings_campaign_id_sponsorship_campaigns"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["image_media_id"],
            ["media_assets.id"],
            name=op.f("fk_ad_bookings_image_media_id_media_assets"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partners.id"],
            name=op.f("fk_ad_bookings_partner_id_partners"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["placement_id"],
            ["ad_placements.id"],
            name=op.f("fk_ad_bookings_placement_id_ad_placements"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ad_bookings")),
    )
    with op.batch_alter_table("ad_bookings", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_ad_bookings_partner_id"), ["partner_id"], unique=False)
        batch_op.create_index(
            "ix_ad_bookings_placement_window",
            ["placement_id", "starts_at", "ends_at"],
            unique=False,
        )

    op.create_table(
        "affiliate_click_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("source_path", sa.String(length=300), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["link_id"],
            ["affiliate_links.id"],
            name=op.f("fk_affiliate_click_daily_link_id_affiliate_links"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_affiliate_click_daily")),
        sa.UniqueConstraint(
            "link_id", "day", "source_path", name=op.f("uq_affiliate_click_daily_link_id")
        ),
    )
    op.create_table(
        "affiliate_commissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("link_id", sa.Integer(), nullable=True),
        sa.Column("external_reference", sa.String(length=160), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("import_batch", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.String(length=600), nullable=False),
        sa.Column("entered_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('import', 'manual')", name=op.f("ck_affiliate_commissions_source_valid")
        ),
        sa.CheckConstraint(
            "status IN ('reported', 'approved', 'paid', 'reversed')",
            name=op.f("ck_affiliate_commissions_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["entered_by_id"],
            ["users.id"],
            name=op.f("fk_affiliate_commissions_entered_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["link_id"],
            ["affiliate_links.id"],
            name=op.f("fk_affiliate_commissions_link_id_affiliate_links"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["affiliate_programs.id"],
            name=op.f("fk_affiliate_commissions_program_id_affiliate_programs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_affiliate_commissions")),
        sa.UniqueConstraint(
            "program_id", "external_reference", name=op.f("uq_affiliate_commissions_program_id")
        ),
    )
    with op.batch_alter_table("affiliate_commissions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_affiliate_commissions_program_id"), ["program_id"], unique=False
        )

    op.create_table(
        "article_sponsorships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=True),
        sa.Column("campaign_id", sa.Integer(), nullable=True),
        sa.Column("sponsor_name", sa.String(length=160), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("disclosure_text", sa.String(length=400), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("sponsor_approval_notes", sa.String(length=2000), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column(
            "sponsored_links",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "sponsor_media_ids",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("approved_by_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "review_status IN ('draft', 'internal_review', 'sponsor_review', 'approved')",
            name=op.f("ck_article_sponsorships_review_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_id"],
            ["users.id"],
            name=op.f("fk_article_sponsorships_approved_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name=op.f("fk_article_sponsorships_article_id_articles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["sponsorship_campaigns.id"],
            name=op.f("fk_article_sponsorships_campaign_id_sponsorship_campaigns"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partners.id"],
            name=op.f("fk_article_sponsorships_partner_id_partners"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_article_sponsorships")),
        sa.UniqueConstraint("article_id", name=op.f("uq_article_sponsorships_article_id")),
    )
    op.create_table(
        "newsletter_sponsorships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("sponsorship_campaign_id", sa.Integer(), nullable=True),
        sa.Column("sponsor_name", sa.String(length=160), nullable=False),
        sa.Column("disclosure_text", sa.String(length=400), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["email_campaigns.id"],
            name=op.f("fk_newsletter_sponsorships_campaign_id_email_campaigns"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sponsorship_campaign_id"],
            ["sponsorship_campaigns.id"],
            name=op.f("fk_newsletter_sponsorships_sponsorship_campaign_id_sponsorship_campaigns"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_newsletter_sponsorships")),
        sa.UniqueConstraint("campaign_id", name=op.f("uq_newsletter_sponsorships_campaign_id")),
    )
    op.create_table(
        "partnership_finance_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=False),
        sa.Column("entered_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('invoiced', 'received')",
            name=op.f("ck_partnership_finance_entries_kind_valid"),
        ),
        sa.CheckConstraint(
            "amount_minor > 0", name=op.f("ck_partnership_finance_entries_amount_positive")
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["sponsorship_campaigns.id"],
            name=op.f("fk_partnership_finance_entries_campaign_id_sponsorship_campaigns"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["entered_by_id"],
            ["users.id"],
            name=op.f("fk_partnership_finance_entries_entered_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partners.id"],
            name=op.f("fk_partnership_finance_entries_partner_id_partners"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partnership_finance_entries")),
    )
    with op.batch_alter_table("partnership_finance_entries", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_partnership_finance_entries_partner_id"), ["partner_id"], unique=False
        )
    # ### end Alembic commands ###
    _sync_permissions()


def downgrade():
    bind = op.get_bind()
    permissions = _permissions_table()
    ids = [
        r[0]
        for r in bind.execute(
            sa.select(permissions.c.id).where(permissions.c.key.in_(NEW_KEYS + NOW_AVAILABLE))
        )
    ]
    if ids:
        bind.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": ids},
        )
    bind.execute(permissions.delete().where(permissions.c.key.in_(NEW_KEYS)))
    bind.execute(
        permissions.update().where(permissions.c.key.in_(NOW_AVAILABLE)).values(is_available=False)
    )
    with op.batch_alter_table("partnership_finance_entries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_partnership_finance_entries_partner_id"))

    op.drop_table("partnership_finance_entries")
    op.drop_table("newsletter_sponsorships")
    op.drop_table("article_sponsorships")
    with op.batch_alter_table("affiliate_commissions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_affiliate_commissions_program_id"))

    op.drop_table("affiliate_commissions")
    op.drop_table("affiliate_click_daily")
    with op.batch_alter_table("ad_bookings", schema=None) as batch_op:
        batch_op.drop_index("ix_ad_bookings_placement_window")
        batch_op.drop_index(batch_op.f("ix_ad_bookings_partner_id"))

    op.drop_table("ad_bookings")
    with op.batch_alter_table("sponsorship_campaigns", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sponsorship_campaigns_partner_id"))

    op.drop_table("sponsorship_campaigns")
    with op.batch_alter_table("partnership_inquiries", schema=None) as batch_op:
        batch_op.drop_index("ix_partnership_inquiries_status_created")

    op.drop_table("partnership_inquiries")
    with op.batch_alter_table("affiliate_links", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_affiliate_links_program_id"))

    op.drop_table("affiliate_links")
    with op.batch_alter_table("partnership_opportunities", schema=None) as batch_op:
        batch_op.drop_index("ix_partnership_opportunities_stage")
        batch_op.drop_index(batch_op.f("ix_partnership_opportunities_partner_id"))

    op.drop_table("partnership_opportunities")
    with op.batch_alter_table("partner_contacts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_partner_contacts_partner_id"))

    op.drop_table("partner_contacts")
    with op.batch_alter_table("partners", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_partners_owner_id"))

    op.drop_table("partners")
    with op.batch_alter_table("rate_cards", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_rate_cards_placement_id"))

    op.drop_table("rate_cards")
    with op.batch_alter_table("commercial_events", schema=None) as batch_op:
        batch_op.drop_index("ix_commercial_events_entity")

    op.drop_table("commercial_events")
    op.drop_table("audience_metrics")
    op.drop_table("affiliate_programs")
    op.drop_table("ad_placements")
    # ### end Alembic commands ###
