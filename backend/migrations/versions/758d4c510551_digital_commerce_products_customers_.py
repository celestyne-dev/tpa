"""Digital commerce: products, private files, customers, orders, payments and downloads.

Incremental and non-destructive:
- new tables only: product catalogue (products, prices, private file versions,
  categories, collections, bundles, revisions), customers (accounts, sessions,
  email tokens), orders (items, payment attempts, verified transactions,
  provider webhook events, receipts, refunds, email delivery records) and
  access (entitlements, entitlement events, download grants and activity).
  No existing table or column is altered or rebuilt;
- permissions: granular product, order, customer, entitlement, download,
  finance and payment-event permissions are added; the previously planned
  products/orders/customers/finance permissions become available. Grants go
  to the commerce role templates that still exist (Administrator, Product
  Manager, Orders Manager, Customer Support, Finance Manager, Marketing
  Manager). Editorial roles (Editor, Moderator, Analyst, writers) gain
  nothing; payments.configure stays sensitive (Super Admin only); custom
  roles are unchanged;
- data: a starter catalogue of five clearly labelled "coming soon" titles (no
  prices, files or page counts), four categories, one collection and a draft
  bundle, inserted only when the slug does not exist yet.

Users, roles, assignments, articles, pages, homepage sections, media, SEO
data, redirects, settings and publishing jobs are preserved.

Downgrade drops the commerce tables (orders and customer data included, so
take a backup first), removes the new permissions and returns the planned
permissions to "unavailable". Private product files on disk are left in place.

Revision ID: 758d4c510551
Revises: de3d968df6ce
Create Date: 2026-10-23 05:30:38.323904

"""

import json
import secrets
from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text  # noqa: F401  (used by rendered JSONB types)
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "758d4c510551"
down_revision = "de3d968df6ce"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")

# Frozen snapshot of app/auth/permissions.py at this revision.
# (key, label, description, group, module, available, sensitive)
PERMISSIONS = [
    ("dashboard.view", "View dashboard", "", "Dashboard & analytics", "dashboard", True, False),
    (
        "analytics.view",
        "View content analytics",
        "",
        "Dashboard & analytics",
        "analytics",
        True,
        False,
    ),
    (
        "articles.view",
        "View all articles",
        "See every article, including other people's drafts.",
        "Articles",
        "articles",
        True,
        False,
    ),
    ("articles.create", "Create articles", "", "Articles", "articles", True, False),
    (
        "articles.edit_own",
        "Edit own drafts",
        "Edit articles you created while they are drafts.",
        "Articles",
        "articles",
        True,
        False,
    ),
    ("articles.edit_any", "Edit any article", "", "Articles", "articles", True, False),
    ("articles.submit_review", "Submit for review", "", "Articles", "articles", True, False),
    ("articles.approve", "Approve articles", "", "Articles", "articles", True, False),
    ("articles.publish", "Publish and schedule", "", "Articles", "articles", True, False),
    ("articles.unpublish", "Unpublish", "", "Articles", "articles", True, False),
    ("articles.archive", "Archive and restore", "", "Articles", "articles", True, False),
    (
        "articles.delete",
        "Delete unpublished drafts",
        "Permanently delete drafts that were never published.",
        "Articles",
        "articles",
        True,
        False,
    ),
    (
        "articles.view_revisions",
        "View revision history",
        "For articles you can open.",
        "Articles",
        "articles",
        True,
        False,
    ),
    (
        "articles.restore_revisions",
        "Restore revisions",
        "Only on articles you are allowed to edit.",
        "Articles",
        "articles",
        True,
        False,
    ),
    (
        "articles.preview",
        "Preview drafts",
        "Private, non-indexed preview of articles you can open.",
        "Articles",
        "articles",
        True,
        False,
    ),
    ("topics.manage", "Manage topics", "", "Topics, tags & authors", "taxonomy", True, False),
    ("tags.manage", "Manage tags", "", "Topics, tags & authors", "taxonomy", True, False),
    ("authors.manage", "Manage authors", "", "Topics, tags & authors", "taxonomy", True, False),
    ("media.view", "View media library", "", "Media library", "media", True, False),
    (
        "media.upload",
        "Upload media",
        "Upload images; they are validated and optimised automatically.",
        "Media library",
        "media",
        True,
        False,
    ),
    (
        "media.edit",
        "Edit media details",
        "Alt text, title, caption, credit and focal point.",
        "Media library",
        "media",
        True,
        False,
    ),
    ("media.replace", "Replace media files", "", "Media library", "media", True, False),
    (
        "media.delete",
        "Archive and delete media",
        "Media still used by content can be archived but never deleted.",
        "Media library",
        "media",
        True,
        False,
    ),
    (
        "homepage.view",
        "View homepage builder",
        "See the homepage sections, drafts, previews and history.",
        "Pages & homepage",
        "homepage",
        True,
        False,
    ),
    (
        "homepage.edit",
        "Edit homepage drafts",
        "Change, add, reorder and restore homepage sections as a draft.",
        "Pages & homepage",
        "homepage",
        True,
        False,
    ),
    (
        "homepage.publish",
        "Publish the homepage",
        "Make homepage drafts live (queues a site rebuild).",
        "Pages & homepage",
        "homepage",
        True,
        False,
    ),
    ("pages.view", "View pages", "", "Pages & homepage", "pages", True, False),
    (
        "pages.edit",
        "Edit page drafts",
        "Edit page content, sections and SEO as a draft; restore revisions.",
        "Pages & homepage",
        "pages",
        True,
        False,
    ),
    ("pages.create", "Create and duplicate pages", "", "Pages & homepage", "pages", True, False),
    (
        "pages.publish",
        "Publish pages",
        "Publish, schedule, unpublish, archive and restore pages.",
        "Pages & homepage",
        "pages",
        True,
        False,
    ),
    (
        "reusable_sections.manage",
        "Manage shared sections and calls to action",
        "Edit shared sections (changes can update every page using them).",
        "Pages & homepage",
        "pages",
        True,
        False,
    ),
    (
        "branding.manage",
        "Manage branding",
        "Site name, logos, favicon, social image and approved style presets.",
        "Site settings",
        "branding",
        True,
        False,
    ),
    (
        "announcements.manage",
        "Manage announcement banners",
        "",
        "Site settings",
        "announcements",
        True,
        False,
    ),
    ("navigation.manage", "Manage navigation menus", "", "Navigation", "navigation", True, False),
    (
        "settings.manage",
        "Manage site settings",
        "Contact details, social links, footer and the newsletter flag.",
        "Site settings",
        "settings",
        True,
        False,
    ),
    (
        "settings.technical",
        "Manage indexing and canonical URL",
        "Search engine indexing and the canonical website address (Super Admin).",
        "Site settings",
        "settings",
        True,
        True,
    ),
    ("settings.security", "Manage security settings", "", "Site settings", "settings", False, True),
    (
        "seo.manage",
        "Manage SEO settings",
        "Default titles, descriptions and sharing image; article canonical URLs, indexing and "
        "post-publication slug changes.",
        "SEO",
        "seo",
        True,
        False,
    ),
    (
        "seo.view",
        "View SEO audit",
        "The SEO dashboard and per-article checks.",
        "SEO",
        "seo",
        True,
        False,
    ),
    ("redirects.manage", "Manage redirects", "", "SEO", "redirects", True, False),
    (
        "publishing.view",
        "View publishing jobs",
        "Static site build status and history.",
        "Publishing",
        "publishing",
        True,
        False,
    ),
    (
        "publishing.manage",
        "Run and retry publishing jobs",
        "",
        "Publishing",
        "publishing",
        True,
        False,
    ),
    (
        "products.view",
        "View products",
        "See the product catalogue, drafts, files list and history.",
        "Digital products",
        "products",
        True,
        False,
    ),
    (
        "products.create",
        "Create and duplicate products",
        "",
        "Digital products",
        "products",
        True,
        False,
    ),
    (
        "products.edit",
        "Edit product drafts",
        "Descriptions, images, categories, collections, FAQs and SEO (as a draft).",
        "Digital products",
        "products",
        True,
        False,
    ),
    (
        "products.publish",
        "Publish products",
        "Publish, unpublish, schedule availability and put products on sale.",
        "Digital products",
        "products",
        True,
        False,
    ),
    (
        "products.archive",
        "Archive and restore products",
        "",
        "Digital products",
        "products",
        True,
        False,
    ),
    (
        "products.manage_prices",
        "Set and approve prices",
        "Prices, compare-at and promotional prices in each currency.",
        "Digital products",
        "products",
        True,
        False,
    ),
    (
        "products.manage_files",
        "Manage private product files",
        "Upload, replace, deactivate and download deliverable files.",
        "Digital products",
        "products",
        True,
        False,
    ),
    (
        "products.manage_bundles",
        "Manage bundles",
        "Choose which products a bundle includes.",
        "Digital products",
        "products",
        True,
        False,
    ),
    (
        "products.manage",
        "Manage products (legacy)",
        "Replaced by the granular product permissions above.",
        "Digital products",
        "products",
        False,
        False,
    ),
    ("orders.view", "View orders", "", "Orders & refunds", "orders", True, False),
    (
        "orders.manage",
        "Manage orders",
        "Re-check payments, cancel unpaid orders, resend receipts and add notes.",
        "Orders & refunds",
        "orders",
        True,
        False,
    ),
    ("orders.export", "Export orders", "", "Orders & refunds", "orders", True, False),
    (
        "refunds.issue",
        "Issue refunds",
        "Request and record refunds (provider refunds only when configured).",
        "Orders & refunds",
        "orders",
        True,
        False,
    ),
    (
        "payments.view_events",
        "View payment events",
        "Payment attempts, provider webhooks and verification results.",
        "Orders & refunds",
        "payments",
        True,
        False,
    ),
    (
        "payments.configure",
        "Configure payments",
        "Payment provider, test/live mode, currencies and checkout availability.",
        "Orders & refunds",
        "payments",
        True,
        True,
    ),
    ("customers.view", "View customers", "", "Customers", "customers", True, False),
    (
        "customers.support",
        "Assist customers",
        "Resend verification and password-reset emails, add support notes.",
        "Customers",
        "customers",
        True,
        False,
    ),
    (
        "customers.manage",
        "Manage customer accounts",
        "Disable or reactivate accounts, mark test accounts, process deletions.",
        "Customers",
        "customers",
        True,
        False,
    ),
    ("entitlements.view", "View download access", "", "Customers", "entitlements", True, False),
    (
        "entitlements.manage",
        "Grant and revoke download access",
        "",
        "Customers",
        "entitlements",
        True,
        False,
    ),
    ("downloads.audit", "View download activity", "", "Customers", "entitlements", True, False),
    ("partnerships.view", "View partnerships", "", "Partnerships", "partnerships", False, False),
    (
        "partnerships.manage",
        "Manage partnerships",
        "",
        "Partnerships",
        "partnerships",
        False,
        False,
    ),
    ("advertising.view", "View advertising", "", "Advertising", "advertising", False, False),
    ("advertising.manage", "Manage advertising", "", "Advertising", "advertising", False, False),
    (
        "affiliates.view",
        "View affiliate campaigns",
        "",
        "Affiliate campaigns",
        "affiliates",
        False,
        False,
    ),
    (
        "affiliates.manage",
        "Manage affiliate campaigns",
        "",
        "Affiliate campaigns",
        "affiliates",
        False,
        False,
    ),
    (
        "newsletters.manage",
        "Manage newsletters",
        "",
        "Newsletters & subscribers",
        "newsletters",
        False,
        False,
    ),
    (
        "subscribers.view",
        "View subscribers",
        "",
        "Newsletters & subscribers",
        "newsletters",
        False,
        False,
    ),
    (
        "subscribers.export",
        "Export subscribers",
        "",
        "Newsletters & subscribers",
        "newsletters",
        False,
        False,
    ),
    ("courses.manage", "Manage courses", "", "Courses & memberships", "courses", False, False),
    (
        "memberships.manage",
        "Manage memberships",
        "",
        "Courses & memberships",
        "memberships",
        False,
        False,
    ),
    (
        "finance.view",
        "View revenue reports",
        "Sales, refunds and downloads by currency and product.",
        "Finance",
        "finance",
        True,
        False,
    ),
    ("finance.export", "Export revenue reports", "", "Finance", "finance", True, False),
    ("finance.manage", "Manage finance", "", "Finance", "finance", False, False),
    ("users.view", "View administrators", "", "Users, roles & audit", "users", True, False),
    (
        "users.manage",
        "Manage administrator accounts",
        "Disable, reactivate and reset passwords of administrators with equal or fewer permissions.",
        "Users, roles & audit",
        "users",
        True,
        False,
    ),
    (
        "roles.manage",
        "Manage roles and permissions",
        "",
        "Users, roles & audit",
        "roles",
        True,
        True,
    ),
    (
        "roles.assign",
        "Assign roles and invite administrators",
        "",
        "Users, roles & audit",
        "roles",
        True,
        True,
    ),
    ("audit.view", "View audit log", "", "Users, roles & audit", "audit", True, False),
]

NEW_KEYS = [
    "products.create",
    "products.edit",
    "products.publish",
    "products.archive",
    "products.manage_prices",
    "products.manage_files",
    "products.manage_bundles",
    "orders.export",
    "payments.view_events",
    "customers.support",
    "entitlements.view",
    "entitlements.manage",
    "downloads.audit",
    "finance.export",
]

# Planned in Batch 02-04 (unavailable); available from this revision.
NOW_AVAILABLE = [
    "products.view",
    "orders.view",
    "orders.manage",
    "refunds.issue",
    "payments.configure",
    "customers.view",
    "customers.manage",
    "finance.view",
]

# Commerce role templates (only if they still exist; edited templates keep their other grants).
GRANTS = {
    "administrator": [
        "customers.manage",
        "customers.support",
        "customers.view",
        "downloads.audit",
        "entitlements.manage",
        "entitlements.view",
        "finance.view",
        "orders.export",
        "orders.manage",
        "orders.view",
        "payments.view_events",
        "products.archive",
        "products.create",
        "products.edit",
        "products.manage_bundles",
        "products.manage_files",
        "products.manage_prices",
        "products.publish",
        "products.view",
    ],
    "customer_support": [
        "customers.support",
        "customers.view",
        "downloads.audit",
        "entitlements.view",
        "orders.view",
        "products.view",
    ],
    "finance_manager": [
        "finance.export",
        "finance.view",
        "orders.export",
        "orders.view",
        "payments.view_events",
        "products.view",
        "refunds.issue",
    ],
    "marketing_manager": ["products.view"],
    "orders_manager": [
        "customers.support",
        "customers.view",
        "downloads.audit",
        "entitlements.manage",
        "entitlements.view",
        "orders.export",
        "orders.manage",
        "orders.view",
        "payments.view_events",
        "products.view",
        "refunds.issue",
    ],
    "product_manager": [
        "media.edit",
        "media.upload",
        "media.view",
        "products.archive",
        "products.create",
        "products.edit",
        "products.manage_bundles",
        "products.manage_files",
        "products.manage_prices",
        "products.publish",
        "products.view",
    ],
}

STARTER_CATEGORIES = [
    {"slug": "ebooks", "name": "eBooks", "sort_order": 1},
    {"slug": "workbooks", "name": "Workbooks", "sort_order": 2},
    {"slug": "journals", "name": "Journals & planners", "sort_order": 3},
    {"slug": "guides", "name": "Guides & resources", "sort_order": 4},
]

STARTER_PRODUCTS = [
    {
        "slug": "the-power-of-starting-again",
        "product_type": "ebook",
        "title": "The Power of Starting Again",
        "subtitle": "A guide to rebuilding with hope and intention",
        "short_description": "A compassionate, practical guide for anyone facing a new chapter after "
        "loss, change or disappointment, with reflections and steps to help you "
        "rebuild at your own pace.",
        "benefits": [
            "Reflections for processing endings honestly",
            "Practical steps for rebuilding routines and direction",
            "Prompts to reconnect with your values and hopes",
        ],
        "format_label": "eBook",
        "cover_theme": "sage",
        "categories": ["ebooks"],
        "featured_order": 1,
    },
    {
        "slug": "the-30-day-mindset-reset-workbook",
        "product_type": "workbook",
        "title": "The 30-Day Mindset Reset Workbook",
        "subtitle": "Daily prompts for a calmer, more hopeful outlook",
        "short_description": "A guided 30-day workbook with short daily exercises to help you notice "
        "unhelpful thought patterns, practise gratitude and build a more balanced "
        "perspective.",
        "benefits": [
            "One focused exercise for each day",
            "Space to journal and track what you notice",
            "Weekly reflections to consolidate progress",
        ],
        "format_label": "Printable workbook",
        "cover_theme": "gold",
        "categories": ["workbooks"],
        "featured_order": 2,
    },
    {
        "slug": "the-daily-reflection-journal",
        "product_type": "journal",
        "title": "The Daily Reflection Journal",
        "subtitle": "A few quiet minutes to check in with yourself",
        "short_description": "A simple, printable journal with gentle morning and evening prompts to "
        "help you notice what matters, celebrate small wins and end each day with "
        "perspective.",
        "benefits": [
            "Morning intentions and evening reflections",
            "Gratitude and small-wins pages",
            "Monthly look-back prompts",
        ],
        "format_label": "Printable journal",
        "cover_theme": "olive",
        "categories": ["journals"],
        "featured_order": 3,
    },
    {
        "slug": "the-confidence-and-self-worth-workbook",
        "product_type": "workbook",
        "title": "The Confidence & Self-Worth Workbook",
        "subtitle": "Building confidence from the inside out",
        "short_description": "An encouraging workbook for recognising your value, setting healthy "
        "boundaries and building confidence that does not depend on other people's "
        "approval.",
        "benefits": [
            "Exercises for quieting the inner critic",
            "Guidance on boundaries and self-respect",
            "Reflection prompts for everyday confidence",
        ],
        "format_label": "Printable workbook",
        "cover_theme": "charcoal",
        "categories": ["workbooks"],
        "featured_order": 4,
    },
    {
        "slug": "the-letting-go-and-moving-forward-guide",
        "product_type": "reflection_guide",
        "title": "The Letting Go & Moving Forward Guide",
        "subtitle": "Making peace with the past, one step at a time",
        "short_description": "A reflective guide for releasing what you cannot change, processing regret "
        "with kindness and choosing small, steady steps towards what comes next.",
        "benefits": [
            "Reflections for acceptance and forgiveness",
            "Exercises for loosening the grip of regret",
            "Gentle next-step planning",
        ],
        "format_label": "Reflection guide",
        "cover_theme": "blush",
        "categories": ["guides"],
        "featured_order": 5,
    },
]

STARTER_COLLECTION = {
    "slug": "fresh-start",
    "name": "The Fresh Start Collection",
    "description": "Three companions for a new chapter: a guide to starting again, a 30-day mindset "
    "reset and a daily reflection journal.",
    "products": [
        "the-power-of-starting-again",
        "the-30-day-mindset-reset-workbook",
        "the-daily-reflection-journal",
    ],
}

STARTER_BUNDLE = {
    "slug": "the-fresh-start-collection",
    "product_type": "bundle",
    "title": "The Fresh Start Collection",
    "subtitle": "Three resources for a new chapter",
    "short_description": "The Power of Starting Again, The 30-Day Mindset Reset Workbook and The "
    "Daily Reflection Journal together.",
    "format_label": "Bundle",
    "cover_theme": "cream",
    "items": [
        "the-power-of-starting-again",
        "the-30-day-mindset-reset-workbook",
        "the-daily-reflection-journal",
    ],
}

PLACEHOLDER_NOTE = "This title is in development and is not yet available to purchase. Details may change as it is finalised."


def _is_sqlite():
    return op.get_bind().dialect.name == "sqlite"


def _current_version_fk():
    # SQLite accepts the forward reference inline; PostgreSQL gets it after both tables exist.
    if _is_sqlite():
        return [
            sa.ForeignKeyConstraint(
                ["current_version_id"],
                ["product_file_versions.id"],
                name=op.f("fk_product_files_current_version_id_product_file_versions"),
                ondelete="SET NULL",
            )
        ]
    return []


def _permissions_table():
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


def _sync_permissions():
    bind = op.get_bind()
    permissions = _permissions_table()
    roles = sa.table("roles", sa.column("id", sa.Integer), sa.column("name", sa.String))
    links = sa.table(
        "role_permissions", sa.column("role_id", sa.Integer), sa.column("permission_id", sa.Integer)
    )
    existing = dict(bind.execute(sa.select(permissions.c.key, permissions.c.id)).all())
    for order, (key, label, desc, group, module, available, sensitive) in enumerate(PERMISSIONS):
        values = {
            "label": label,
            "description": desc,
            "group": group,
            "module": module,
            "is_available": available,
            "is_sensitive": sensitive,
            "sort_order": order,
        }
        if key in existing:
            bind.execute(
                permissions.update().where(permissions.c.id == existing[key]).values(**values)
            )
        else:
            bind.execute(permissions.insert().values(key=key, **values))
    perm_ids = dict(bind.execute(sa.select(permissions.c.key, permissions.c.id)).all())
    role_ids = dict(bind.execute(sa.select(roles.c.name, roles.c.id)).all())
    current = set(bind.execute(sa.select(links.c.role_id, links.c.permission_id)).all())
    wanted = set()
    for role, keys in GRANTS.items():
        if role in role_ids:  # templates deleted by an administrator stay deleted
            wanted |= {(role_ids[role], perm_ids[k]) for k in keys}
    rows = [{"role_id": r, "permission_id": p} for r, p in sorted(wanted - current)]
    if rows:
        op.bulk_insert(links, rows)


def _snapshot(product, category_ids):
    return {
        "version": 1,
        "slug": product["slug"],
        "product_type": product["product_type"],
        "title": product["title"],
        "subtitle": product["subtitle"],
        "short_description": product["short_description"],
        "description": product["description"],
        "benefits": product.get("benefits", []),
        "included": [],
        "faq": [],
        "audience": "",
        "format_label": product["format_label"],
        "language": "en",
        "edition": "",
        "page_count": None,
        "sample_text": "",
        "author_id": None,
        "cover_media_id": None,
        "cover_theme": product["cover_theme"],
        "gallery": [],
        "social_image_id": None,
        "seo_title": None,
        "meta_description": None,
        "noindex": False,
        "category_ids": category_ids,
        "tags": [],
    }


def _seed_catalogue():
    bind = op.get_bind()
    now = datetime.now(UTC)
    cat_t = sa.table(
        "product_categories",
        sa.column("id", sa.Integer),
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    prod_cols = [
        "id",
        "public_id",
        "slug",
        "published_slug",
        "product_type",
        "title",
        "subtitle",
        "short_description",
        "description",
        "benefits",
        "included",
        "faq",
        "audience",
        "format_label",
        "language",
        "edition",
        "sample_text",
        "cover_theme",
        "gallery",
        "noindex",
        "tax_category",
        "status",
        "sales_status",
        "pricing_model",
        "is_featured",
        "featured_order",
        "published_at",
        "first_published_at",
        "published_snapshot",
        "lock_version",
        "created_at",
        "updated_at",
    ]
    json_cols = {"description", "benefits", "included", "faq", "gallery", "published_snapshot"}
    bool_cols = {"noindex", "is_featured"}
    int_cols = {"id", "featured_order", "lock_version"}

    def col_type(c):
        if c in json_cols:
            return JSON
        if c in bool_cols:
            return sa.Boolean
        if c in int_cols:
            return sa.Integer
        return sa.DateTime(timezone=True) if c.endswith("_at") else sa.String

    prod_t = sa.table("products", *[sa.column(c, col_type(c)) for c in prod_cols])
    link_t = sa.table(
        "product_category_links",
        sa.column("product_id", sa.Integer),
        sa.column("category_id", sa.Integer),
    )
    rev_t = sa.table(
        "product_revisions",
        sa.column("product_id", sa.Integer),
        sa.column("number", sa.Integer),
        sa.column("kind", sa.String),
        sa.column("summary", sa.String),
        sa.column("snapshot", JSON),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    coll_t = sa.table(
        "product_collections",
        sa.column("id", sa.Integer),
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("is_featured", sa.Boolean),
        sa.column("sort_order", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    item_t = sa.table(
        "product_collection_items",
        sa.column("collection_id", sa.Integer),
        sa.column("product_id", sa.Integer),
        sa.column("position", sa.Integer),
    )
    bundle_t = sa.table(
        "bundle_items",
        sa.column("bundle_id", sa.Integer),
        sa.column("product_id", sa.Integer),
        sa.column("position", sa.Integer),
    )

    cats = dict(bind.execute(sa.select(cat_t.c.slug, cat_t.c.id)).all())
    for c in STARTER_CATEGORIES:
        if c["slug"] not in cats:
            bind.execute(
                cat_t.insert().values(
                    description="", is_active=True, created_at=now, updated_at=now, **c
                )
            )
    cats = dict(bind.execute(sa.select(cat_t.c.slug, cat_t.c.id)).all())
    slugs = dict(bind.execute(sa.select(prod_t.c.slug, prod_t.c.id)).all())

    def insert_product(spec, **extra):
        values = {c: None for c in prod_cols if c != "id"}
        values.update(
            public_id=secrets.token_hex(8),
            slug=spec["slug"],
            product_type=spec["product_type"],
            title=spec["title"],
            subtitle=spec["subtitle"],
            short_description=spec["short_description"],
            description=spec.get("description", []),
            benefits=spec.get("benefits", []),
            included=[],
            faq=[],
            audience="",
            format_label=spec["format_label"],
            language="en",
            edition="",
            sample_text="",
            cover_theme=spec["cover_theme"],
            gallery=[],
            noindex=False,
            tax_category="digital_goods",
            pricing_model="paid",
            is_featured=False,
            featured_order=0,
            lock_version=1,
            created_at=now,
            updated_at=now,
        )
        values.update(extra)
        bind.execute(prod_t.insert().values(**values))
        return bind.execute(
            sa.select(prod_t.c.id).where(prod_t.c.slug == spec["slug"])
        ).scalar_one()

    for spec in STARTER_PRODUCTS:
        if spec["slug"] in slugs:
            continue
        spec = dict(
            spec,
            description=[
                {"type": "paragraph", "text": spec["short_description"]},
                {"type": "paragraph", "text": PLACEHOLDER_NOTE},
            ],
        )
        category_ids = [cats[c] for c in spec["categories"] if c in cats]
        snapshot = _snapshot(spec, category_ids)
        product_id = insert_product(
            spec,
            status="published",
            sales_status="coming_soon",
            is_featured=True,
            featured_order=spec["featured_order"],
            published_slug=spec["slug"],
            published_at=now,
            first_published_at=now,
            published_snapshot=snapshot,
        )
        for cid in category_ids:
            bind.execute(link_t.insert().values(product_id=product_id, category_id=cid))
        bind.execute(
            rev_t.insert().values(
                product_id=product_id,
                number=1,
                kind="system",
                summary="Starter catalogue (coming soon)",
                snapshot=snapshot,
                created_at=now,
            )
        )
        slugs[spec["slug"]] = product_id
    if (
        bind.execute(
            sa.select(coll_t.c.id).where(coll_t.c.slug == STARTER_COLLECTION["slug"])
        ).first()
        is None
    ):
        bind.execute(
            coll_t.insert().values(
                slug=STARTER_COLLECTION["slug"],
                name=STARTER_COLLECTION["name"],
                description=STARTER_COLLECTION["description"],
                is_active=True,
                is_featured=True,
                sort_order=0,
                created_at=now,
                updated_at=now,
            )
        )
        cid = bind.execute(
            sa.select(coll_t.c.id).where(coll_t.c.slug == STARTER_COLLECTION["slug"])
        ).scalar_one()
        for position, slug in enumerate(STARTER_COLLECTION["products"]):
            if slug in slugs:
                bind.execute(
                    item_t.insert().values(
                        collection_id=cid, product_id=slugs[slug], position=position
                    )
                )
    if STARTER_BUNDLE["slug"] not in slugs:
        bundle_id = insert_product(STARTER_BUNDLE, status="draft", sales_status="coming_soon")
        for position, slug in enumerate(STARTER_BUNDLE["items"]):
            if slug in slugs:
                bind.execute(
                    bundle_t.insert().values(
                        bundle_id=bundle_id, product_id=slugs[slug], position=position
                    )
                )


def upgrade():
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_test_account", sa.Boolean(), nullable=False),
        sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("support_notes", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'disabled', 'deleted')", name=op.f("ck_customers_status_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("email", name=op.f("uq_customers_email")),
        sa.UniqueConstraint("public_id", name=op.f("uq_customers_public_id")),
    )
    op.create_table(
        "product_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=400), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_categories")),
        sa.UniqueConstraint("slug", name=op.f("uq_product_categories_slug")),
    )
    op.create_table(
        "customer_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_customer_sessions_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_customer_sessions_token_hash")),
    )
    with op.batch_alter_table("customer_sessions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_customer_sessions_customer_active", ["customer_id", "revoked_at"], unique=False
        )

    op.create_table(
        "customer_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('verify_email', 'password_reset')",
            name=op.f("ck_customer_tokens_purpose_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_customer_tokens_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_customer_tokens_token_hash")),
    )
    with op.batch_alter_table("customer_tokens", schema=None) as batch_op:
        batch_op.create_index(
            "ix_customer_tokens_customer_purpose", ["customer_id", "purpose"], unique=False
        )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal_minor", sa.BigInteger(), nullable=False),
        sa.Column("discount_minor", sa.BigInteger(), nullable=False),
        sa.Column("tax_minor", sa.BigInteger(), nullable=False),
        sa.Column("total_minor", sa.BigInteger(), nullable=False),
        sa.Column("refunded_minor", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("cart_hash", sa.String(length=64), nullable=False),
        sa.Column("terms_version", sa.String(length=40), nullable=False),
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("review_reason", sa.String(length=300), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("mode IN ('test', 'live')", name=op.f("ck_orders_mode_valid")),
        sa.CheckConstraint(
            "status IN ('pending', 'awaiting_payment', 'paid', 'failed', 'cancelled', 'partially_refunded', 'refunded')",
            name=op.f("ck_orders_status_valid"),
        ),
        sa.CheckConstraint(
            "refunded_minor >= 0 AND refunded_minor <= total_minor",
            name=op.f("ck_orders_refund_within_total"),
        ),
        sa.CheckConstraint(
            "subtotal_minor >= 0 AND total_minor >= 0", name=op.f("ck_orders_amounts_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_orders_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("customer_id", "idempotency_key", name="uq_orders_idempotency"),
        sa.UniqueConstraint("number", name=op.f("uq_orders_number")),
        sa.UniqueConstraint("public_id", name=op.f("uq_orders_public_id")),
    )
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_orders_customer_id"), ["customer_id"], unique=False)
        batch_op.create_index("ix_orders_status_created", ["status", "created_at"], unique=False)

    op.create_table(
        "email_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template", sa.String(length=60), nullable=False),
        sa.Column("recipient", sa.String(length=254), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('sent', 'development_console', 'memory', 'not_configured', 'failed')",
            name=op.f("ck_email_deliveries_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_email_deliveries_customer_id_customers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_email_deliveries_order_id_orders"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_deliveries")),
    )
    with op.batch_alter_table("email_deliveries", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_email_deliveries_customer_id"), ["customer_id"], unique=False
        )
        batch_op.create_index("ix_email_deliveries_order", ["order_id"], unique=False)

    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("authorization_url", sa.String(length=500), nullable=True),
        sa.Column("access_code", sa.String(length=100), nullable=True),
        sa.Column("provider_status", sa.String(length=40), nullable=False),
        sa.Column("failure_reason", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("mode IN ('test', 'live')", name=op.f("ck_payment_attempts_mode_valid")),
        sa.CheckConstraint(
            "status IN ('created', 'initialized', 'succeeded', 'failed', 'abandoned', 'mismatch')",
            name=op.f("ck_payment_attempts_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_payment_attempts_order_id_orders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_attempts")),
        sa.UniqueConstraint("reference", name=op.f("uq_payment_attempts_reference")),
    )
    with op.batch_alter_table("payment_attempts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_payment_attempts_order_id"), ["order_id"], unique=False
        )

    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("mode", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result", sa.String(length=300), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("received_count", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('received', 'processed', 'ignored', 'rejected', 'deferred', 'error')",
            name=op.f("ck_payment_events_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_payment_events_order_id_orders"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_events")),
        sa.UniqueConstraint("provider", "dedupe_key", name="uq_payment_events_dedupe"),
    )
    with op.batch_alter_table("payment_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_payment_events_order_id"), ["order_id"], unique=False)
        batch_op.create_index("ix_payment_events_reference", ["reference"], unique=False)

    op.create_table(
        "product_collections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=600), nullable=False),
        sa.Column("cover_media_id", sa.Integer(), nullable=True),
        sa.Column("seo_title", sa.String(length=200), nullable=True),
        sa.Column("meta_description", sa.String(length=320), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["cover_media_id"],
            ["media_assets.id"],
            name=op.f("fk_product_collections_cover_media_id_media_assets"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_collections")),
        sa.UniqueConstraint("slug", name=op.f("uq_product_collections_slug")),
    )
    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(length=40), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "data",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_receipts_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receipts")),
        sa.UniqueConstraint("number", name=op.f("uq_receipts_number")),
        sa.UniqueConstraint("order_id", name=op.f("uq_receipts_order_id")),
    )
    op.create_table(
        "refunds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_refund_id", sa.String(length=100), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("revoke_access", sa.Boolean(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("failure_reason", sa.String(length=300), nullable=False),
        sa.Column("downloads_at_request", sa.Integer(), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), nullable=True),
        sa.Column("completed_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('manual_review', 'pending_provider', 'processed', 'failed', 'rejected')",
            name=op.f("ck_refunds_status_valid"),
        ),
        sa.CheckConstraint("amount_minor > 0", name=op.f("ck_refunds_amount_positive")),
        sa.ForeignKeyConstraint(
            ["completed_by_id"],
            ["users.id"],
            name=op.f("fk_refunds_completed_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_refunds_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name=op.f("fk_refunds_requested_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refunds")),
        sa.UniqueConstraint("order_id", "idempotency_key", name="uq_refunds_idempotency"),
        sa.UniqueConstraint("provider", "provider_refund_id", name="uq_refunds_provider_id"),
    )
    with op.batch_alter_table("refunds", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_refunds_order_id"), ["order_id"], unique=False)

    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("provider_id", sa.String(length=100), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('charge', 'refund')", name=op.f("ck_payment_transactions_kind_valid")
        ),
        sa.CheckConstraint(
            "mode IN ('test', 'live')", name=op.f("ck_payment_transactions_mode_valid")
        ),
        sa.CheckConstraint(
            "amount_minor >= 0", name=op.f("ck_payment_transactions_amount_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["payment_attempts.id"],
            name=op.f("fk_payment_transactions_attempt_id_payment_attempts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_payment_transactions_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_transactions")),
        sa.UniqueConstraint("provider", "kind", "provider_id", name="uq_payment_transactions_id"),
    )
    with op.batch_alter_table("payment_transactions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_payment_transactions_order_id"), ["order_id"], unique=False
        )

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("published_slug", sa.String(length=200), nullable=True),
        sa.Column("product_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subtitle", sa.String(length=240), nullable=False),
        sa.Column("short_description", sa.String(length=400), nullable=False),
        sa.Column(
            "description",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "benefits",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "included",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "faq",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("audience", sa.String(length=600), nullable=False),
        sa.Column("format_label", sa.String(length=80), nullable=False),
        sa.Column("language", sa.String(length=35), nullable=False),
        sa.Column("edition", sa.String(length=60), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("sample_text", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("cover_media_id", sa.Integer(), nullable=True),
        sa.Column("cover_theme", sa.String(length=20), nullable=False),
        sa.Column(
            "gallery",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("social_image_id", sa.Integer(), nullable=True),
        sa.Column("seo_title", sa.String(length=200), nullable=True),
        sa.Column("meta_description", sa.String(length=320), nullable=True),
        sa.Column("noindex", sa.Boolean(), nullable=False),
        sa.Column("tax_category", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("sales_status", sa.String(length=20), nullable=False),
        sa.Column("pricing_model", sa.String(length=10), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False),
        sa.Column("featured_order", sa.Integer(), nullable=False),
        sa.Column("available_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "published_snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "pricing_model IN ('paid', 'free')", name=op.f("ck_products_pricing_model_valid")
        ),
        sa.CheckConstraint(
            "sales_status IN ('coming_soon', 'on_sale')",
            name=op.f("ck_products_sales_status_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')", name=op.f("ck_products_status_valid")
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count > 0", name=op.f("ck_products_page_count_positive")
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["authors.id"],
            name=op.f("fk_products_author_id_authors"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cover_media_id"],
            ["media_assets.id"],
            name=op.f("fk_products_cover_media_id_media_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_products_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["social_image_id"],
            ["media_assets.id"],
            name=op.f("fk_products_social_image_id_media_assets"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_products_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("public_id", name=op.f("uq_products_public_id")),
        sa.UniqueConstraint("published_slug", name=op.f("uq_products_published_slug")),
        sa.UniqueConstraint("slug", name=op.f("uq_products_slug")),
    )
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_products_author_id"), ["author_id"], unique=False)
        batch_op.create_index(
            "ix_products_status_featured", ["status", "is_featured"], unique=False
        )

    op.create_table(
        "bundle_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bundle_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("bundle_id <> product_id", name=op.f("ck_bundle_items_not_self")),
        sa.ForeignKeyConstraint(
            ["bundle_id"],
            ["products.id"],
            name=op.f("fk_bundle_items_bundle_id_products"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_bundle_items_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bundle_items")),
        sa.UniqueConstraint("bundle_id", "product_id", name="uq_bundle_items_pair"),
    )
    with op.batch_alter_table("bundle_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_bundle_items_product_id"), ["product_id"], unique=False
        )

    op.create_table(
        "product_category_links",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["product_categories.id"],
            name=op.f("fk_product_category_links_category_id_product_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_category_links_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "product_id", "category_id", name=op.f("pk_product_category_links")
        ),
    )
    with op.batch_alter_table("product_category_links", schema=None) as batch_op:
        batch_op.create_index(
            "ix_product_category_links_category_id", ["category_id"], unique=False
        )

    op.create_table(
        "product_collection_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["product_collections.id"],
            name=op.f("fk_product_collection_items_collection_id_product_collections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_collection_items_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_collection_items")),
        sa.UniqueConstraint("collection_id", "product_id", name="uq_product_collection_items_pair"),
    )
    with op.batch_alter_table("product_collection_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_product_collection_items_product_id"), ["product_id"], unique=False
        )

    op.create_table(
        "product_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=600), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')", name=op.f("ck_product_files_status_valid")
        ),
        *_current_version_fk(),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_files_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_files")),
        sa.UniqueConstraint("public_id", name=op.f("uq_product_files_public_id")),
    )
    with op.batch_alter_table("product_files", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_product_files_product_id"), ["product_id"], unique=False
        )

    op.create_table(
        "product_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("compare_at_minor", sa.BigInteger(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("approved_by_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('regular', 'promotional')", name=op.f("ck_product_prices_kind_valid")
        ),
        sa.CheckConstraint("amount_minor >= 0", name=op.f("ck_product_prices_amount_non_negative")),
        sa.CheckConstraint(
            "compare_at_minor IS NULL OR compare_at_minor > amount_minor",
            name=op.f("ck_product_prices_compare_at_greater"),
        ),
        sa.CheckConstraint("length(currency) = 3", name=op.f("ck_product_prices_currency_code")),
        sa.ForeignKeyConstraint(
            ["approved_by_id"],
            ["users.id"],
            name=op.f("fk_product_prices_approved_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_prices_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_prices")),
        sa.UniqueConstraint("product_id", "currency", "kind", name="uq_product_prices_kind"),
    )
    with op.batch_alter_table("product_prices", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_product_prices_product_id"), ["product_id"], unique=False
        )

    op.create_table(
        "product_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column(
            "snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('draft', 'publish', 'restore', 'system')",
            name=op.f("ck_product_revisions_kind_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_product_revisions_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_revisions_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_revisions")),
        sa.UniqueConstraint("product_id", "number", name="uq_product_revisions_number"),
    )
    with op.batch_alter_table("product_revisions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_product_revisions_product_id"), ["product_id"], unique=False
        )

    op.create_table(
        "product_tags",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_tags_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], name=op.f("fk_product_tags_tag_id_tags"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("product_id", "tag_id", name=op.f("pk_product_tags")),
    )
    with op.batch_alter_table("product_tags", schema=None) as batch_op:
        batch_op.create_index("ix_product_tags_tag_id", ["tag_id"], unique=False)

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_public_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("product_type", sa.String(length=40), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("unit_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("compare_at_minor", sa.BigInteger(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total_minor", sa.BigInteger(), nullable=False),
        sa.Column("price_id", sa.Integer(), nullable=True),
        sa.Column(
            "bundle_contents",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity = 1", name=op.f("ck_order_items_single_licence")),
        sa.CheckConstraint(
            "unit_amount_minor >= 0", name=op.f("ck_order_items_amount_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_order_items_order_id_orders"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["price_id"],
            ["product_prices.id"],
            name=op.f("fk_order_items_price_id_product_prices"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_order_items_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_items")),
        sa.UniqueConstraint("order_id", "product_id", name="uq_order_items_product"),
    )
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_order_items_order_id"), ["order_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_order_items_product_id"), ["product_id"], unique=False)

    op.create_table(
        "product_file_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_format", sa.String(length=20), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("scan_status", sa.String(length=20), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(length=300), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scan_status IN ('not_configured', 'pending', 'clean', 'infected', 'error')",
            name=op.f("ck_product_file_versions_scan_status_valid"),
        ),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_product_file_versions_size_positive")),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["product_files.id"],
            name=op.f("fk_product_file_versions_file_id_product_files"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["users.id"],
            name=op.f("fk_product_file_versions_uploaded_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_file_versions")),
        sa.UniqueConstraint("file_id", "version", name="uq_product_file_versions_number"),
        sa.UniqueConstraint("storage_key", name=op.f("uq_product_file_versions_storage_key")),
    )
    with op.batch_alter_table("product_file_versions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_product_file_versions_file_id"), ["file_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_product_file_versions_sha256"), ["sha256"], unique=False
        )

    if not _is_sqlite():
        op.create_foreign_key(
            op.f("fk_product_files_current_version_id_product_file_versions"),
            "product_files",
            "product_file_versions",
            ["current_version_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "entitlements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("grant_key", sa.String(length=120), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("order_item_id", sa.Integer(), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "purchased_versions",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("download_count", sa.Integer(), nullable=False),
        sa.Column("download_limit", sa.Integer(), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("granted_by_id", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=300), nullable=False),
        sa.CheckConstraint(
            "source IN ('purchase', 'bundle', 'free', 'manual')",
            name=op.f("ck_entitlements_source_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')", name=op.f("ck_entitlements_status_valid")
        ),
        sa.CheckConstraint(
            "download_limit IS NULL OR download_limit > 0",
            name=op.f("ck_entitlements_download_limit_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_entitlements_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_id"],
            ["users.id"],
            name=op.f("fk_entitlements_granted_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_entitlements_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id"],
            ["order_items.id"],
            name=op.f("fk_entitlements_order_item_id_order_items"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["entitlements.id"],
            name=op.f("fk_entitlements_parent_id_entitlements"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_entitlements_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entitlements")),
        sa.UniqueConstraint("grant_key", name=op.f("uq_entitlements_grant_key")),
    )
    with op.batch_alter_table("entitlements", schema=None) as batch_op:
        batch_op.create_index(
            "ix_entitlements_customer_status", ["customer_id", "status"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_entitlements_order_id"), ["order_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_entitlements_product_id"), ["product_id"], unique=False
        )

    op.create_table(
        "download_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("entitlement_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("file_version_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_download_grants_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entitlement_id"],
            ["entitlements.id"],
            name=op.f("fk_download_grants_entitlement_id_entitlements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_version_id"],
            ["product_file_versions.id"],
            name=op.f("fk_download_grants_file_version_id_product_file_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_download_grants")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_download_grants_token_hash")),
    )
    with op.batch_alter_table("download_grants", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_download_grants_entitlement_id"), ["entitlement_id"], unique=False
        )

    op.create_table(
        "entitlement_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entitlement_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_entitlement_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["entitlement_id"],
            ["entitlements.id"],
            name=op.f("fk_entitlement_events_entitlement_id_entitlements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entitlement_events")),
    )
    with op.batch_alter_table("entitlement_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_entitlement_events_entitlement_id"), ["entitlement_id"], unique=False
        )

    op.create_table(
        "download_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("entitlement_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("file_version_id", sa.Integer(), nullable=True),
        sa.Column("grant_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('authorized', 'served', 'denied')",
            name=op.f("ck_download_events_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_download_events_customer_id_customers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["entitlement_id"],
            ["entitlements.id"],
            name=op.f("fk_download_events_entitlement_id_entitlements"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["file_version_id"],
            ["product_file_versions.id"],
            name=op.f("fk_download_events_file_version_id_product_file_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["grant_id"],
            ["download_grants.id"],
            name=op.f("fk_download_events_grant_id_download_grants"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_download_events_product_id_products"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_download_events")),
    )
    with op.batch_alter_table("download_events", schema=None) as batch_op:
        batch_op.create_index("ix_download_events_created_at", ["created_at"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_download_events_customer_id"), ["customer_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_download_events_entitlement_id"), ["entitlement_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_download_events_product_id"), ["product_id"], unique=False
        )

    _sync_permissions()
    _seed_catalogue()


def downgrade():
    bind = op.get_bind()
    permissions = _permissions_table()
    gone = NEW_KEYS + NOW_AVAILABLE
    ids = [
        r[0] for r in bind.execute(sa.select(permissions.c.id).where(permissions.c.key.in_(gone)))
    ]
    if ids:
        bind.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": ids},
        )
    bind.execute(permissions.delete().where(permissions.c.key.in_(NEW_KEYS)))
    bind.execute(
        permissions.update().where(permissions.c.key.in_(NOW_AVAILABLE)).values(is_available=False)
    )
    if not _is_sqlite():
        op.drop_constraint(
            op.f("fk_product_files_current_version_id_product_file_versions"),
            "product_files",
            type_="foreignkey",
        )
    with op.batch_alter_table("download_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_download_events_product_id"))
        batch_op.drop_index(batch_op.f("ix_download_events_entitlement_id"))
        batch_op.drop_index(batch_op.f("ix_download_events_customer_id"))
        batch_op.drop_index("ix_download_events_created_at")

    op.drop_table("download_events")
    with op.batch_alter_table("entitlement_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_entitlement_events_entitlement_id"))

    op.drop_table("entitlement_events")
    with op.batch_alter_table("download_grants", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_download_grants_entitlement_id"))

    op.drop_table("download_grants")
    with op.batch_alter_table("entitlements", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_entitlements_product_id"))
        batch_op.drop_index(batch_op.f("ix_entitlements_order_id"))
        batch_op.drop_index("ix_entitlements_customer_status")

    op.drop_table("entitlements")
    with op.batch_alter_table("product_file_versions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_product_file_versions_sha256"))
        batch_op.drop_index(batch_op.f("ix_product_file_versions_file_id"))

    op.drop_table("product_file_versions")
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_order_items_product_id"))
        batch_op.drop_index(batch_op.f("ix_order_items_order_id"))

    op.drop_table("order_items")
    with op.batch_alter_table("product_tags", schema=None) as batch_op:
        batch_op.drop_index("ix_product_tags_tag_id")

    op.drop_table("product_tags")
    with op.batch_alter_table("product_revisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_product_revisions_product_id"))

    op.drop_table("product_revisions")
    with op.batch_alter_table("product_prices", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_product_prices_product_id"))

    op.drop_table("product_prices")
    with op.batch_alter_table("product_files", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_product_files_product_id"))

    op.drop_table("product_files")
    with op.batch_alter_table("product_collection_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_product_collection_items_product_id"))

    op.drop_table("product_collection_items")
    with op.batch_alter_table("product_category_links", schema=None) as batch_op:
        batch_op.drop_index("ix_product_category_links_category_id")

    op.drop_table("product_category_links")
    with op.batch_alter_table("bundle_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_bundle_items_product_id"))

    op.drop_table("bundle_items")
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_index("ix_products_status_featured")
        batch_op.drop_index(batch_op.f("ix_products_author_id"))

    op.drop_table("products")
    with op.batch_alter_table("payment_transactions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_payment_transactions_order_id"))

    op.drop_table("payment_transactions")
    with op.batch_alter_table("refunds", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_refunds_order_id"))

    op.drop_table("refunds")
    op.drop_table("receipts")
    op.drop_table("product_collections")
    with op.batch_alter_table("payment_events", schema=None) as batch_op:
        batch_op.drop_index("ix_payment_events_reference")
        batch_op.drop_index(batch_op.f("ix_payment_events_order_id"))

    op.drop_table("payment_events")
    with op.batch_alter_table("payment_attempts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_payment_attempts_order_id"))

    op.drop_table("payment_attempts")
    with op.batch_alter_table("email_deliveries", schema=None) as batch_op:
        batch_op.drop_index("ix_email_deliveries_order")
        batch_op.drop_index(batch_op.f("ix_email_deliveries_customer_id"))

    op.drop_table("email_deliveries")
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_index("ix_orders_status_created")
        batch_op.drop_index(batch_op.f("ix_orders_customer_id"))

    op.drop_table("orders")
    with op.batch_alter_table("customer_tokens", schema=None) as batch_op:
        batch_op.drop_index("ix_customer_tokens_customer_purpose")

    op.drop_table("customer_tokens")
    with op.batch_alter_table("customer_sessions", schema=None) as batch_op:
        batch_op.drop_index("ix_customer_sessions_customer_active")

    op.drop_table("customer_sessions")
    op.drop_table("product_categories")
    op.drop_table("customers")
