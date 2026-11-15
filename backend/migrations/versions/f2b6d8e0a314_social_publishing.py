"""Social publishing: Pinterest / Instagram accounts, posts and Instagram imports.

Revision ID: f2b6d8e0a314
Revises: e1a4c6b8d920
Create Date: 2026-11-15

- New tables ``social_accounts`` (encrypted tokens), ``social_posts`` and
  ``social_imports``. No existing table changes.
- Permissions ``social.view``, ``social.publish`` and ``social.connect`` (Super Admin
  only), granted to the roles in ``GRANTS`` (mirrors ``SOCIAL_GRANTS``).

Downgrade drops the three tables (connected accounts must be reconnected and post history
is lost; imported images stay in the Media Library) and removes the permissions.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2b6d8e0a314"
down_revision = "e1a4c6b8d920"
branch_labels = None
depends_on = None

GROUP = "Social publishing"
NEW_PERMISSIONS = [
    (
        "social.view",
        "View social publishing",
        "See the connected accounts and scheduled and published posts.",
        False,
    ),
    (
        "social.publish",
        "Publish to Pinterest and Instagram",
        "Create, schedule, retry and cancel Pins and Instagram posts, and import your own "
        "Instagram images into the Media Library.",
        False,
    ),
    (
        "social.connect",
        "Connect social accounts",
        "Connect and disconnect the Pinterest and Instagram accounts.",
        True,
    ),
]
GRANTS = {
    "administrator": ["social.view", "social.publish"],
    "marketing_manager": ["social.view", "social.publish"],
    "editor_in_chief": ["social.view"],
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
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _permission_id(bind, key):
    return bind.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.key == key)).scalar()


def _add_permissions(bind) -> None:
    order = bind.execute(sa.select(sa.func.max(PERMISSIONS.c.sort_order))).scalar()
    order = -1 if order is None else order
    for key, label, description, sensitive in NEW_PERMISSIONS:
        if _permission_id(bind, key) is None:
            order += 1
            bind.execute(
                PERMISSIONS.insert().values(
                    key=key,
                    label=label,
                    description=description,
                    group=GROUP,
                    module="social",
                    is_available=True,
                    is_sensitive=sensitive,
                    sort_order=order,
                )
            )
    ids = {key: _permission_id(bind, key) for key, *_ in NEW_PERMISSIONS}
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
        "social_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("username", sa.String(length=200), nullable=True),
        sa.Column("account_type", sa.String(length=50), nullable=True),
        sa.Column("profile_url", sa.String(length=500), nullable=True),
        sa.Column("scopes", _json(), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column("refresh_token_enc", sa.Text(), nullable=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("connected_by_id", sa.Integer(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "platform IN ('pinterest', 'instagram')", name=op.f("ck_social_accounts_platform_valid")
        ),
        sa.CheckConstraint(
            "status IN ('connected', 'expired', 'error')",
            name=op.f("ck_social_accounts_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["connected_by_id"],
            ["users.id"],
            name=op.f("fk_social_accounts_connected_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_social_accounts")),
        sa.UniqueConstraint("platform", name=op.f("uq_social_accounts_platform")),
    )
    op.create_table(
        "social_posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("media_asset_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=100), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("alt_text", sa.String(length=500), nullable=True),
        sa.Column("destination_url", sa.String(length=2048), nullable=True),
        sa.Column("board_id", sa.String(length=100), nullable=True),
        sa.Column("board_name", sa.String(length=200), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_id", sa.String(length=100), nullable=True),
        sa.Column("external_url", sa.String(length=500), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("details", _json(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "platform IN ('pinterest', 'instagram')", name=op.f("ck_social_posts_platform_valid")
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'publishing', 'checking', 'published', 'failed', 'cancelled')",
            name=op.f("ck_social_posts_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name=op.f("fk_social_posts_article_id_articles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_social_posts_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["media_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_social_posts_media_asset_id_media_assets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_social_posts")),
    )
    op.create_index(
        "ix_social_posts_status_scheduled_at", "social_posts", ["status", "scheduled_at"]
    )
    op.create_index(op.f("ix_social_posts_media_asset_id"), "social_posts", ["media_asset_id"])
    op.create_index(op.f("ix_social_posts_article_id"), "social_posts", ["article_id"])
    op.create_table(
        "social_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("media_asset_id", sa.Integer(), nullable=True),
        sa.Column("permalink", sa.String(length=500), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("username", sa.String(length=200), nullable=True),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ownership_confirmed", sa.Boolean(), nullable=False),
        sa.Column("imported_by_id", sa.Integer(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "platform IN ('pinterest', 'instagram')",
            name=op.f("ck_social_imports_platform_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["imported_by_id"],
            ["users.id"],
            name=op.f("fk_social_imports_imported_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["media_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_social_imports_media_asset_id_media_assets"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_social_imports")),
        sa.UniqueConstraint("platform", "external_id", name="uq_social_imports_external"),
    )
    op.create_index(op.f("ix_social_imports_media_asset_id"), "social_imports", ["media_asset_id"])
    _add_permissions(op.get_bind())


def downgrade():
    bind = op.get_bind()
    keys = [key for key, *_ in NEW_PERMISSIONS]
    ids = list(
        bind.execute(sa.select(PERMISSIONS.c.id).where(PERMISSIONS.c.key.in_(keys))).scalars()
    )
    if ids:
        bind.execute(LINKS.delete().where(LINKS.c.permission_id.in_(ids)))
        bind.execute(PERMISSIONS.delete().where(PERMISSIONS.c.id.in_(ids)))
    op.drop_index(op.f("ix_social_imports_media_asset_id"), table_name="social_imports")
    op.drop_table("social_imports")
    op.drop_index(op.f("ix_social_posts_article_id"), table_name="social_posts")
    op.drop_index(op.f("ix_social_posts_media_asset_id"), table_name="social_posts")
    op.drop_index("ix_social_posts_status_scheduled_at", table_name="social_posts")
    op.drop_table("social_posts")
    op.drop_table("social_accounts")
