"""Media library, article revisions, redirects and publishing jobs.

Incremental and non-destructive:
- new tables: media_variants, article_revisions, redirects, publish_jobs;
- new column authors.is_person (Person structured data only for real people);
- new columns on media_assets (public id, title, caption, credit, status,
  checksum, retained original, focal point, version ...) and articles
  (social title/description, lock_version, pending changes), added with
  ALTER TABLE ... ADD COLUMN only - no table is dropped, copied or recreated;
- permissions: the catalogue is brought up to date (media upload/edit/
  replace/delete, revisions, previews, SEO audit, redirects, publishing) and
  the matching permissions are granted to the built-in roles and the role
  templates that still exist. Custom roles are not changed.

Existing users, roles, assignments, invitations, articles, media records and
settings are preserved. Built-in /images/... media keep working unchanged.

Downgrade removes the new tables, columns and permissions (uploaded media
files on disk are left in place).

Revision ID: a817c9636960
Revises: 7cf88d33a308
Create Date: 2026-10-22 15:29:52.074604

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text  # noqa: F401  (used by rendered JSONB types)
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a817c9636960'
down_revision = '7cf88d33a308'
branch_labels = None
depends_on = None

# Frozen snapshot of app/auth/permissions.py at this revision.
# (key, label, description, group, module, available, sensitive)
PERMISSIONS = [('dashboard.view', 'View dashboard', '', 'Dashboard & analytics', 'dashboard', True, False),
 ('analytics.view',
  'View content analytics',
  '',
  'Dashboard & analytics',
  'analytics',
  True,
  False),
 ('articles.view',
  'View all articles',
  "See every article, including other people's drafts.",
  'Articles',
  'articles',
  True,
  False),
 ('articles.create', 'Create articles', '', 'Articles', 'articles', True, False),
 ('articles.edit_own',
  'Edit own drafts',
  'Edit articles you created while they are drafts.',
  'Articles',
  'articles',
  True,
  False),
 ('articles.edit_any', 'Edit any article', '', 'Articles', 'articles', True, False),
 ('articles.submit_review', 'Submit for review', '', 'Articles', 'articles', True, False),
 ('articles.approve', 'Approve articles', '', 'Articles', 'articles', True, False),
 ('articles.publish', 'Publish and schedule', '', 'Articles', 'articles', True, False),
 ('articles.unpublish', 'Unpublish', '', 'Articles', 'articles', True, False),
 ('articles.archive', 'Archive and restore', '', 'Articles', 'articles', True, False),
 ('articles.delete',
  'Delete unpublished drafts',
  'Permanently delete drafts that were never published.',
  'Articles',
  'articles',
  True,
  False),
 ('articles.view_revisions',
  'View revision history',
  'For articles you can open.',
  'Articles',
  'articles',
  True,
  False),
 ('articles.restore_revisions',
  'Restore revisions',
  'Only on articles you are allowed to edit.',
  'Articles',
  'articles',
  True,
  False),
 ('articles.preview',
  'Preview drafts',
  'Private, non-indexed preview of articles you can open.',
  'Articles',
  'articles',
  True,
  False),
 ('topics.manage', 'Manage topics', '', 'Topics, tags & authors', 'taxonomy', True, False),
 ('tags.manage', 'Manage tags', '', 'Topics, tags & authors', 'taxonomy', True, False),
 ('authors.manage', 'Manage authors', '', 'Topics, tags & authors', 'taxonomy', True, False),
 ('media.view', 'View media library', '', 'Media library', 'media', True, False),
 ('media.upload',
  'Upload media',
  'Upload images; they are validated and optimised automatically.',
  'Media library',
  'media',
  True,
  False),
 ('media.edit',
  'Edit media details',
  'Alt text, title, caption, credit and focal point.',
  'Media library',
  'media',
  True,
  False),
 ('media.replace', 'Replace media files', '', 'Media library', 'media', True, False),
 ('media.delete',
  'Archive and delete media',
  'Media still used by content can be archived but never deleted.',
  'Media library',
  'media',
  True,
  False),
 ('pages.view', 'View pages and sections', '', 'Pages & homepage', 'pages', True, False),
 ('pages.edit', 'Edit pages and homepage sections', '', 'Pages & homepage', 'pages', True, False),
 ('navigation.manage', 'Manage navigation menus', '', 'Navigation', 'navigation', True, False),
 ('settings.manage',
  'Manage site settings',
  'Branding, contact details, social links, footer and newsletter flag.',
  'Site settings',
  'settings',
  True,
  False),
 ('settings.security', 'Manage security settings', '', 'Site settings', 'settings', False, True),
 ('seo.manage',
  'Manage SEO settings',
  'Default titles, descriptions and sharing image; article canonical URLs, indexing and '
  'post-publication slug changes.',
  'SEO',
  'seo',
  True,
  False),
 ('seo.view',
  'View SEO audit',
  'The SEO dashboard and per-article checks.',
  'SEO',
  'seo',
  True,
  False),
 ('redirects.manage', 'Manage redirects', '', 'SEO', 'redirects', True, False),
 ('publishing.view',
  'View publishing jobs',
  'Static site build status and history.',
  'Publishing',
  'publishing',
  True,
  False),
 ('publishing.manage',
  'Run and retry publishing jobs',
  '',
  'Publishing',
  'publishing',
  True,
  False),
 ('products.view', 'View digital products', '', 'Digital products', 'products', False, False),
 ('products.manage',
  'Manage products and pricing',
  '',
  'Digital products',
  'products',
  False,
  False),
 ('orders.view', 'View orders', '', 'Orders & refunds', 'orders', False, False),
 ('orders.manage', 'Manage orders', '', 'Orders & refunds', 'orders', False, False),
 ('refunds.issue', 'Issue refunds', '', 'Orders & refunds', 'orders', False, False),
 ('payments.configure', 'Configure payments', '', 'Orders & refunds', 'payments', False, True),
 ('customers.view', 'View customers', '', 'Customers', 'customers', False, False),
 ('customers.manage', 'Manage customers', '', 'Customers', 'customers', False, False),
 ('partnerships.view', 'View partnerships', '', 'Partnerships', 'partnerships', False, False),
 ('partnerships.manage', 'Manage partnerships', '', 'Partnerships', 'partnerships', False, False),
 ('advertising.view', 'View advertising', '', 'Advertising', 'advertising', False, False),
 ('advertising.manage', 'Manage advertising', '', 'Advertising', 'advertising', False, False),
 ('affiliates.view',
  'View affiliate campaigns',
  '',
  'Affiliate campaigns',
  'affiliates',
  False,
  False),
 ('affiliates.manage',
  'Manage affiliate campaigns',
  '',
  'Affiliate campaigns',
  'affiliates',
  False,
  False),
 ('newsletters.manage',
  'Manage newsletters',
  '',
  'Newsletters & subscribers',
  'newsletters',
  False,
  False),
 ('subscribers.view',
  'View subscribers',
  '',
  'Newsletters & subscribers',
  'newsletters',
  False,
  False),
 ('subscribers.export',
  'Export subscribers',
  '',
  'Newsletters & subscribers',
  'newsletters',
  False,
  False),
 ('courses.manage', 'Manage courses', '', 'Courses & memberships', 'courses', False, False),
 ('memberships.manage',
  'Manage memberships',
  '',
  'Courses & memberships',
  'memberships',
  False,
  False),
 ('finance.view', 'View finance reports', '', 'Finance', 'finance', False, False),
 ('finance.manage', 'Manage finance', '', 'Finance', 'finance', False, False),
 ('users.view', 'View administrators', '', 'Users, roles & audit', 'users', True, False),
 ('users.manage',
  'Manage administrator accounts',
  'Disable, reactivate and reset passwords of administrators with equal or fewer permissions.',
  'Users, roles & audit',
  'users',
  True,
  False),
 ('roles.manage', 'Manage roles and permissions', '', 'Users, roles & audit', 'roles', True, True),
 ('roles.assign',
  'Assign roles and invite administrators',
  '',
  'Users, roles & audit',
  'roles',
  True,
  True),
 ('audit.view', 'View audit log', '', 'Users, roles & audit', 'audit', True, False)]

GRANTS = {'administrator': ['articles.preview',
                   'articles.restore_revisions',
                   'articles.view_revisions',
                   'media.delete',
                   'media.edit',
                   'media.replace',
                   'media.upload',
                   'media.view',
                   'publishing.manage',
                   'publishing.view',
                   'redirects.manage',
                   'seo.view'],
 'analyst': ['articles.preview', 'publishing.view', 'seo.view'],
 'content_editor': ['articles.preview',
                    'articles.restore_revisions',
                    'articles.view_revisions',
                    'media.edit',
                    'media.upload'],
 'content_writer': ['articles.preview',
                    'articles.restore_revisions',
                    'articles.view_revisions',
                    'media.upload'],
 'editor': ['articles.preview',
            'articles.restore_revisions',
            'articles.view_revisions',
            'media.edit',
            'media.replace',
            'media.upload',
            'publishing.view',
            'seo.view'],
 'editor_in_chief': ['articles.preview',
                     'articles.restore_revisions',
                     'articles.view_revisions',
                     'media.delete',
                     'media.edit',
                     'media.replace',
                     'media.upload',
                     'media.view',
                     'publishing.manage',
                     'publishing.view',
                     'seo.view'],
 'marketing_manager': ['articles.preview', 'seo.view'],
 'moderator': ['articles.preview', 'articles.view_revisions', 'publishing.view'],
 'seo_manager': ['articles.preview',
                 'articles.view_revisions',
                 'media.edit',
                 'media.view',
                 'redirects.manage',
                 'seo.view'],
 'website_manager': ['media.edit', 'media.replace', 'media.upload', 'publishing.view', 'seo.view']}

NEW_KEYS = (
    "media.edit",
    "media.replace",
    "articles.view_revisions",
    "articles.restore_revisions",
    "articles.preview",
    "seo.view",
    "redirects.manage",
    "publishing.view",
    "publishing.manage",
)
MEDIA_STATUS_CHECK = "status IN ('active', 'archived')"
JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')


def _is_sqlite():
    return op.get_bind().dialect.name == "sqlite"


def _add_columns():
    if _is_sqlite():
        # ADD COLUMN with inline constraints keeps the existing tables in place.
        for statement in (
            "ALTER TABLE articles ADD COLUMN social_title VARCHAR(200)",
            "ALTER TABLE articles ADD COLUMN social_description VARCHAR(320)",
            "ALTER TABLE articles ADD COLUMN lock_version INTEGER DEFAULT '1' NOT NULL",
            "ALTER TABLE articles ADD COLUMN pending_changes JSON",
            "ALTER TABLE articles ADD COLUMN pending_updated_at DATETIME",
            "ALTER TABLE articles ADD COLUMN pending_by_id INTEGER "
            "CONSTRAINT fk_articles_pending_by_id_users REFERENCES users (id) ON DELETE SET NULL",
            "ALTER TABLE authors ADD COLUMN is_person BOOLEAN DEFAULT '0' NOT NULL",
            "ALTER TABLE media_assets ADD COLUMN public_id VARCHAR(32)",
            "ALTER TABLE media_assets ADD COLUMN title VARCHAR(200) DEFAULT '' NOT NULL",
            "ALTER TABLE media_assets ADD COLUMN caption VARCHAR(500) DEFAULT '' NOT NULL",
            "ALTER TABLE media_assets ADD COLUMN credit VARCHAR(200) DEFAULT '' NOT NULL",
            "ALTER TABLE media_assets ADD COLUMN source_url VARCHAR(500)",
            "ALTER TABLE media_assets ADD COLUMN status VARCHAR(20) DEFAULT 'active' NOT NULL "
            f"CONSTRAINT ck_media_assets_status_valid CHECK ({MEDIA_STATUS_CHECK})",
            "ALTER TABLE media_assets ADD COLUMN checksum VARCHAR(64)",
            "ALTER TABLE media_assets ADD COLUMN original_filename VARCHAR(255)",
            "ALTER TABLE media_assets ADD COLUMN original_key VARCHAR(500)",
            "ALTER TABLE media_assets ADD COLUMN original_mime VARCHAR(100)",
            "ALTER TABLE media_assets ADD COLUMN original_size BIGINT",
            "ALTER TABLE media_assets ADD COLUMN focal_x FLOAT DEFAULT '0.5' NOT NULL",
            "ALTER TABLE media_assets ADD COLUMN focal_y FLOAT DEFAULT '0.5' NOT NULL",
            "ALTER TABLE media_assets ADD COLUMN version INTEGER DEFAULT '1' NOT NULL",
            "ALTER TABLE media_assets ADD COLUMN has_alpha BOOLEAN DEFAULT '0' NOT NULL",
            "ALTER TABLE media_assets ADD COLUMN dominant_color VARCHAR(7)",
            "ALTER TABLE media_assets ADD COLUMN updated_at DATETIME",
            "ALTER TABLE media_assets ADD COLUMN archived_at DATETIME",
        ):
            op.execute(statement)
    else:
        op.add_column('articles', sa.Column('social_title', sa.String(length=200), nullable=True))
        op.add_column('articles', sa.Column('social_description', sa.String(length=320), nullable=True))
        op.add_column('articles', sa.Column('lock_version', sa.Integer(), server_default='1', nullable=False))
        op.add_column('articles', sa.Column('pending_changes', JSON, nullable=True))
        op.add_column('articles', sa.Column('pending_updated_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column('articles', sa.Column('pending_by_id', sa.Integer(), nullable=True))
        op.create_foreign_key(op.f('fk_articles_pending_by_id_users'), 'articles', 'users', ['pending_by_id'], ['id'], ondelete='SET NULL')
        op.add_column('authors', sa.Column('is_person', sa.Boolean(), server_default='0', nullable=False))
        op.add_column('media_assets', sa.Column('public_id', sa.String(length=32), nullable=True))
        op.add_column('media_assets', sa.Column('title', sa.String(length=200), server_default='', nullable=False))
        op.add_column('media_assets', sa.Column('caption', sa.String(length=500), server_default='', nullable=False))
        op.add_column('media_assets', sa.Column('credit', sa.String(length=200), server_default='', nullable=False))
        op.add_column('media_assets', sa.Column('source_url', sa.String(length=500), nullable=True))
        op.add_column('media_assets', sa.Column('status', sa.String(length=20), server_default='active', nullable=False))
        op.add_column('media_assets', sa.Column('checksum', sa.String(length=64), nullable=True))
        op.add_column('media_assets', sa.Column('original_filename', sa.String(length=255), nullable=True))
        op.add_column('media_assets', sa.Column('original_key', sa.String(length=500), nullable=True))
        op.add_column('media_assets', sa.Column('original_mime', sa.String(length=100), nullable=True))
        op.add_column('media_assets', sa.Column('original_size', sa.BigInteger(), nullable=True))
        op.add_column('media_assets', sa.Column('focal_x', sa.Float(), server_default='0.5', nullable=False))
        op.add_column('media_assets', sa.Column('focal_y', sa.Float(), server_default='0.5', nullable=False))
        op.add_column('media_assets', sa.Column('version', sa.Integer(), server_default='1', nullable=False))
        op.add_column('media_assets', sa.Column('has_alpha', sa.Boolean(), server_default='0', nullable=False))
        op.add_column('media_assets', sa.Column('dominant_color', sa.String(length=7), nullable=True))
        op.add_column('media_assets', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column('media_assets', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
        op.create_check_constraint(op.f('ck_media_assets_status_valid'), 'media_assets', MEDIA_STATUS_CHECK)
    # A unique index (not a table constraint) so SQLite needs no table rebuild.
    op.create_index('uq_media_assets_public_id', 'media_assets', ['public_id'], unique=True)
    op.create_index(op.f('ix_media_assets_checksum'), 'media_assets', ['checksum'], unique=False)


def _permissions_table():
    return sa.table(
        'permissions',
        sa.column('id', sa.Integer), sa.column('key', sa.String), sa.column('label', sa.String),
        sa.column('description', sa.String), sa.column('group', sa.String),
        sa.column('module', sa.String), sa.column('is_available', sa.Boolean),
        sa.column('is_sensitive', sa.Boolean), sa.column('sort_order', sa.Integer),
    )


def _sync_permissions():
    bind = op.get_bind()
    permissions = _permissions_table()
    roles = sa.table('roles', sa.column('id', sa.Integer), sa.column('name', sa.String))
    links = sa.table('role_permissions', sa.column('role_id', sa.Integer), sa.column('permission_id', sa.Integer))
    existing = dict(bind.execute(sa.select(permissions.c.key, permissions.c.id)).all())
    for order, (key, label, desc, group, module, available, sensitive) in enumerate(PERMISSIONS):
        values = {'label': label, 'description': desc, 'group': group, 'module': module,
                  'is_available': available, 'is_sensitive': sensitive, 'sort_order': order}
        if key in existing:
            bind.execute(permissions.update().where(permissions.c.id == existing[key]).values(**values))
        else:
            bind.execute(permissions.insert().values(key=key, **values))
    perm_ids = dict(bind.execute(sa.select(permissions.c.key, permissions.c.id)).all())
    role_ids = dict(bind.execute(sa.select(roles.c.name, roles.c.id)).all())
    current = set(bind.execute(sa.select(links.c.role_id, links.c.permission_id)).all())
    rows = []
    for role, keys in GRANTS.items():
        if role not in role_ids:
            continue  # template deleted by an administrator: leave it deleted
        for key in keys:
            pair = (role_ids[role], perm_ids[key])
            if pair not in current:
                rows.append({'role_id': pair[0], 'permission_id': pair[1]})
                current.add(pair)
    if rows:
        op.bulk_insert(links, rows)


def upgrade():
    op.create_table('publish_jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('reasons', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('trigger', sa.String(length=20), nullable=False),
    sa.Column('requested_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('not_before', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('worker', sa.String(length=100), nullable=True),
    sa.Column('release', sa.String(length=100), nullable=True),
    sa.Column('error', sa.String(length=500), nullable=True),
    sa.Column('log_tail', sa.Text(), nullable=True),
    sa.Column('details', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=True),
    sa.CheckConstraint("status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')", name=op.f('ck_publish_jobs_status_valid')),
    sa.ForeignKeyConstraint(['requested_by_id'], ['users.id'], name=op.f('fk_publish_jobs_requested_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_publish_jobs'))
    )
    op.create_index('ix_publish_jobs_status_not_before', 'publish_jobs', ['status', 'not_before'], unique=False)

    op.create_table('redirects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_path', sa.String(length=500), nullable=False),
    sa.Column('destination', sa.String(length=1000), nullable=False),
    sa.Column('status_code', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('origin', sa.String(length=20), nullable=False),
    sa.Column('note', sa.String(length=300), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("origin IN ('manual', 'slug_change', 'import')", name=op.f('ck_redirects_origin_valid')),
    sa.CheckConstraint('status_code IN (301, 302, 307, 308)', name=op.f('ck_redirects_status_code_valid')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_redirects_created_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_redirects')),
    sa.UniqueConstraint('source_path', name=op.f('uq_redirects_source_path'))
    )
    op.create_table('media_variants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('asset_id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('preset', sa.String(length=40), nullable=False),
    sa.Column('format', sa.String(length=10), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('storage_key', sa.String(length=500), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['asset_id'], ['media_assets.id'], name=op.f('fk_media_variants_asset_id_media_assets'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_media_variants')),
    sa.UniqueConstraint('storage_key', name=op.f('uq_media_variants_storage_key'))
    )
    op.create_index('ix_media_variants_asset_current', 'media_variants', ['asset_id', 'superseded_at'], unique=False)

    op.create_table('article_revisions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('article_id', sa.Integer(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('summary', sa.String(length=300), nullable=False),
    sa.Column('snapshot', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('editor_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('manual', 'autosave', 'restore', 'publish', 'system')", name=op.f('ck_article_revisions_kind_valid')),
    sa.ForeignKeyConstraint(['article_id'], ['articles.id'], name=op.f('fk_article_revisions_article_id_articles'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['editor_id'], ['users.id'], name=op.f('fk_article_revisions_editor_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_article_revisions')),
    sa.UniqueConstraint('article_id', 'number', name='uq_article_revisions_article_number')
    )
    op.create_index(op.f('ix_article_revisions_article_id'), 'article_revisions', ['article_id'], unique=False)

    _add_columns()
    _sync_permissions()


def downgrade():
    bind = op.get_bind()
    permissions = _permissions_table()
    new_ids = [
        r[0] for r in bind.execute(sa.select(permissions.c.id).where(permissions.c.key.in_(NEW_KEYS)))
    ]
    if new_ids:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN :ids")
                     .bindparams(sa.bindparam('ids', expanding=True)), {'ids': new_ids})
        bind.execute(permissions.delete().where(permissions.c.id.in_(new_ids)))
    # Media upload/delete return to "not available yet" (the previous release had no uploads),
    # so their grants are removed as well.
    old_ids = [
        r[0]
        for r in bind.execute(
            sa.select(permissions.c.id).where(permissions.c.key.in_(("media.upload", "media.delete")))
        )
    ]
    if old_ids:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN :ids")
                     .bindparams(sa.bindparam('ids', expanding=True)), {'ids': old_ids})
    bind.execute(
        permissions.update()
        .where(permissions.c.key.in_(("media.upload", "media.delete")))
        .values(is_available=False)
    )
    op.drop_index(op.f('ix_media_assets_checksum'), table_name='media_assets')
    op.drop_index('uq_media_assets_public_id', table_name='media_assets')
    article_cols = ('pending_by_id', 'pending_updated_at', 'pending_changes', 'lock_version',
                    'social_description', 'social_title')
    media_cols = ('archived_at', 'updated_at', 'dominant_color', 'has_alpha', 'version', 'focal_y',
                  'focal_x', 'original_size', 'original_mime', 'original_key', 'original_filename',
                  'checksum', 'status', 'source_url', 'credit', 'caption', 'title', 'public_id')
    op.drop_index('ix_article_revisions_article_id', table_name='article_revisions')
    op.drop_table('article_revisions')
    op.drop_index('ix_media_variants_asset_current', table_name='media_variants')
    op.drop_table('media_variants')
    op.drop_table('redirects')
    op.drop_index('ix_publish_jobs_status_not_before', table_name='publish_jobs')
    op.drop_table('publish_jobs')
    op.drop_column('authors', 'is_person')  # plain column: dropped in place on SQLite too
    if _is_sqlite():
        op.execute("PRAGMA foreign_keys=OFF")
        with op.batch_alter_table('articles') as batch_op:
            for column in article_cols:
                batch_op.drop_column(column)
        with op.batch_alter_table('media_assets') as batch_op:
            batch_op.drop_constraint(batch_op.f('ck_media_assets_status_valid'), type_='check')
            for column in media_cols:
                batch_op.drop_column(column)
        op.execute("PRAGMA foreign_keys=ON")
        return
    op.drop_constraint(op.f('fk_articles_pending_by_id_users'), 'articles', type_='foreignkey')
    for column in article_cols:
        op.drop_column('articles', column)
    op.drop_constraint(op.f('ck_media_assets_status_valid'), 'media_assets', type_='check')
    for column in media_cols:
        op.drop_column('media_assets', column)
