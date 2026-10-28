"""First-party website analytics (Batch 11.1).

Revision ID: f2b6d8e4a173
Revises: e8c4a2d6b917
Create Date: 2026-10-28

New tables only: ``analytics_page_views`` (raw, short retention),
``analytics_daily_pages`` and ``analytics_daily_sources`` (daily rollups),
``analytics_rollup_days`` and ``analytics_salts``. No permissions change: reports reuse
``analytics.view``. No existing data is touched.
"""

import sqlalchemy as sa
from alembic import op

revision = "f2b6d8e4a173"
down_revision = "e8c4a2d6b917"
branch_labels = None
depends_on = None


def _dims():
    return [
        sa.Column("utm_source", sa.String(length=100), nullable=False),
        sa.Column("utm_medium", sa.String(length=100), nullable=False),
        sa.Column("utm_campaign", sa.String(length=100), nullable=False),
    ]


def upgrade():
    op.create_table(
        "analytics_page_views",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("path", sa.String(length=300), nullable=False),
        sa.Column("page_type", sa.String(length=20), nullable=False),
        sa.Column("content_type", sa.String(length=20), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("referrer_host", sa.String(length=255), nullable=False),
        *_dims(),
        sa.Column("utm_content", sa.String(length=100), nullable=False),
        sa.Column("utm_term", sa.String(length=100), nullable=False),
        sa.Column("visitor_hash", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analytics_page_views")),
    )
    op.create_index("ix_analytics_page_views_day", "analytics_page_views", ["day", "page_type"])
    op.create_index(
        "ix_analytics_page_views_visitor", "analytics_page_views", ["visitor_hash", "occurred_at"]
    )
    op.create_table(
        "analytics_daily_pages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("path", sa.String(length=300), nullable=False),
        sa.Column("page_type", sa.String(length=20), nullable=False),
        sa.Column("content_type", sa.String(length=20), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=True),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("visitors", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analytics_daily_pages")),
        sa.UniqueConstraint("day", "path", name=op.f("uq_analytics_daily_pages_day_path")),
    )
    op.create_table(
        "analytics_daily_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("referrer_host", sa.String(length=255), nullable=False),
        *_dims(),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("visitors", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analytics_daily_sources")),
        sa.UniqueConstraint(
            "day",
            "source",
            "referrer_host",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            name=op.f("uq_analytics_daily_sources_dims"),
        ),
    )
    op.create_table(
        "analytics_rollup_days",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("visitors", sa.Integer(), nullable=False),
        sa.Column("rolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_analytics_rollup_days")),
    )
    op.create_table(
        "analytics_salts",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("salt", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_analytics_salts")),
    )


def downgrade():
    # Analytics data is derived and non-essential; dropping it loses only statistics.
    op.drop_table("analytics_salts")
    op.drop_table("analytics_rollup_days")
    op.drop_table("analytics_daily_sources")
    op.drop_table("analytics_daily_pages")
    op.drop_index("ix_analytics_page_views_visitor", table_name="analytics_page_views")
    op.drop_index("ix_analytics_page_views_day", table_name="analytics_page_views")
    op.drop_table("analytics_page_views")
