"""Two-step sign-in (TOTP) for administrators (technical release).

Revision ID: c4e6a8b0d235
Revises: b3d5f7a9c124
Create Date: 2026-11-03

Adds nullable columns to ``users`` only (no data changes): every existing account keeps
signing in exactly as before until it enrols. Downgrade removes the columns, which turns
two-step sign-in off for everyone.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c4e6a8b0d235"
down_revision = "b3d5f7a9c124"
branch_labels = None
depends_on = None

COLUMNS = (
    ("mfa_salt", sa.String(64)),
    ("mfa_pending_salt", sa.String(64)),
    ("mfa_enabled_at", sa.DateTime(timezone=True)),
    ("mfa_last_step", sa.BigInteger()),
    ("mfa_recovery_codes", sa.JSON().with_variant(postgresql.JSONB(), "postgresql")),
)


def upgrade():
    # ALTER TABLE ... ADD COLUMN on every database: no table is rebuilt, no row touched.
    for name, type_ in COLUMNS:
        op.add_column("users", sa.Column(name, type_, nullable=True))


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        # SQLite rebuilds the table to drop columns; rows that reference users (roles,
        # sessions, audit entries) stay intact, so foreign-key checks pause meanwhile.
        op.execute("PRAGMA foreign_keys=OFF")
        with op.batch_alter_table("users") as batch:
            for name, _type in reversed(COLUMNS):
                batch.drop_column(name)
        op.execute("PRAGMA foreign_keys=ON")
        return
    for name, _type in reversed(COLUMNS):
        op.drop_column("users", name)
