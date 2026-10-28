"""Membership plans, immutable plan prices and included products (Batch 10.1).

Revision ID: b8d0f6c4e215
Revises: a7c9e5b3d104
Create Date: 2026-10-28

Additive only: three new tables. No existing table is altered, so purchases,
entitlements, courses and enrolments are untouched. ``memberships.manage`` (present
since Batch 02 as an unavailable placeholder) becomes available with its new label, and
``memberships.view`` / ``memberships.publish`` are appended, with the grants the code
defines (a later RBAC sync changes nothing). No billing, subscriptions or entitlement
grants exist yet.

Downgrade refuses while any membership plan exists.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text  # noqa: F401  (used by rendered JSONB types)
from sqlalchemy.dialects import postgresql

revision = "b8d0f6c4e215"
down_revision = "a7c9e5b3d104"
branch_labels = None
depends_on = None

GROUP = "Courses & memberships"
MANAGE = (
    "memberships.manage",
    "Manage membership plans",
    "Plan content, benefits, prices and the courses and resources included.",
)
OLD_MANAGE = ("Manage memberships", "")
NEW_PERMISSIONS = [
    ("memberships.view", "View membership plans", ""),
    (
        "memberships.publish",
        "Publish membership plans",
        "Publish, unpublish and archive plans shown on the membership page.",
    ),
]
_ALL = ["memberships.view", "memberships.manage", "memberships.publish"]
GRANTS = {
    "administrator": _ALL,
    "editor_in_chief": _ALL,
    "product_manager": ["memberships.view", "memberships.manage"],
    "marketing_manager": ["memberships.view"],
    "customer_support": ["memberships.view"],
    "finance_manager": ["memberships.view"],
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


def _json():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


def _permission_id(bind, key):
    return bind.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.key == key)).scalar()


def _add_permissions(bind) -> None:
    key, label, description = MANAGE
    manage_id = _permission_id(bind, key)
    if manage_id is None:  # databases created before the placeholder existed
        order = bind.execute(sa.select(sa.func.max(PERMISSIONS.c.sort_order))).scalar() or 0
        bind.execute(
            PERMISSIONS.insert().values(
                key=key,
                label=label,
                description=description,
                group=GROUP,
                module="memberships",
                is_available=True,
                is_sensitive=False,
                sort_order=order + 1,
            )
        )
    else:
        bind.execute(
            PERMISSIONS.update()
            .where(PERMISSIONS.c.id == manage_id)
            .values(label=label, description=description, is_available=True)
        )
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
    ids = {key: _permission_id(bind, key) for key in _ALL}
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
        "membership_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=24), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("tagline", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("benefits", _json(), nullable=False),
        sa.Column("tier_rank", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name=op.f("ck_membership_plans_status_valid"),
        ),
        sa.CheckConstraint("tier_rank > 0", name=op.f("ck_membership_plans_tier_rank_positive")),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_membership_plans_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_membership_plans_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership_plans")),
        sa.UniqueConstraint("public_id", name=op.f("uq_membership_plans_public_id")),
        sa.UniqueConstraint("slug", name=op.f("uq_membership_plans_slug")),
        sa.UniqueConstraint("tier_rank", name=op.f("uq_membership_plans_tier_rank")),
    )
    op.create_table(
        "membership_plan_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=24), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("interval", sa.String(length=10), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("shown_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "interval IN ('month', 'year')", name=op.f("ck_membership_plan_prices_interval_valid")
        ),
        sa.CheckConstraint(
            "status IN ('active', 'retired')", name=op.f("ck_membership_plan_prices_status_valid")
        ),
        sa.CheckConstraint(
            "amount_minor > 0", name=op.f("ck_membership_plan_prices_amount_positive")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_membership_plan_prices_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["membership_plans.id"],
            name=op.f("fk_membership_plan_prices_plan_id_membership_plans"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership_plan_prices")),
        sa.UniqueConstraint("public_id", name=op.f("uq_membership_plan_prices_public_id")),
    )
    with op.batch_alter_table("membership_plan_prices", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_membership_plan_prices_plan_id"), ["plan_id"], unique=False
        )
        batch_op.create_index(
            "uq_membership_plan_prices_active",
            ["plan_id", "interval", "currency"],
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
            sqlite_where=sa.text("status = 'active'"),
        )
    op.create_table(
        "membership_plan_access",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("added_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["added_by_id"],
            ["users.id"],
            name=op.f("fk_membership_plan_access_added_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["membership_plans.id"],
            name=op.f("fk_membership_plan_access_plan_id_membership_plans"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_membership_plan_access_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership_plan_access")),
        sa.UniqueConstraint(
            "plan_id", "product_id", name=op.f("uq_membership_plan_access_product")
        ),
    )
    with op.batch_alter_table("membership_plan_access", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_membership_plan_access_product_id"), ["product_id"], unique=False
        )
    _add_permissions(op.get_bind())


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM membership_plans")).scalar():
        raise RuntimeError(
            "Membership plans exist; downgrading would delete them with their prices. "
            "Back up the database and remove the plans first."
        )
    keys = [key for key, _, _ in NEW_PERMISSIONS]
    ids = list(
        bind.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.key.in_(keys))).scalars()
    )
    if ids:
        bind.execute(LINKS.delete().where(LINKS.c.permission_id.in_(ids)))
        bind.execute(PERMISSIONS.delete().where(PERMISSIONS.c.id.in_(ids)))
    manage_id = _permission_id(bind, MANAGE[0])
    if manage_id is not None:
        bind.execute(LINKS.delete().where(LINKS.c.permission_id == manage_id))
        bind.execute(
            PERMISSIONS.update()
            .where(PERMISSIONS.c.id == manage_id)
            .values(label=OLD_MANAGE[0], description=OLD_MANAGE[1], is_available=False)
        )

    with op.batch_alter_table("membership_plan_access", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_membership_plan_access_product_id"))
    op.drop_table("membership_plan_access")
    with op.batch_alter_table("membership_plan_prices", schema=None) as batch_op:
        batch_op.drop_index("uq_membership_plan_prices_active")
        batch_op.drop_index(batch_op.f("ix_membership_plan_prices_plan_id"))
    op.drop_table("membership_plan_prices")
    op.drop_table("membership_plans")
