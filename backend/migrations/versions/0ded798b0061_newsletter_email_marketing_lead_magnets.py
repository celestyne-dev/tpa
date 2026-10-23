"""Newsletter, email marketing, lead magnets and audience growth (The Positive Reset).

Incremental and non-destructive:
- new tables only: subscribers (consent evidence, preferences, tags, activity),
  a hashed suppression list, segments, email templates, campaigns, the email
  outbox (per-recipient delivery records), automations (steps, enrolments,
  trigger events) and lead magnets (claims with hashed, expiring tokens).
  No existing table or column is altered or rebuilt;
- permissions: subscribers.manage, newsletters.view/create/edit/publish/send/
  schedule/reports, email_templates.manage, email_automations.manage,
  lead_magnets.manage and the sensitive email_settings.manage are added; the
  previously planned subscribers.view and subscribers.export become available;
  newsletters.manage stays unavailable (superseded). Grants go to the
  Administrator, Newsletter Manager and Marketing Manager templates that still
  exist; editorial roles and custom roles gain nothing;
- no subscribers are created: customers and buyers are never subscribed.

Downgrade drops the newsletter tables (subscriber data included, so take a
backup first), removes the new permissions and returns subscribers.view/export
to "unavailable".

Revision ID: 0ded798b0061
Revises: 758d4c510551
Create Date: 2026-10-23 10:30:31.194610

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text  # noqa: F401  (used by rendered JSONB types)
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0ded798b0061"
down_revision = "758d4c510551"
branch_labels = None
depends_on = None

# Frozen snapshot of the Batch 06 permission changes.
# (key, label, description, group, module, available, sensitive)
GROUP = "Newsletters & subscribers"
NEW_PERMISSIONS = [
    (
        "subscribers.manage",
        "Manage subscribers",
        "Tags, segments, imports (quarantined), unsubscribes and suppressions.",
        False,
    ),
    ("newsletters.view", "View newsletters", "", False),
    ("newsletters.create", "Create newsletters", "", False),
    ("newsletters.edit", "Edit newsletter drafts", "", False),
    (
        "newsletters.publish",
        "Approve newsletters",
        "Approve a campaign for sending (any later edit withdraws the approval).",
        False,
    ),
    ("newsletters.send", "Send newsletters", "Send an approved campaign to its audience.", False),
    ("newsletters.schedule", "Schedule newsletters", "", False),
    ("newsletters.reports", "View newsletter reports", "", False),
    ("email_templates.manage", "Manage email templates", "", False),
    ("email_automations.manage", "Manage email automations", "", False),
    ("lead_magnets.manage", "Manage lead magnets", "", False),
    (
        "email_settings.manage",
        "Configure email sending",
        "Sending mode (disabled/test/live), sender identity, consent wording and "
        "deliverability confirmations.",
        True,
    ),
]
NEW_KEYS = [p[0] for p in NEW_PERMISSIONS]
NOW_AVAILABLE = ["subscribers.view", "subscribers.export"]
NOW_AVAILABLE_DESCRIPTIONS = {
    "subscribers.view": "",
    "subscribers.export": "Download subscriber personal data and consent records (audited).",
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
    "advertising.view",
    "advertising.manage",
    "affiliates.view",
    "affiliates.manage",
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
_EDITING = ["newsletters.view", "newsletters.create", "newsletters.edit", "newsletters.reports"]
_ALL = _EDITING + [
    "newsletters.publish",
    "newsletters.send",
    "newsletters.schedule",
    "email_templates.manage",
    "email_automations.manage",
    "lead_magnets.manage",
]
GRANTS = {
    "administrator": _ALL + ["subscribers.view", "subscribers.manage"],
    "newsletter_manager": _ALL
    + [
        "subscribers.view",
        "subscribers.manage",
        "subscribers.export",
        "media.view",
        "articles.view",
        "products.view",
    ],
    "marketing_manager": _EDITING + ["subscribers.view", "lead_magnets.manage", "media.view"],
}


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
    for key, label, desc, sensitive in NEW_PERMISSIONS:
        values = {
            "label": label,
            "description": desc,
            "group": GROUP,
            "module": "newsletters",
            "is_available": True,
            "is_sensitive": sensitive,
        }
        if key in existing:
            bind.execute(
                permissions.update().where(permissions.c.id == existing[key]).values(**values)
            )
        else:
            bind.execute(permissions.insert().values(key=key, sort_order=0, **values))
    for key, description in NOW_AVAILABLE_DESCRIPTIONS.items():
        bind.execute(
            permissions.update()
            .where(permissions.c.key == key)
            .values(is_available=True, description=description)
        )
    bind.execute(
        permissions.update()
        .where(permissions.c.key == "newsletters.manage")
        .values(
            label="Manage newsletters (superseded)",
            description="Replaced in Batch 06 by the specific newsletters.* permissions.",
            is_available=False,
        )
    )
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
        "email_automation_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=40), nullable=False),
        sa.Column("context_key", sa.String(length=120), nullable=False),
        sa.Column(
            "context",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("enrolled_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_automation_events")),
        sa.UniqueConstraint(
            "trigger", "context_key", name=op.f("uq_email_automation_events_trigger")
        ),
    )
    op.create_table(
        "subscriber_tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriber_tags")),
        sa.UniqueConstraint("slug", name=op.f("uq_subscriber_tags_slug")),
    )
    op.create_table(
        "subscribers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("first_name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("source_detail", sa.String(length=200), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_text", sa.String(length=1000), nullable=False),
        sa.Column("consent_version", sa.String(length=40), nullable=False),
        sa.Column("consent_ip_hash", sa.String(length=64), nullable=False),
        sa.Column("confirmation_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribe_reason", sa.String(length=300), nullable=False),
        sa.Column("notice_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "preferences",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "interests",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("last_engaged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_batch", sa.String(length=40), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'subscribed', 'unsubscribed', 'bounced', 'complained', 'quarantined')",
            name=op.f("ck_subscribers_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscribers")),
        sa.UniqueConstraint("email", name=op.f("uq_subscribers_email")),
        sa.UniqueConstraint("public_id", name=op.f("uq_subscribers_public_id")),
    )
    with op.batch_alter_table("subscribers", schema=None) as batch_op:
        batch_op.create_index("ix_subscribers_status_source", ["status", "source"], unique=False)

    op.create_table(
        "email_suppressions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=60), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reason IN ('unsubscribed', 'bounced', 'complained', 'manual', 'erased')",
            name=op.f("ck_email_suppressions_reason_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_email_suppressions_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_suppressions")),
        sa.UniqueConstraint("email_hash", name=op.f("uq_email_suppressions_email_hash")),
    )
    op.create_table(
        "email_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("preheader", sa.String(length=200), nullable=False),
        sa.Column(
            "blocks",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("is_starter", sa.Boolean(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('campaign', 'automation')", name=op.f("ck_email_templates_kind_valid")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_email_templates_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_templates")),
        sa.UniqueConstraint("key", name=op.f("uq_email_templates_key")),
    )
    op.create_table(
        "subscriber_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column(
            "details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_subscriber_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["subscriber_id"],
            ["subscribers.id"],
            name=op.f("fk_subscriber_events_subscriber_id_subscribers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriber_events")),
    )
    with op.batch_alter_table("subscriber_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_subscriber_events_subscriber", ["subscriber_id", "created_at"], unique=False
        )

    op.create_table(
        "subscriber_segments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column(
            "rules",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_subscriber_segments_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriber_segments")),
        sa.UniqueConstraint("slug", name=op.f("uq_subscriber_segments_slug")),
    )
    op.create_table(
        "subscriber_tag_links",
        sa.Column("subscriber_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["subscriber_id"],
            ["subscribers.id"],
            name=op.f("fk_subscriber_tag_links_subscriber_id_subscribers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["subscriber_tags.id"],
            name=op.f("fk_subscriber_tag_links_tag_id_subscriber_tags"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("subscriber_id", "tag_id", name=op.f("pk_subscriber_tag_links")),
    )
    op.create_table(
        "email_automations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=400), nullable=False),
        sa.Column("trigger", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("segment_id", sa.Integer(), nullable=True),
        sa.Column("required_preference", sa.String(length=40), nullable=False),
        sa.Column(
            "settings",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused')",
            name=op.f("ck_email_automations_status_valid"),
        ),
        sa.CheckConstraint(
            "trigger IN ('subscription_confirmed', 'lead_magnet_claimed', 'article_published', 'product_published', 'inactive')",
            name=op.f("ck_email_automations_trigger_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["subscriber_segments.id"],
            name=op.f("fk_email_automations_segment_id_subscriber_segments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_email_automations_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_automations")),
        sa.UniqueConstraint("key", name=op.f("uq_email_automations_key")),
    )
    op.create_table(
        "email_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("preheader", sa.String(length=200), nullable=False),
        sa.Column("from_name", sa.String(length=80), nullable=False),
        sa.Column("reply_to", sa.String(length=254), nullable=False),
        sa.Column("template_key", sa.String(length=60), nullable=False),
        sa.Column(
            "blocks",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "article_ids",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "product_ids",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "ctas",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("segment_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.Integer(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("send_mode", sa.String(length=10), nullable=False),
        sa.Column("eligible_count", sa.Integer(), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'scheduled', 'sending', 'sent', 'cancelled')",
            name=op.f("ck_email_campaigns_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_id"],
            ["users.id"],
            name=op.f("fk_email_campaigns_approved_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_email_campaigns_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["subscriber_segments.id"],
            name=op.f("fk_email_campaigns_segment_id_subscriber_segments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_email_campaigns_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_campaigns")),
        sa.UniqueConstraint("public_id", name=op.f("uq_email_campaigns_public_id")),
    )
    with op.batch_alter_table("email_campaigns", schema=None) as batch_op:
        batch_op.create_index(
            "ix_email_campaigns_status_scheduled", ["status", "scheduled_at"], unique=False
        )

    op.create_table(
        "email_automation_enrollments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("automation_id", sa.Integer(), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), nullable=False),
        sa.Column("context_key", sa.String(length=120), nullable=False),
        sa.Column(
            "context",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("next_position", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_reason", sa.String(length=120), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'exited')",
            name=op.f("ck_email_automation_enrollments_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["automation_id"],
            ["email_automations.id"],
            name=op.f("fk_email_automation_enrollments_automation_id_email_automations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subscriber_id"],
            ["subscribers.id"],
            name=op.f("fk_email_automation_enrollments_subscriber_id_subscribers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_automation_enrollments")),
        sa.UniqueConstraint(
            "automation_id",
            "subscriber_id",
            "context_key",
            name=op.f("uq_email_automation_enrollments_automation_id"),
        ),
    )
    with op.batch_alter_table("email_automation_enrollments", schema=None) as batch_op:
        batch_op.create_index(
            "ix_email_automation_enrollments_due", ["status", "next_run_at"], unique=False
        )

    op.create_table(
        "email_automation_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("automation_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("delay_minutes", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("preheader", sa.String(length=200), nullable=False),
        sa.Column(
            "blocks",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["automation_id"],
            ["email_automations.id"],
            name=op.f("fk_email_automation_steps_automation_id_email_automations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_automation_steps")),
        sa.UniqueConstraint(
            "automation_id", "position", name=op.f("uq_email_automation_steps_automation_id")
        ),
    )
    op.create_table(
        "email_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=True),
        sa.Column("enrollment_id", sa.Integer(), nullable=True),
        sa.Column("subscriber_id", sa.Integer(), nullable=True),
        sa.Column("to_email", sa.String(length=254), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("send_mode", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.String(length=80), nullable=False),
        sa.Column("attempt_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=False),
        sa.Column("error", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bounced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("complained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('campaign', 'automation', 'confirmation', 'lead_magnet', 'notice', 'test')",
            name=op.f("ck_email_messages_kind_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'sending', 'accepted', 'delivered', 'bounced', 'complained', 'failed', 'unknown', 'cancelled', 'suppressed', 'skipped')",
            name=op.f("ck_email_messages_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["email_campaigns.id"],
            name=op.f("fk_email_messages_campaign_id_email_campaigns"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id"],
            ["email_automation_enrollments.id"],
            name=op.f("fk_email_messages_enrollment_id_email_automation_enrollments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["subscriber_id"],
            ["subscribers.id"],
            name=op.f("fk_email_messages_subscriber_id_subscribers"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_messages")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_email_messages_dedupe_key")),
    )
    with op.batch_alter_table("email_messages", schema=None) as batch_op:
        batch_op.create_index(
            "ix_email_messages_campaign_status", ["campaign_id", "status"], unique=False
        )
        batch_op.create_index("ix_email_messages_due", ["status", "next_attempt_at"], unique=False)
        batch_op.create_index(
            "ix_email_messages_provider_id", ["provider_message_id"], unique=False
        )

    op.create_table(
        "lead_magnets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=600), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("newsletter_optin", sa.String(length=20), nullable=False),
        sa.Column("optin_notice", sa.String(length=600), nullable=False),
        sa.Column("link_ttl_hours", sa.Integer(), nullable=True),
        sa.Column("max_downloads", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "newsletter_optin IN ('optional', 'required')", name=op.f("ck_lead_magnets_optin_valid")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')", name=op.f("ck_lead_magnets_status_valid")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_lead_magnets_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_lead_magnets_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_magnets")),
        sa.UniqueConstraint("slug", name=op.f("uq_lead_magnets_slug")),
    )
    op.create_table(
        "lead_magnet_claims",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lead_magnet_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("download_count", sa.Integer(), nullable=False),
        sa.Column("max_downloads", sa.Integer(), nullable=True),
        sa.Column("last_download_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["lead_magnet_id"],
            ["lead_magnets.id"],
            name=op.f("fk_lead_magnet_claims_lead_magnet_id_lead_magnets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subscriber_id"],
            ["subscribers.id"],
            name=op.f("fk_lead_magnet_claims_subscriber_id_subscribers"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_magnet_claims")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_lead_magnet_claims_token_hash")),
    )
    with op.batch_alter_table("lead_magnet_claims", schema=None) as batch_op:
        batch_op.create_index(
            "ix_lead_magnet_claims_email", ["lead_magnet_id", "email"], unique=False
        )

    # ### end Alembic commands ###
    _sync_permissions()


def downgrade():
    bind = op.get_bind()
    permissions = _permissions_table()
    gone = NEW_KEYS + NOW_AVAILABLE
    ids = [
        r[0] for r in bind.execute(sa.select(permissions.c.id).where(permissions.c.key.in_(gone)))
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
    with op.batch_alter_table("lead_magnet_claims", schema=None) as batch_op:
        batch_op.drop_index("ix_lead_magnet_claims_email")

    op.drop_table("lead_magnet_claims")
    op.drop_table("lead_magnets")
    with op.batch_alter_table("email_messages", schema=None) as batch_op:
        batch_op.drop_index("ix_email_messages_provider_id")
        batch_op.drop_index("ix_email_messages_due")
        batch_op.drop_index("ix_email_messages_campaign_status")

    op.drop_table("email_messages")
    op.drop_table("email_automation_steps")
    with op.batch_alter_table("email_automation_enrollments", schema=None) as batch_op:
        batch_op.drop_index("ix_email_automation_enrollments_due")

    op.drop_table("email_automation_enrollments")
    with op.batch_alter_table("email_campaigns", schema=None) as batch_op:
        batch_op.drop_index("ix_email_campaigns_status_scheduled")

    op.drop_table("email_campaigns")
    op.drop_table("email_automations")
    op.drop_table("subscriber_tag_links")
    op.drop_table("subscriber_segments")
    with op.batch_alter_table("subscriber_events", schema=None) as batch_op:
        batch_op.drop_index("ix_subscriber_events_subscriber")

    op.drop_table("subscriber_events")
    op.drop_table("email_templates")
    op.drop_table("email_suppressions")
    with op.batch_alter_table("subscribers", schema=None) as batch_op:
        batch_op.drop_index("ix_subscribers_status_source")

    op.drop_table("subscribers")
    op.drop_table("subscriber_tags")
    op.drop_table("email_automation_events")
    # ### end Alembic commands ###
