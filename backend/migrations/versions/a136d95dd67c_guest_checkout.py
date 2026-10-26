"""Guest checkout: guest buyer records, guest access links and guest download grants.

Revision ID: a136d95dd67c
Revises: 4a65b8174c82
Create Date: 2026-10-26

Non-destructive:
- customers.status and customer_tokens.purpose accept one more value each
  ("guest", "guest_access"); existing rows are unchanged.
- orders gain is_guest (false for every existing order) and guest_token_hash (null).
- download_grants gain guest (false for every existing grant).
On SQLite the two constraint changes rebuild those tables (batch mode), copying every
row. Orders, sessions and tokens reference customers, and inside a transaction SQLite
can't pause foreign-key enforcement, so dropping the old table would fail or cascade.
Enforcement is therefore switched off outside the transaction for the rebuild and the
result is checked with ``PRAGMA foreign_key_check``. On PostgreSQL they are plain ALTERs.
"""

import sqlalchemy as sa
from alembic import op

revision = "a136d95dd67c"
down_revision = "4a65b8174c82"
branch_labels = None
depends_on = None

OLD_STATUSES = "status IN ('active', 'disabled', 'deleted')"
NEW_STATUSES = "status IN ('active', 'disabled', 'deleted', 'guest')"
OLD_PURPOSES = "purpose IN ('verify_email', 'password_reset')"
NEW_PURPOSES = "purpose IN ('verify_email', 'password_reset', 'guest_access')"


def _replace_check(table: str, name: str, condition: str) -> None:
    with op.batch_alter_table(table, schema=None) as batch_op:
        batch_op.drop_constraint(op.f(name), type_="check")
        batch_op.create_check_constraint(op.f(name), condition)


def _replace_checks(statuses: str, purposes: str) -> None:
    conn = op.get_bind()
    sqlite = conn.dialect.name == "sqlite"
    if sqlite:
        with op.get_context().autocommit_block():
            op.execute("PRAGMA foreign_keys=OFF")
    try:
        _replace_check("customers", "ck_customers_status_valid", statuses)
        _replace_check("customer_tokens", "ck_customer_tokens_purpose_valid", purposes)
        if sqlite:
            broken = conn.execute(sa.text("PRAGMA foreign_key_check")).fetchall()
            if broken:
                raise RuntimeError(f"Foreign keys broken by the table rebuild: {broken[:5]}")
    finally:
        if sqlite:
            with op.get_context().autocommit_block():
                op.execute("PRAGMA foreign_keys=ON")


def upgrade():
    _replace_checks(NEW_STATUSES, NEW_PURPOSES)
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_guest", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(sa.Column("guest_token_hash", sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint(
            batch_op.f("uq_orders_guest_token_hash"), ["guest_token_hash"]
        )
    with op.batch_alter_table("download_grants", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("guest", sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade():
    conn = op.get_bind()
    if conn.execute(sa.text("SELECT COUNT(*) FROM customers WHERE status = 'guest'")).scalar():
        raise RuntimeError(
            "Guest buyer records exist (orders and receipts depend on them). Downgrading "
            "would break those records; keep this revision or migrate the data first."
        )
    op.execute("DELETE FROM customer_tokens WHERE purpose = 'guest_access'")
    with op.batch_alter_table("download_grants", schema=None) as batch_op:
        batch_op.drop_column("guest")
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_orders_guest_token_hash"), type_="unique")
        batch_op.drop_column("guest_token_hash")
        batch_op.drop_column("is_guest")
    _replace_checks(OLD_STATUSES, OLD_PURPOSES)
