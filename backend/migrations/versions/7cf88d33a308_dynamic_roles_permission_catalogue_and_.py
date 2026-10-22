"""Dynamic roles, permission catalogue and article review workflow.

Incremental and non-destructive:
- adds the permissions and role_permissions tables;
- adds columns to roles (label, kind, is_active, grants_all, timestamps) and
  articles (review_status, submitted_at, approved_at, approved_by_id) with
  ALTER TABLE ... ADD COLUMN only - no table is dropped, copied or recreated;
- seeds the permission catalogue and role templates, marks the four existing
  roles as protected system roles and maps their existing permissions.

Users, roles, role assignments and invitations are never deleted. The data
below is a frozen snapshot of app/auth/permissions.py at this revision; later
catalogue changes are applied with "flask --app wsgi rbac sync".

Downgrade removes the new tables and columns and the template roles that no
user holds; custom roles and every user/role assignment are kept.

Revision ID: 7cf88d33a308
Revises: 5e0cca7bc654
Create Date: 2026-10-22 14:27:56.741901

"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text  # noqa: F401  (used by rendered JSONB types)


# revision identifiers, used by Alembic.
revision = '7cf88d33a308'
down_revision = '5e0cca7bc654'
branch_labels = None
depends_on = None

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
 ('topics.manage', 'Manage topics', '', 'Topics, tags & authors', 'taxonomy', True, False),
 ('tags.manage', 'Manage tags', '', 'Topics, tags & authors', 'taxonomy', True, False),
 ('authors.manage', 'Manage authors', '', 'Topics, tags & authors', 'taxonomy', True, False),
 ('media.view', 'View media library', '', 'Media library', 'media', True, False),
 ('media.upload', 'Upload media', '', 'Media library', 'media', False, False),
 ('media.delete', 'Delete media', '', 'Media library', 'media', False, False),
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
  'Default titles, descriptions and sharing image.',
  'SEO',
  'seo',
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

ROLES = [('super_admin',
  'Super Admin',
  'Full access to everything, including roles, users and sensitive settings.',
  'system',
  True,
  []),
 ('editor',
  'Editor',
  'Creates, edits, approves and publishes editorial content.',
  'system',
  False,
  ['articles.approve',
   'articles.archive',
   'articles.create',
   'articles.edit_any',
   'articles.edit_own',
   'articles.publish',
   'articles.submit_review',
   'articles.unpublish',
   'articles.view',
   'authors.manage',
   'dashboard.view',
   'media.view',
   'pages.edit',
   'pages.view',
   'tags.manage',
   'topics.manage']),
 ('moderator',
  'Moderator',
  'Reviews content and can take published content offline.',
  'system',
  False,
  ['articles.archive',
   'articles.unpublish',
   'articles.view',
   'dashboard.view',
   'media.view',
   'pages.view']),
 ('analyst',
  'Analyst',
  'Read-only access to the dashboard, content and analytics.',
  'system',
  False,
  ['analytics.view', 'articles.view', 'dashboard.view', 'media.view']),
 ('administrator',
  'Administrator',
  'Runs day-to-day operations across content and the website (no role management).',
  'template',
  False,
  ['analytics.view',
   'articles.approve',
   'articles.archive',
   'articles.create',
   'articles.delete',
   'articles.edit_any',
   'articles.edit_own',
   'articles.publish',
   'articles.submit_review',
   'articles.unpublish',
   'articles.view',
   'audit.view',
   'authors.manage',
   'dashboard.view',
   'media.view',
   'navigation.manage',
   'pages.edit',
   'pages.view',
   'seo.manage',
   'settings.manage',
   'tags.manage',
   'topics.manage',
   'users.manage',
   'users.view']),
 ('editor_in_chief',
  'Editor-in-Chief',
  'Owns the editorial calendar: approves, publishes and curates all content.',
  'template',
  False,
  ['analytics.view',
   'articles.approve',
   'articles.archive',
   'articles.create',
   'articles.delete',
   'articles.edit_any',
   'articles.edit_own',
   'articles.publish',
   'articles.submit_review',
   'articles.unpublish',
   'articles.view',
   'authors.manage',
   'dashboard.view',
   'media.view',
   'pages.view',
   'tags.manage',
   'topics.manage']),
 ('content_editor',
  'Content Editor',
  'Edits and prepares articles and submits them for approval.',
  'template',
  False,
  ['articles.create',
   'articles.edit_any',
   'articles.edit_own',
   'articles.submit_review',
   'articles.view',
   'dashboard.view',
   'media.view',
   'tags.manage']),
 ('content_writer',
  'Content Writer',
  'Writes and edits their own drafts and submits them for review.',
  'template',
  False,
  ['articles.create',
   'articles.edit_own',
   'articles.submit_review',
   'dashboard.view',
   'media.view']),
 ('product_manager',
  'Product Manager',
  'Will manage the digital product catalogue and pricing.',
  'template',
  False,
  ['dashboard.view']),
 ('orders_manager',
  'Orders Manager',
  'Will manage orders and refunds.',
  'template',
  False,
  ['dashboard.view']),
 ('customer_support',
  'Customer Support',
  'Will help customers with orders and account questions.',
  'template',
  False,
  ['dashboard.view']),
 ('partnerships_manager',
  'Partnerships Manager',
  'Will manage brand partnerships and sponsored campaigns.',
  'template',
  False,
  ['dashboard.view']),
 ('affiliate_manager',
  'Affiliate Manager',
  'Will manage affiliate campaigns.',
  'template',
  False,
  ['dashboard.view']),
 ('marketing_manager',
  'Marketing Manager',
  'Reviews content performance; will manage advertising and campaigns.',
  'template',
  False,
  ['analytics.view', 'articles.view', 'dashboard.view']),
 ('newsletter_manager',
  'Newsletter Manager',
  'Will manage The Positive Reset newsletter and subscribers.',
  'template',
  False,
  ['dashboard.view']),
 ('seo_manager',
  'SEO Manager',
  'Manages SEO defaults and reviews content for search visibility.',
  'template',
  False,
  ['analytics.view', 'articles.view', 'dashboard.view', 'pages.view', 'seo.manage']),
 ('website_manager',
  'Website Manager',
  'Maintains pages, homepage sections, navigation and site settings.',
  'template',
  False,
  ['dashboard.view',
   'media.view',
   'navigation.manage',
   'pages.edit',
   'pages.view',
   'settings.manage']),
 ('finance_manager',
  'Finance Manager',
  'Will review revenue and financial reports.',
  'template',
  False,
  ['dashboard.view'])]


REVIEW_CHECK = "review_status IN ('none', 'submitted', 'approved')"
KIND_CHECK = "kind IN ('system', 'template', 'custom')"


def _is_sqlite():
    return op.get_bind().dialect.name == "sqlite"


def _add_columns():
    if _is_sqlite():
        # SQLite supports ADD COLUMN with inline REFERENCES/CHECK clauses, which
        # avoids Alembic's batch mode (that would copy and recreate the tables).
        for statement in (
            "ALTER TABLE articles ADD COLUMN review_status VARCHAR(20) DEFAULT 'none' NOT NULL "
            f"CONSTRAINT ck_articles_review_status_valid CHECK ({REVIEW_CHECK})",
            "ALTER TABLE articles ADD COLUMN submitted_at DATETIME",
            "ALTER TABLE articles ADD COLUMN approved_at DATETIME",
            "ALTER TABLE articles ADD COLUMN approved_by_id INTEGER "
            "CONSTRAINT fk_articles_approved_by_id_users REFERENCES users (id) ON DELETE SET NULL",
            "ALTER TABLE roles ADD COLUMN label VARCHAR(80) DEFAULT '' NOT NULL",
            "ALTER TABLE roles ADD COLUMN kind VARCHAR(20) DEFAULT 'custom' NOT NULL "
            f"CONSTRAINT ck_roles_kind_valid CHECK ({KIND_CHECK})",
            "ALTER TABLE roles ADD COLUMN is_active BOOLEAN DEFAULT '1' NOT NULL",
            "ALTER TABLE roles ADD COLUMN grants_all BOOLEAN DEFAULT '0' NOT NULL",
            "ALTER TABLE roles ADD COLUMN created_at DATETIME",
            "ALTER TABLE roles ADD COLUMN updated_at DATETIME",
        ):
            op.execute(statement)
        return
    op.add_column('articles', sa.Column('review_status', sa.String(length=20), server_default='none', nullable=False))
    op.add_column('articles', sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('articles', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('articles', sa.Column('approved_by_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('fk_articles_approved_by_id_users'), 'articles', 'users', ['approved_by_id'], ['id'], ondelete='SET NULL')
    op.create_check_constraint(op.f('ck_articles_review_status_valid'), 'articles', REVIEW_CHECK)
    op.add_column('roles', sa.Column('label', sa.String(length=80), server_default='', nullable=False))
    op.add_column('roles', sa.Column('kind', sa.String(length=20), server_default='custom', nullable=False))
    op.add_column('roles', sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False))
    op.add_column('roles', sa.Column('grants_all', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('roles', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('roles', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(op.f('ck_roles_kind_valid'), 'roles', KIND_CHECK)


def _seed():
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    permissions = sa.table(
        'permissions',
        sa.column('id', sa.Integer), sa.column('key', sa.String), sa.column('label', sa.String),
        sa.column('description', sa.String), sa.column('group', sa.String),
        sa.column('module', sa.String), sa.column('is_available', sa.Boolean),
        sa.column('is_sensitive', sa.Boolean), sa.column('sort_order', sa.Integer),
    )
    roles = sa.table(
        'roles',
        sa.column('id', sa.Integer), sa.column('name', sa.String), sa.column('label', sa.String),
        sa.column('description', sa.String), sa.column('kind', sa.String),
        sa.column('is_active', sa.Boolean), sa.column('grants_all', sa.Boolean),
        sa.column('created_at', sa.DateTime(timezone=True)),
        sa.column('updated_at', sa.DateTime(timezone=True)),
    )
    role_permissions = sa.table(
        'role_permissions', sa.column('role_id', sa.Integer), sa.column('permission_id', sa.Integer)
    )
    op.bulk_insert(permissions, [
        {'key': k, 'label': label, 'description': desc, 'group': group, 'module': module,
         'is_available': available, 'is_sensitive': sensitive, 'sort_order': order}
        for order, (k, label, desc, group, module, available, sensitive) in enumerate(PERMISSIONS)
    ])
    perm_ids = dict(bind.execute(sa.select(permissions.c.key, permissions.c.id)).all())
    existing = dict(bind.execute(sa.select(roles.c.name, roles.c.id)).all())
    links = []
    for name, label, desc, kind, grants_all, keys in ROLES:
        values = {'label': label, 'description': desc, 'kind': kind, 'grants_all': grants_all,
                  'is_active': True, 'updated_at': now}
        if name in existing:
            # Existing role (the four built-ins): keep its id and every assignment.
            bind.execute(roles.update().where(roles.c.id == existing[name]).values(**values))
            role_id = existing[name]
        else:
            role_id = bind.execute(
                roles.insert().values(name=name, created_at=now, **values).returning(roles.c.id)
            ).scalar_one()
        links += [{'role_id': role_id, 'permission_id': perm_ids[k]} for k in keys]
    # Roles that existed but are not in the snapshot keep working as custom roles
    # with no permissions until a super administrator assigns some.
    bind.execute(
        roles.update().where(roles.c.label == '').values(label=roles.c.name, updated_at=now)
    )
    if links:
        op.bulk_insert(role_permissions, links)


def upgrade():
    op.create_table('permissions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=False),
    sa.Column('description', sa.String(length=300), nullable=False),
    sa.Column('group', sa.String(length=60), nullable=False),
    sa.Column('module', sa.String(length=40), nullable=False),
    sa.Column('is_available', sa.Boolean(), nullable=False),
    sa.Column('is_sensitive', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_permissions')),
    sa.UniqueConstraint('key', name=op.f('uq_permissions_key'))
    )
    op.create_table('role_permissions',
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('permission_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], name=op.f('fk_role_permissions_permission_id_permissions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name=op.f('fk_role_permissions_role_id_roles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('role_id', 'permission_id', name=op.f('pk_role_permissions'))
    )
    op.create_index('ix_role_permissions_permission_id', 'role_permissions', ['permission_id'], unique=False)
    _add_columns()
    _seed()


def downgrade():
    bind = op.get_bind()
    if _is_sqlite():
        # Batch mode rebuilds roles/articles below; referencing rows (user_roles,
        # account links) stay intact, so foreign-key checks are paused meanwhile.
        op.execute("PRAGMA foreign_keys=OFF")
    # Remove only the template roles this revision introduced and nobody holds.
    templates = [name for name, _l, _d, kind, _g, _k in ROLES if kind == 'template']
    bind.execute(sa.text(
        "DELETE FROM roles WHERE kind = 'template' AND name IN :names "
        "AND id NOT IN (SELECT role_id FROM user_roles)"
    ).bindparams(sa.bindparam('names', expanding=True)), {'names': templates})
    op.drop_index('ix_role_permissions_permission_id', table_name='role_permissions')
    op.drop_table('role_permissions')
    op.drop_table('permissions')
    if _is_sqlite():
        # SQLite cannot drop constrained columns in place, so downgrade uses batch mode.
        with op.batch_alter_table('roles') as batch_op:
            batch_op.drop_constraint(batch_op.f('ck_roles_kind_valid'), type_='check')
            for column in ('updated_at', 'created_at', 'grants_all', 'is_active', 'kind', 'label'):
                batch_op.drop_column(column)
        with op.batch_alter_table('articles') as batch_op:
            batch_op.drop_constraint(batch_op.f('ck_articles_review_status_valid'), type_='check')
            for column in ('approved_by_id', 'approved_at', 'submitted_at', 'review_status'):
                batch_op.drop_column(column)
        op.execute("PRAGMA foreign_keys=ON")
        return
    op.drop_constraint(op.f('ck_roles_kind_valid'), 'roles', type_='check')
    for column in ('updated_at', 'created_at', 'grants_all', 'is_active', 'kind', 'label'):
        op.drop_column('roles', column)
    op.drop_constraint(op.f('ck_articles_review_status_valid'), 'articles', type_='check')
    op.drop_constraint(op.f('fk_articles_approved_by_id_users'), 'articles', type_='foreignkey')
    for column in ('approved_by_id', 'approved_at', 'submitted_at', 'review_status'):
        op.drop_column('articles', column)
