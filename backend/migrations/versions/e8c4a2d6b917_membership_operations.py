"""Membership operations (Batch 10.4): complimentary grants and two new permissions.

Revision ID: e8c4a2d6b917
Revises: d4a2f7c9e815
Create Date: 2026-10-28

- New table ``membership_grants`` (complimentary memberships with expiry, reason and the
  granting/revoking staff member).
- Permissions ``memberships.manage_subscriptions`` and ``memberships.view_reports``,
  granted to the roles listed in ``GRANTS`` (mirrors ``BATCH_104_GRANTS``).

No existing data changes. Downgrade refuses while complimentary grants exist.
"""

import sqlalchemy as sa
from alembic import op

revision = "e8c4a2d6b917"
down_revision = "d4a2f7c9e815"
branch_labels = None
depends_on = None

GROUP = "Courses & memberships"
NEW_PERMISSIONS = [
    (
        "memberships.manage_subscriptions",
        "Manage member subscriptions",
        "View subscribers, reconcile with Paystack, cancel, extend grace periods and grant "
        "complimentary memberships. Refunds still need the refund permission.",
    ),
    (
        "memberships.view_reports",
        "View membership reports",
        "Subscriber counts, renewals, churn and verified membership revenue.",
    ),
]
GRANTS = {
    "administrator": ["memberships.manage_subscriptions", "memberships.view_reports"],
    "customer_support": ["memberships.manage_subscriptions"],
    "finance_manager": ["memberships.view_reports"],
    "analyst": ["memberships.view_reports"],
}

PERMISSIONS = sa.table(
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
ROLES = sa.table("roles", sa.column("id", sa.Integer), sa.column("name", sa.String))
LINKS = sa.table(
    "role_permissions", sa.column("role_id", sa.Integer), sa.column("permission_id", sa.Integer)
)


def _permission_id(bind, key):
    return bind.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.key == key)).scalar()


def _add_permissions(bind) -> None:
    order = bind.execute(sa.select(sa.func.max(PERMISSIONS.c.sort_order))).scalar()
    order = -1 if order is None else order
    for key, label, description in NEW_PERMISSIONS:
        if _permission_id(bind, key) is None:
            order += 1
            bind.execute(
                PERMISSIONS.insert().values(
                    key=key,
                    label=label,
                    description=description,
                    group=GROUP,
                    module="memberships",
                    is_available=True,
                    is_sensitive=False,
                    sort_order=order,
                )
            )
    ids = {key: _permission_id(bind, key) for key, _, _ in NEW_PERMISSIONS}
    for role_name, keys in GRANTS.items():
        role_id = bind.execute(sa.select(ROLES.c.id).where(ROLES.c.name == role_name)).scalar()
        if role_id is None:
            continue  # created with these grants by the next RBAC sync
        for key in keys:
            linked = bind.execute(
                sa.select(LINKS.c.role_id).where(
                    LINKS.c.role_id == role_id, LINKS.c.permission_id == ids[key]
                )
            ).scalar()
            if linked is None:
                bind.execute(LINKS.insert().values(role_id=role_id, permission_id=ids[key]))


def upgrade():
    op.create_table(
        "membership_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=24), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("granted_by_id", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", sa.Integer(), nullable=True),
        sa.Column("revoke_reason", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')", name=op.f("ck_membership_grants_status_valid")
        ),
        sa.CheckConstraint(
            "expires_at > starts_at", name=op.f("ck_membership_grants_period_valid")
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_membership_grants_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["membership_plans.id"],
            name=op.f("fk_membership_grants_plan_id_membership_plans"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_id"],
            ["users.id"],
            name=op.f("fk_membership_grants_granted_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_id"],
            ["users.id"],
            name=op.f("fk_membership_grants_revoked_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership_grants")),
        sa.UniqueConstraint(
            "customer_id", "idempotency_key", name=op.f("uq_membership_grants_key")
        ),
        sa.UniqueConstraint("public_id", name=op.f("uq_membership_grants_public_id")),
    )
    op.create_index("ix_membership_grants_customer", "membership_grants", ["customer_id", "status"])
    _add_permissions(op.get_bind())


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM membership_grants")).scalar():
        raise RuntimeError(
            "Complimentary memberships exist; downgrading would delete them. Back up the "
            "database and remove them first."
        )
    keys = [key for key, _, _ in NEW_PERMISSIONS]
    ids = list(
        bind.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.key.in_(keys))).scalars()
    )
    if ids:
        bind.execute(LINKS.delete().where(LINKS.c.permission_id.in_(ids)))
        bind.execute(PERMISSIONS.delete().where(PERMISSIONS.c.id.in_(ids)))
    op.drop_index("ix_membership_grants_customer", table_name="membership_grants")
    op.drop_table("membership_grants")
