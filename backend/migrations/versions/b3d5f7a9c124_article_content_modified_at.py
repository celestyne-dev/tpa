"""Article "last updated" date for material changes (technical release).

Revision ID: b3d5f7a9c124
Revises: a7c2e9f4b318
Create Date: 2026-11-03

Adds one nullable column, ``articles.content_modified_at``. It is set only when an
editor publishes a change marked as a material update; existing rows keep NULL (no
backfill), so no article, slug, canonical or publication date changes.
"""

import sqlalchemy as sa
from alembic import op

revision = "b3d5f7a9c124"
down_revision = "a7c2e9f4b318"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("articles") as batch:
        batch.add_column(sa.Column("content_modified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("articles") as batch:
        batch.drop_column("content_modified_at")
