"""Indexes for report date-range filters (Batch 12.2).

Revision ID: a7c2e9f4b318
Revises: f2b6d8e4a173
Create Date: 2026-10-28

Indexes only; no data or permissions change. They support the finance and analytics
reports' range filters on ``payment_transactions`` (kind, created_at), ``orders``
(paid_at) and ``subscribers`` (created_at, confirmed_at, unsubscribed_at).
"""

from alembic import op

revision = "a7c2e9f4b318"
down_revision = "f2b6d8e4a173"
branch_labels = None
depends_on = None

INDEXES = [
    ("ix_payment_transactions_kind_created", "payment_transactions", ["kind", "created_at"]),
    ("ix_orders_paid_at", "orders", ["paid_at"]),
    ("ix_subscribers_created_at", "subscribers", ["created_at"]),
    ("ix_subscribers_confirmed_at", "subscribers", ["confirmed_at"]),
    ("ix_subscribers_unsubscribed_at", "subscribers", ["unsubscribed_at"]),
]


def upgrade():
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade():
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
