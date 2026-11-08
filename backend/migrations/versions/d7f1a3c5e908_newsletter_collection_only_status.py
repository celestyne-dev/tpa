"""Newsletter collection-only sign-ups: the ``collected`` subscriber status.

Revision ID: d7f1a3c5e908
Revises: c4e6a8b0d235
Create Date: 2026-11-08

Widens the subscribers status check to allow ``collected``: someone who signed up on the
website with explicit consent while the newsletter collects addresses only (no
confirmation email is sent, so the address is not verified). No data changes on upgrade.

Downgrade: ``collected`` rows become ``quarantined`` (the older status for unverified
contacts that are never mailed); their consent evidence is kept.
"""

from alembic import op

revision = "d7f1a3c5e908"
down_revision = "c4e6a8b0d235"
branch_labels = None
depends_on = None

OLD = "('pending', 'subscribed', 'unsubscribed', 'bounced', 'complained', 'quarantined')"
NEW = (
    "('pending', 'subscribed', 'unsubscribed', 'bounced', 'complained', 'quarantined', "
    "'collected')"
)


def _foreign_keys(enabled: bool) -> None:
    """SQLite rebuilds ``subscribers`` (referenced by events, tag links, messages and
    enrolments) to change the check; dropping the old table must not cascade."""
    if op.get_bind().dialect.name == "sqlite":
        with op.get_context().autocommit_block():
            op.execute(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")


def _status_check(values: str) -> None:
    _foreign_keys(False)
    try:
        with op.batch_alter_table("subscribers", schema=None) as batch_op:
            batch_op.drop_constraint(batch_op.f("ck_subscribers_status_valid"), type_="check")
            batch_op.create_check_constraint(
                batch_op.f("ck_subscribers_status_valid"), f"status IN {values}"
            )
    finally:
        _foreign_keys(True)


def upgrade():
    _status_check(NEW)


def downgrade():
    op.execute("UPDATE subscribers SET status = 'quarantined' WHERE status = 'collected'")
    _status_check(OLD)
