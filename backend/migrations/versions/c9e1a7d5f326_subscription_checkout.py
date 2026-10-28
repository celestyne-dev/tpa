"""Membership subscriptions: provider plans, subscriptions, billing periods and events
(Batch 10.2: test-mode checkout and verified first-payment activation).

Revision ID: c9e1a7d5f326
Revises: b8d0f6c4e215
Create Date: 2026-10-28

- New tables ``membership_provider_plans``, ``customer_subscriptions``,
  ``subscription_periods`` and ``subscription_events``.
- ``membership_plans.product_id`` (hidden backing product for subscription orders).
- ``orders.kind`` (``purchase`` | ``subscription``); every existing order becomes
  ``purchase``.
- Course enrolments accept the source ``membership``.

Existing orders, payments, entitlements and enrolments are unchanged. Downgrade refuses
while any subscription or subscription order exists.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text  # noqa: F401  (used by rendered JSONB types)
from sqlalchemy.dialects import postgresql

revision = "c9e1a7d5f326"
down_revision = "b8d0f6c4e215"
branch_labels = None
depends_on = None

LIVE = "status IN ('pending', 'active', 'past_due', 'grace')"


def _json():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


def _foreign_keys(enabled: bool) -> None:
    """SQLite rebuilds ``orders`` and ``course_enrollments`` (both referenced by other
    tables) to change constraints; dropping the old table must not cascade, so
    enforcement is paused meanwhile (it can only change outside a transaction)."""
    if op.get_bind().dialect.name == "sqlite":
        with op.get_context().autocommit_block():
            op.execute(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")


def upgrade():
    op.create_table(
        "membership_provider_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("price_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("plan_code", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mode IN ('test', 'live')", name=op.f("ck_membership_provider_plans_mode_valid")
        ),
        sa.ForeignKeyConstraint(
            ["price_id"],
            ["membership_plan_prices.id"],
            name=op.f("fk_membership_provider_plans_price_id_membership_plan_prices"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership_provider_plans")),
        sa.UniqueConstraint(
            "provider", "mode", "price_id", name=op.f("uq_membership_provider_plans_price")
        ),
        sa.UniqueConstraint(
            "provider", "plan_code", name=op.f("uq_membership_provider_plans_code")
        ),
    )
    op.create_table(
        "customer_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=24), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("price_id", sa.Integer(), nullable=False),
        sa.Column("provider_plan_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("interval", sa.String(length=10), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("provider_customer_code", sa.String(length=60), nullable=True),
        sa.Column("provider_subscription_code", sa.String(length=60), nullable=True),
        sa.Column("provider_email_token", sa.String(length=100), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(length=60), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'past_due', 'grace', 'incomplete', 'ended')",
            name=op.f("ck_customer_subscriptions_status_valid"),
        ),
        sa.CheckConstraint(
            "mode IN ('test', 'live')", name=op.f("ck_customer_subscriptions_mode_valid")
        ),
        sa.CheckConstraint(
            "amount_minor > 0", name=op.f("ck_customer_subscriptions_amount_positive")
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_customer_subscriptions_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_customer_subscriptions_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["membership_plans.id"],
            name=op.f("fk_customer_subscriptions_plan_id_membership_plans"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["price_id"],
            ["membership_plan_prices.id"],
            name=op.f("fk_customer_subscriptions_price_id_membership_plan_prices"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provider_plan_id"],
            ["membership_provider_plans.id"],
            name=op.f("fk_customer_subscriptions_provider_plan_id_membership_provider_plans"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_subscriptions")),
        sa.UniqueConstraint(
            "customer_id", "idempotency_key", name=op.f("uq_customer_subscriptions_key")
        ),
        sa.UniqueConstraint("order_id", name=op.f("uq_customer_subscriptions_order_id")),
        sa.UniqueConstraint(
            "provider_subscription_code",
            name=op.f("uq_customer_subscriptions_provider_subscription_code"),
        ),
        sa.UniqueConstraint("public_id", name=op.f("uq_customer_subscriptions_public_id")),
    )
    with op.batch_alter_table("customer_subscriptions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_customer_subscriptions_customer_id"), ["customer_id"], unique=False
        )
        batch_op.create_index("ix_customer_subscriptions_status", ["status"], unique=False)
        batch_op.create_index(
            "uq_customer_subscriptions_live",
            ["customer_id"],
            unique=True,
            postgresql_where=sa.text(LIVE),
            sqlite_where=sa.text(LIVE),
        )
    op.create_table(
        "subscription_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("provider_invoice_code", sa.String(length=60), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'paid', 'failed', 'refunded', 'void')",
            name=op.f("ck_subscription_periods_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_subscription_periods_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["customer_subscriptions.id"],
            name=op.f("fk_subscription_periods_subscription_id_customer_subscriptions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_periods")),
        sa.UniqueConstraint(
            "provider_invoice_code", name=op.f("uq_subscription_periods_provider_invoice_code")
        ),
        sa.UniqueConstraint(
            "subscription_id", "sequence", name=op.f("uq_subscription_periods_sequence")
        ),
    )
    op.create_table(
        "subscription_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("payment_event_id", sa.Integer(), nullable=True),
        sa.Column("details", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('customer', 'webhook', 'verification', 'admin', 'job', 'system')",
            name=op.f("ck_subscription_events_source_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["payment_event_id"],
            ["payment_events.id"],
            name=op.f("fk_subscription_events_payment_event_id_payment_events"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["customer_subscriptions.id"],
            name=op.f("fk_subscription_events_subscription_id_customer_subscriptions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_events")),
    )
    with op.batch_alter_table("subscription_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_subscription_events_subscription", ["subscription_id", "id"], unique=False
        )

    _foreign_keys(False)
    try:
        with op.batch_alter_table("membership_plans", schema=None) as batch_op:
            batch_op.add_column(sa.Column("product_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                batch_op.f("fk_membership_plans_product_id_products"),
                "products",
                ["product_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        with op.batch_alter_table("orders", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("kind", sa.String(length=20), server_default="purchase", nullable=False)
            )
            batch_op.create_check_constraint(
                batch_op.f("ck_orders_kind_valid"), "kind IN ('purchase', 'subscription')"
            )
        with op.batch_alter_table("course_enrollments", schema=None) as batch_op:
            batch_op.drop_constraint(
                batch_op.f("ck_course_enrollments_source_valid"), type_="check"
            )
            batch_op.create_check_constraint(
                batch_op.f("ck_course_enrollments_source_valid"),
                "source IN ('free', 'purchase', 'manual', 'membership')",
            )
    finally:
        _foreign_keys(True)


def downgrade():
    bind = op.get_bind()
    for sql, problem in (
        ("SELECT COUNT(*) FROM customer_subscriptions", "Membership subscriptions exist"),
        ("SELECT COUNT(*) FROM orders WHERE kind = 'subscription'", "Subscription orders exist"),
        (
            "SELECT COUNT(*) FROM course_enrollments WHERE source = 'membership'",
            "Membership course enrolments exist",
        ),
    ):
        if bind.execute(sa.text(sql)).scalar():
            raise RuntimeError(
                f"{problem}; downgrading would lose membership billing records. Back up the "
                "database and remove them first."
            )
    _foreign_keys(False)
    try:
        with op.batch_alter_table("course_enrollments", schema=None) as batch_op:
            batch_op.drop_constraint(
                batch_op.f("ck_course_enrollments_source_valid"), type_="check"
            )
            batch_op.create_check_constraint(
                batch_op.f("ck_course_enrollments_source_valid"),
                "source IN ('free', 'purchase', 'manual')",
            )
        with op.batch_alter_table("orders", schema=None) as batch_op:
            batch_op.drop_constraint(batch_op.f("ck_orders_kind_valid"), type_="check")
            batch_op.drop_column("kind")
        with op.batch_alter_table("membership_plans", schema=None) as batch_op:
            batch_op.drop_constraint(
                batch_op.f("fk_membership_plans_product_id_products"), type_="foreignkey"
            )
            batch_op.drop_column("product_id")
    finally:
        _foreign_keys(True)

    with op.batch_alter_table("subscription_events", schema=None) as batch_op:
        batch_op.drop_index("ix_subscription_events_subscription")
    op.drop_table("subscription_events")
    op.drop_table("subscription_periods")
    with op.batch_alter_table("customer_subscriptions", schema=None) as batch_op:
        batch_op.drop_index("uq_customer_subscriptions_live")
        batch_op.drop_index("ix_customer_subscriptions_status")
        batch_op.drop_index(batch_op.f("ix_customer_subscriptions_customer_id"))
    op.drop_table("customer_subscriptions")
    op.drop_table("membership_provider_plans")
