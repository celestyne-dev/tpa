"""VPS storage, media categories and premium resources.

Revision ID: c3e8d1f20b47
Revises: a136d95dd67c
Create Date: 2026-10-27

Non-destructive:
- media_assets.category ("general" for every existing image).
- products: download_limit, access_days (both empty: store-wide limit, lifetime access)
  and membership_eligible (false). Their positive-value check constraints are added on
  PostgreSQL only; on SQLite "products" is never rebuilt (rebuilding it inside the
  migration would cascade through its many references) and the service validates.
- product_related: ordered related resources.
- entitlements.expires_at (empty: lifetime access, as before) and two reserved
  entitlement sources, "membership" and "course". On SQLite the entitlements table is
  rebuilt with foreign-key enforcement paused outside the transaction, then checked.
- permission storage.view, granted to the Administrator and Website Manager templates.
"""

import sqlalchemy as sa
from alembic import op

revision = "c3e8d1f20b47"
down_revision = "a136d95dd67c"
branch_labels = None
depends_on = None

OLD_SOURCES = "source IN ('purchase', 'bundle', 'free', 'manual')"
NEW_SOURCES = "source IN ('purchase', 'bundle', 'free', 'manual', 'membership', 'course')"
STORAGE_VIEW = {
    "key": "storage.view",
    "label": "View storage health",
    "description": "Disk space, folder permissions, missing files, upload errors and backups.",
    "group": "Users, roles & audit",
    "module": "storage",
    "is_available": True,
    "is_sensitive": False,
}
STORAGE_GRANTS = ("administrator", "website_manager")


def _sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _replace_entitlement_sources(condition: str) -> None:
    conn = op.get_bind()
    sqlite = _sqlite()
    if sqlite:
        with op.get_context().autocommit_block():
            op.execute("PRAGMA foreign_keys=OFF")
    try:
        with op.batch_alter_table("entitlements", schema=None) as batch_op:
            batch_op.drop_constraint(op.f("ck_entitlements_source_valid"), type_="check")
            batch_op.create_check_constraint(op.f("ck_entitlements_source_valid"), condition)
        if sqlite:
            broken = conn.execute(sa.text("PRAGMA foreign_key_check")).fetchall()
            if broken:
                raise RuntimeError(f"Foreign keys broken by the table rebuild: {broken[:5]}")
    finally:
        if sqlite:
            with op.get_context().autocommit_block():
                op.execute("PRAGMA foreign_keys=ON")


def _permissions():
    return sa.table(
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


def upgrade():
    # Plain ALTER TABLE ... ADD COLUMN (never a table rebuild, on SQLite too).
    op.add_column(
        "media_assets",
        sa.Column("category", sa.String(length=40), server_default="general", nullable=False),
    )
    op.add_column("products", sa.Column("download_limit", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("access_days", sa.Integer(), nullable=True))
    op.add_column(
        "products",
        sa.Column("membership_eligible", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    if not _sqlite():
        op.create_check_constraint(
            op.f("ck_products_download_limit_positive"),
            "products",
            "download_limit IS NULL OR download_limit > 0",
        )
        op.create_check_constraint(
            op.f("ck_products_access_days_positive"),
            "products",
            "access_days IS NULL OR access_days > 0",
        )

    op.create_table(
        "product_related",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("related_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("product_id <> related_id", name=op.f("ck_product_related_not_self")),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_related_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["related_id"],
            ["products.id"],
            name=op.f("fk_product_related_related_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("product_id", "related_id", name=op.f("pk_product_related")),
    )
    op.create_index("ix_product_related_related_id", "product_related", ["related_id"])

    op.add_column(
        "entitlements", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    _replace_entitlement_sources(NEW_SOURCES)

    bind = op.get_bind()
    permissions = _permissions()
    exists = bind.execute(
        sa.select(permissions.c.id).where(permissions.c.key == STORAGE_VIEW["key"])
    ).scalar()
    if exists is None:
        order = bind.execute(sa.select(sa.func.max(permissions.c.sort_order))).scalar()
        bind.execute(permissions.insert().values(sort_order=(order or 0) + 1, **STORAGE_VIEW))
    perm_id = bind.execute(
        sa.select(permissions.c.id).where(permissions.c.key == STORAGE_VIEW["key"])
    ).scalar()
    roles = sa.table("roles", sa.column("id", sa.Integer), sa.column("name", sa.String))
    links = sa.table(
        "role_permissions", sa.column("role_id", sa.Integer), sa.column("permission_id", sa.Integer)
    )
    for role_id in bind.execute(
        sa.select(roles.c.id).where(roles.c.name.in_(STORAGE_GRANTS))
    ).scalars():
        linked = bind.execute(
            sa.select(links.c.role_id).where(
                links.c.role_id == role_id, links.c.permission_id == perm_id
            )
        ).scalar()
        if linked is None:
            bind.execute(links.insert().values(role_id=role_id, permission_id=perm_id))


def downgrade():
    bind = op.get_bind()
    reserved = bind.execute(
        sa.text("SELECT COUNT(*) FROM entitlements WHERE source IN ('membership', 'course')")
    ).scalar()
    if reserved:
        raise RuntimeError(
            "Membership or course entitlements exist; downgrading would make them invalid."
        )
    permissions = _permissions()
    perm_id = bind.execute(
        sa.select(permissions.c.id).where(permissions.c.key == STORAGE_VIEW["key"])
    ).scalar()
    if perm_id is not None:
        bind.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id = :p"), {"p": perm_id}
        )
        bind.execute(permissions.delete().where(permissions.c.id == perm_id))

    _replace_entitlement_sources(OLD_SOURCES)
    op.drop_column("entitlements", "expires_at")

    op.drop_index("ix_product_related_related_id", table_name="product_related")
    op.drop_table("product_related")

    if not _sqlite():
        op.drop_constraint(op.f("ck_products_access_days_positive"), "products", type_="check")
        op.drop_constraint(op.f("ck_products_download_limit_positive"), "products", type_="check")
    # Plain columns: dropped in place (no table rebuild) on SQLite 3.35+ and PostgreSQL.
    op.drop_column("products", "membership_eligible")
    op.drop_column("products", "access_days")
    op.drop_column("products", "download_limit")
    op.drop_column("media_assets", "category")
