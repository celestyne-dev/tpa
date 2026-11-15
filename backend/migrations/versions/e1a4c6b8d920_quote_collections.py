"""Quote collections: ``articles.content_type``.

Revision ID: e1a4c6b8d920
Revises: d7f1a3c5e908
Create Date: 2026-11-15

Adds one column with a server default, so every existing row becomes an ``article``
(no data rewrite, no table rebuild). Quote collections are stored as ``quotes`` rows and
reuse the article editor, revisions, scheduling and SEO fields. Downgrade drops the
column; run it only after deleting any quote collections, which would otherwise be
listed as articles.
"""

import sqlalchemy as sa
from alembic import op

revision = "e1a4c6b8d920"
down_revision = "d7f1a3c5e908"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("articles", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "content_type", sa.String(length=20), server_default="article", nullable=False
            )
        )
    op.create_index("ix_articles_content_type", "articles", ["content_type"], unique=False)


def downgrade():
    op.drop_index("ix_articles_content_type", table_name="articles")
    with op.batch_alter_table("articles", schema=None) as batch_op:
        batch_op.drop_column("content_type")
