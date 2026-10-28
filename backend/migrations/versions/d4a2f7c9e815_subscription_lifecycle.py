"""Membership subscription lifecycle (Batch 10.3: renewals, failed payments, grace,
cancellation at period end, reconciliation).

Revision ID: d4a2f7c9e815
Revises: c9e1a7d5f326
Create Date: 2026-10-28

- ``customer_subscriptions`` gains ``cancel_at_period_end`` (false for existing rows),
  ``cancel_requested_at``, ``past_due_since`` and ``last_reconciled_at``.
- ``subscription_periods.order_id`` becomes unique (one billing period per order), so a
  renewal can never create two periods for the same payment.

No data is rewritten. Downgrade refuses while a cancellation is scheduled or a renewal
period exists (that state could not be represented any more).
"""

import sqlalchemy as sa
from alembic import op

revision = "d4a2f7c9e815"
down_revision = "c9e1a7d5f326"
branch_labels = None
depends_on = None


def _foreign_keys(enabled: bool) -> None:
    """SQLite may rebuild ``customer_subscriptions`` (referenced with ON DELETE CASCADE by
    periods and events); enforcement is paused so the rebuild cannot delete history."""
    if op.get_bind().dialect.name == "sqlite":
        with op.get_context().autocommit_block():
            op.execute(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")


def upgrade():
    _foreign_keys(False)
    try:
        with op.batch_alter_table("customer_subscriptions", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "cancel_at_period_end",
                    sa.Boolean(),
                    server_default=sa.false(),
                    nullable=False,
                )
            )
            batch_op.add_column(
                sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True)
            )
            batch_op.add_column(
                sa.Column("past_due_since", sa.DateTime(timezone=True), nullable=True)
            )
            batch_op.add_column(
                sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True)
            )
    finally:
        _foreign_keys(True)
    op.create_index(
        "uq_subscription_periods_order", "subscription_periods", ["order_id"], unique=True
    )


def downgrade():
    bind = op.get_bind()
    for sql, problem in (
        (
            "SELECT COUNT(*) FROM customer_subscriptions WHERE cancel_at_period_end",
            "Scheduled membership cancellations exist",
        ),
        (
            "SELECT COUNT(*) FROM subscription_periods WHERE sequence > 1",
            "Membership renewal periods exist",
        ),
    ):
        if bind.execute(sa.text(sql)).scalar():
            raise RuntimeError(
                f"{problem}; downgrading would lose membership billing state. Back up the "
                "database and resolve them first."
            )
    op.drop_index("uq_subscription_periods_order", table_name="subscription_periods")
    _foreign_keys(False)
    try:
        with op.batch_alter_table("customer_subscriptions", schema=None) as batch_op:
            batch_op.drop_column("last_reconciled_at")
            batch_op.drop_column("past_due_since")
            batch_op.drop_column("cancel_requested_at")
            batch_op.drop_column("cancel_at_period_end")
    finally:
        _foreign_keys(True)
