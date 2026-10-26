"""Run the real Alembic migrations against a fresh SQLite file."""

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from sqlalchemy import event, inspect, text
from sqlalchemy.orm import configure_mappers, raiseload

from app import create_app
from app.auth.permissions import TEMPLATE_ROLES
from app.auth.rbac import effective_permissions, sync_rbac
from app.extensions import db

MIGRATIONS = str(Path(__file__).resolve().parents[1] / "migrations")


def _real_drift(diff):
    """Ignore one SQLite reflection gap: a foreign key added with ALTER TABLE ... ADD
    COLUMN ... REFERENCES is enforced (checked via PRAGMA below), but SQLAlchemy
    cannot reflect its name or ON DELETE option, so Alembic reports it as changed."""

    def known(op):
        kind = op[0]
        fk = op[1] if kind in ("add_fk", "remove_fk") else None
        return fk is not None and [c.name for c in fk.columns] in (
            ["approved_by_id"],
            ["pending_by_id"],
            ["reusable_section_id"],
            ["parent_id"],
            ["social_image_id"],
            ["published_by_id"],
            ["updated_by_id"],
        )

    return [op for op in diff if not known(op)]


def _app(tmp_path, name):
    url = f"sqlite:///{tmp_path / name}"
    return create_app("testing", {"SQLALCHEMY_DATABASE_URI": url, "SQLALCHEMY_ENGINE_OPTIONS": {}})


def test_upgrade_downgrade_and_no_model_drift(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrations.db'}"
    app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": url, "SQLALCHEMY_ENGINE_OPTIONS": {}})
    with app.app_context():
        upgrade(directory=MIGRATIONS)
        tables = set(inspect(db.engine).get_table_names())
        assert {
            "users",
            "roles",
            "user_roles",
            "articles",
            "topics",
            "tags",
            "authors",
            "media_assets",
            "site_settings",
            "navigation_menus",
            "navigation_items",
            "pages",
            "page_sections",
            "audit_logs",
            "refresh_tokens",
        } <= tables
        kinds = dict(db.session.execute(text("SELECT name, kind FROM roles")).all())
        assert {k for k, v in kinds.items() if v == "system"} == {
            "super_admin",
            "editor",
            "moderator",
            "analyst",
        }
        assert {k for k, v in kinds.items() if v == "template"} == {r.key for r in TEMPLATE_ROLES}

        with db.engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), db.metadata)
        assert _real_drift(diff) == [], f"Models and migrations differ: {diff}"
        fks = db.session.execute(text("PRAGMA foreign_key_list(articles)")).all()
        assert any(r[3] == "approved_by_id" and r[2] == "users" and r[6] == "SET NULL" for r in fks)
        # The migration's frozen snapshot matches the code catalogue exactly.
        assert set(sync_rbac().values()) == {0}
        db.session.rollback()

        db.session.remove()
        downgrade(directory=MIGRATIONS, revision="base")
        assert set(inspect(db.engine).get_table_names()) <= {"alembic_version"}


def test_app_startup_does_not_create_tables(tmp_path):
    url = f"sqlite:///{tmp_path / 'empty.db'}"
    app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": url, "SQLALCHEMY_ENGINE_OPTIONS": {}})
    with app.app_context():
        assert inspect(db.engine).get_table_names() == []


def test_rbac_upgrade_preserves_users_roles_and_invitations(tmp_path):
    app = _app(tmp_path, "upgrade.db")
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="5e0cca7bc654")
        conn = db.session
        role_ids = dict(conn.execute(text("SELECT name, id FROM roles")).all())
        if not role_ids:  # the previous release created the four roles at first use
            for name in ("super_admin", "editor", "moderator", "analyst"):
                conn.execute(
                    text("INSERT INTO roles (name, description) VALUES (:n, '')"), {"n": name}
                )
            role_ids = dict(conn.execute(text("SELECT name, id FROM roles")).all())
        now = "2026-10-01 10:00:00"
        users = {
            "owner@example.org": ["super_admin"],
            "ed@example.org": ["editor", "analyst"],
            "mod@example.org": ["moderator"],
        }
        for email, roles in users.items():
            uid = conn.execute(
                text(
                    "INSERT INTO users (email, display_name, password_hash, status, "
                    "session_version, created_at, updated_at) "
                    "VALUES (:e, :e, 'x', 'active', 1, :now, :now) RETURNING id"
                ),
                {"e": email, "now": now},
            ).scalar_one()
            for role in roles:
                conn.execute(
                    text(
                        "INSERT INTO user_roles (user_id, role_id, assigned_at) "
                        "VALUES (:u, :r, :now)"
                    ),
                    {"u": uid, "r": role_ids[role], "now": now},
                )
        conn.execute(
            text(
                "INSERT INTO account_tokens (purpose, token_hash, email, roles, created_at, "
                "expires_at, delivery) VALUES ('invitation', :h, 'new@example.org', "
                "'[\"editor\"]', :now, '2099-01-01 00:00:00', 'memory')"
            ),
            {"h": "a" * 64, "now": now},
        )
        conn.commit()
        conn.remove()

        statements = []

        def capture(_conn, _cursor, statement, *_args):
            statements.append(statement.upper())

        event.listen(db.engine, "before_cursor_execute", capture)
        upgrade(directory=MIGRATIONS, revision="7cf88d33a308")
        event.remove(db.engine, "before_cursor_execute", capture)
        # Incremental: nothing is dropped, renamed or rebuilt.
        assert not [s for s in statements if "DROP TABLE" in s or "_ALEMBIC_TMP" in s]
        assert not [s for s in statements if "CREATE TABLE" in s and "PERMISSIONS" not in s]

        from app.models import AccountToken, Role, User

        assert (
            dict(db.session.execute(text("SELECT name, id FROM roles WHERE kind = 'system'")).all())
            == role_ids
        )
        for email, roles in users.items():
            user = db.session.scalar(db.select(User).where(User.email == email))
            assert user.role_names == sorted(roles)
        owner = db.session.scalar(db.select(User).where(User.email == "owner@example.org"))
        editor = db.session.scalar(db.select(User).where(User.email == "ed@example.org"))
        assert db.session.scalar(db.select(Role).where(Role.name == "super_admin")).grants_all
        assert "roles.manage" in effective_permissions(owner)
        # Specs include later additions (Batch 03); at this revision only the original set exists.
        assert {"articles.edit_any", "analytics.view", "articles.publish"} <= effective_permissions(
            editor
        )
        invite = db.session.scalar(db.select(AccountToken))
        assert invite.roles == ["editor"] and invite.used_at is None
        db.session.rollback()
        db.session.remove()

        downgrade(directory=MIGRATIONS, revision="5e0cca7bc654")
        assert db.session.execute(text("SELECT COUNT(*) FROM users")).scalar_one() == 3
        assert db.session.execute(text("SELECT COUNT(*) FROM user_roles")).scalar_one() == 4
        assert db.session.execute(text("SELECT COUNT(*) FROM account_tokens")).scalar_one() == 1
        assert {r[0] for r in db.session.execute(text("SELECT name FROM roles"))} == set(role_ids)


def test_batch03_upgrade_preserves_content_and_adds_permissions(tmp_path):
    """7cf88d33a308 -> a817c9636960: existing data survives, tables are only extended."""
    app = _app(tmp_path, "batch03.db")
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="7cf88d33a308")
        conn = db.session
        now = "2026-10-01 10:00:00"
        uid = conn.execute(
            text(
                "INSERT INTO users (email, display_name, password_hash, status, session_version, "
                "created_at, updated_at) VALUES ('w@example.org', 'W', 'x', 'active', 1, :n, :n) "
                "RETURNING id"
            ),
            {"n": now},
        ).scalar_one()
        writer_role = conn.execute(
            text("SELECT id FROM roles WHERE name = 'content_writer'")
        ).scalar_one()
        conn.execute(
            text("INSERT INTO user_roles (user_id, role_id, assigned_at) VALUES (:u, :r, :n)"),
            {"u": uid, "r": writer_role, "n": now},
        )
        media_id = conn.execute(
            text(
                "INSERT INTO media_assets (filename, mime_type, storage_key, size_bytes, alt_text, "
                "width, height, visibility, created_at) VALUES ('calm.svg', 'image/svg+xml', "
                "'/images/articles/calm.svg', 0, 'Calm', 1600, 1000, 'public', :n) RETURNING id"
            ),
            {"n": now},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO articles (title, slug, excerpt, body, status, featured, noindex, "
                "source, created_at, updated_at, featured_image_id, review_status) VALUES "
                "('Kept', 'kept', 'e', '[]', 'draft', 0, 0, 'original', :n, :n, :m, 'none')"
            ),
            {"n": now, "m": media_id},
        )
        conn.execute(
            text(
                "INSERT INTO site_settings (key, value, updated_at) VALUES "
                "('site.name', '\"TPA\"', :n)"
            ),
            {"n": now},
        )
        conn.commit()
        conn.remove()

        statements = []

        def capture(_conn, _cursor, statement, *_args):
            statements.append(statement.upper())

        event.listen(db.engine, "before_cursor_execute", capture)
        upgrade(directory=MIGRATIONS, revision="a817c9636960")
        event.remove(db.engine, "before_cursor_execute", capture)
        assert not [s for s in statements if "DROP TABLE" in s or "_ALEMBIC_TMP" in s]
        created = {
            s.split("CREATE TABLE ")[1].split(" ")[0].strip()
            for s in statements
            if "CREATE TABLE" in s
        }
        assert created == {"PUBLISH_JOBS", "REDIRECTS", "MEDIA_VARIANTS", "ARTICLE_REVISIONS"}

        from app.models import Article, MediaAsset, User

        # The sponsorship side table (Batch 07) doesn't exist at this revision yet: never load
        # it (raiseload fails loudly instead of querying). The backref exists once mappers
        # are configured.
        configure_mappers()
        article = db.session.scalar(
            db.select(Article).where(Article.slug == "kept").options(raiseload(Article.sponsorship))
        )
        assert article.lock_version == 1 and article.pending_changes is None
        assert article.featured_image_id == media_id
        asset = db.session.get(MediaAsset, media_id)
        assert asset.status == "active" and asset.public_id is None and not asset.variants
        assert asset.as_image()["src"] == "/images/articles/calm.svg"
        writer = db.session.get(User, uid)
        perms = effective_permissions(writer)
        assert {"media.upload", "articles.view_revisions", "articles.preview"} <= perms
        assert "articles.publish" not in perms and "publishing.manage" not in perms
        assert db.session.execute(text("SELECT value FROM site_settings")).scalar_one() == '"TPA"'
        db.session.remove()
        upgrade(directory=MIGRATIONS)  # the catalogue matches the code only at head
        assert set(sync_rbac().values()) == {0}
        db.session.rollback()
        db.session.remove()

        downgrade(directory=MIGRATIONS, revision="7cf88d33a308")
        assert db.session.execute(text("SELECT COUNT(*) FROM articles")).scalar_one() == 1
        assert db.session.execute(text("SELECT COUNT(*) FROM media_assets")).scalar_one() == 1
        assert db.session.execute(text("SELECT COUNT(*) FROM user_roles")).scalar_one() == 1
        keys = set(db.session.scalars(text("SELECT key FROM permissions")))
        assert "media.edit" not in keys and "publishing.view" not in keys


def test_batch04_upgrade_converts_homepage_without_losing_edits(tmp_path):
    """a817c9636960 -> de3d968df6ce: unedited defaults become the Batch 04 homepage,
    edited text is kept, the live homepage gets its first snapshot and custom roles
    keep (only) the equivalent permissions."""
    from app.cms.defaults import HOME_SECTIONS
    from app.cms.sections import check_section

    app = _app(tmp_path, "batch04.db")
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="a817c9636960")
        conn = db.session
        now = "2026-10-01 10:00:00"
        page_id = conn.execute(
            text(
                "INSERT INTO pages (slug, title, status, noindex, content, created_at, updated_at) "
                "VALUES ('home', 'Homepage', 'published', 0, '[]', :n, :n) RETURNING id"
            ),
            {"n": now},
        ).scalar_one()
        hero_v1 = {
            "eyebrow": "Think Positive Always",
            "heading": "A Better Mindset.",
            "highlight": "A Brighter Life.",
            "body": "Practical encouragement, thoughtful resources, and tools to help you grow "
            "through every season of life.",
            "primary_cta_label": "Explore Our Resources",
            "primary_cta_url": "/free-resources",
            "secondary_cta_label": "Read Our Articles",
            "secondary_cta_url": "/articles",
        }
        edited = {
            "eyebrow": "Our mission",
            "heading": "Welcome, friend",
            "body": "Edited by the team.",
            "cta_label": "Read our story",
            "cta_url": "/about",
        }
        import json

        for order, (key, stype, variant, content) in enumerate(
            [
                ("hero", "hero", "default", hero_v1),
                ("welcome", "brand_intro", "default", edited),
                ("notes", "rich_text", "default", {"heading": "", "body": "One\n\nTwo"}),
            ]
        ):
            conn.execute(
                text(
                    "INSERT INTO page_sections (page_id, key, section_type, variant, content, "
                    "is_visible, display_order, created_at, updated_at) VALUES "
                    "(:p, :k, :t, :v, :c, 1, :o, :n, :n)"
                ),
                {
                    "p": page_id,
                    "k": key,
                    "t": stype,
                    "v": variant,
                    "c": json.dumps(content),
                    "o": order,
                    "n": now,
                },
            )
        role_id = conn.execute(
            text(
                "INSERT INTO roles (name, label, description, kind, is_active, grants_all) "
                "VALUES ('site_helper', 'Site helper', '', 'custom', 1, 0) RETURNING id"
            )
        ).scalar_one()
        for key in ("pages.view", "pages.edit", "settings.manage"):
            conn.execute(
                text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "SELECT :r, id FROM permissions WHERE key = :k"
                ),
                {"r": role_id, "k": key},
            )
        conn.commit()
        conn.remove()

        statements = []

        def capture(_conn, _cursor, statement, *_args):
            statements.append(statement.upper())

        event.listen(db.engine, "before_cursor_execute", capture)
        upgrade(directory=MIGRATIONS, revision="de3d968df6ce")
        event.remove(db.engine, "before_cursor_execute", capture)
        assert not [s for s in statements if "DROP TABLE" in s or "_ALEMBIC_TMP" in s]
        created = {
            s.split("CREATE TABLE ")[1].split(" ")[0].strip()
            for s in statements
            if "CREATE TABLE" in s
        }
        assert created == {"ANNOUNCEMENTS", "GLOBAL_CTAS", "REUSABLE_SECTIONS", "PAGE_REVISIONS"}

        from app.models import Page, PageRevision, Role

        page = db.session.get(Page, page_id)
        assert (
            page.path == page.published_path == "/" and page.is_system and page.template == "home"
        )
        by_key = {s.key: s for s in page.sections}
        assert by_key["hero"].content == HOME_SECTIONS[0]["content"]  # unedited -> Batch 04 default
        assert by_key["hero"].variant == "split" and by_key["hero"].design["background"] == "ivory"
        welcome = by_key["welcome"]
        assert welcome.content["heading"] == "Welcome, friend"  # edits are kept
        assert welcome.content["cta"] == {
            "label": "Read our story",
            "url": "/about",
            "style": "outline",
            "cta_id": None,
        }
        assert by_key["notes"].content["body"] == [
            {"type": "paragraph", "text": "One"},
            {"type": "paragraph", "text": "Two"},
        ]
        for section in page.sections:  # converted content is valid in the new editor
            _, errors, _ = check_section(
                section.section_type,
                section.variant,
                section.content,
                section.design,
                section.visibility,
            )
            assert errors == {}, (section.key, errors)
        assert page.published_snapshot["sections"][1]["content"]["heading"] == "Welcome, friend"
        assert db.session.query(PageRevision).filter_by(page_id=page_id).count() == 1
        helper = db.session.get(Role, role_id)
        granted = {p.key for p in helper.permissions}
        assert {"homepage.view", "homepage.edit", "branding.manage"} <= granted
        assert (
            not {"homepage.publish", "pages.publish", "pages.create", "settings.technical"}
            & granted
        )
        db.session.remove()
        upgrade(directory=MIGRATIONS)  # the catalogue matches the code only at head
        assert set(sync_rbac().values()) == {0}
        db.session.rollback()
        db.session.remove()

        # Downgrade restores the Batch 02 field format; upgrading again is safe.
        downgrade(directory=MIGRATIONS, revision="a817c9636960")
        row = db.session.execute(
            text("SELECT content, variant FROM page_sections WHERE key = 'welcome'")
        ).one()
        assert json.loads(row[0])["cta_label"] == "Read our story" and row[1] == "default"
        db.session.remove()
        upgrade(directory=MIGRATIONS)
        page = db.session.get(Page, page_id)
        assert {s.key: s for s in page.sections}["welcome"].content["heading"] == "Welcome, friend"


COMMERCE_TABLES = {
    "PRODUCTS",
    "PRODUCT_CATEGORIES",
    "PRODUCT_CATEGORY_LINKS",
    "PRODUCT_TAGS",
    "PRODUCT_COLLECTIONS",
    "PRODUCT_COLLECTION_ITEMS",
    "PRODUCT_PRICES",
    "PRODUCT_FILES",
    "PRODUCT_FILE_VERSIONS",
    "PRODUCT_REVISIONS",
    "BUNDLE_ITEMS",
    "CUSTOMERS",
    "CUSTOMER_SESSIONS",
    "CUSTOMER_TOKENS",
    "ORDERS",
    "ORDER_ITEMS",
    "PAYMENT_ATTEMPTS",
    "PAYMENT_TRANSACTIONS",
    "PAYMENT_EVENTS",
    "RECEIPTS",
    "REFUNDS",
    "EMAIL_DELIVERIES",
    "ENTITLEMENTS",
    "ENTITLEMENT_EVENTS",
    "DOWNLOAD_GRANTS",
    "DOWNLOAD_EVENTS",
}


def test_batch05_upgrade_preserves_data_and_grants_commerce_roles_only(tmp_path):
    app = _app(tmp_path, "batch05.db")
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="de3d968df6ce")
        conn = db.session
        now = "2026-10-20 09:00:00"
        ids = {}
        for email, role in (
            ("editor@example.org", "editor"),
            ("pm@example.org", "product_manager"),
            ("help@example.org", "customer_support"),
        ):
            uid = conn.execute(
                text(
                    "INSERT INTO users (email, display_name, password_hash, status, "
                    "session_version, created_at, updated_at) VALUES (:e, 'U', 'x', 'active', 1, "
                    ":n, :n) RETURNING id"
                ),
                {"e": email, "n": now},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO user_roles (user_id, role_id, assigned_at) "
                    "SELECT :u, id, :n FROM roles WHERE name = :r"
                ),
                {"u": uid, "r": role, "n": now},
            )
            ids[role] = uid
        role_id = conn.execute(
            text(
                "INSERT INTO roles (name, label, description, kind, is_active, grants_all) "
                "VALUES ('helper', 'Helper', '', 'custom', 1, 0) RETURNING id"
            )
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT :r, id FROM permissions WHERE key = 'pages.view'"
            ),
            {"r": role_id},
        )
        conn.execute(
            text(
                "INSERT INTO site_settings (key, value, updated_at) "
                "VALUES ('site.name', '\"TPA Test\"', :n)"
            ),
            {"n": now},
        )
        conn.commit()
        before = {
            t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one()
            for t in ("users", "roles", "user_roles", "role_permissions", "site_settings", "pages")
        }
        conn.remove()

        statements = []

        def capture(_conn, _cursor, statement, *_args):
            statements.append(statement.upper())

        event.listen(db.engine, "before_cursor_execute", capture)
        upgrade(directory=MIGRATIONS, revision="758d4c510551")
        event.remove(db.engine, "before_cursor_execute", capture)
        assert not [s for s in statements if "DROP TABLE" in s or "_ALEMBIC_TMP" in s]
        assert not [s for s in statements if s.lstrip().startswith("ALTER TABLE")]
        created = {
            s.split("CREATE TABLE ")[1].split(" ")[0].strip()
            for s in statements
            if "CREATE TABLE" in s
        }
        assert created == COMMERCE_TABLES

        after = {
            t: db.session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one() for t in before
        }
        assert {k: v for k, v in after.items() if k != "role_permissions"} == {
            k: v for k, v in before.items() if k != "role_permissions"
        }
        assert after["role_permissions"] > before["role_permissions"]

        from app.models import Product, ProductPrice, Role, User

        editor = effective_permissions(db.session.get(User, ids["editor"]))
        assert not {
            p
            for p in editor
            if p.split(".")[0]
            in (
                "products",
                "orders",
                "finance",
                "payments",
                "customers",
                "entitlements",
                "downloads",
                "refunds",
            )
        }
        pm = effective_permissions(db.session.get(User, ids["product_manager"]))
        assert {"products.manage_prices", "products.manage_files", "products.publish"} <= pm
        assert "payments.configure" not in pm and "orders.view" not in pm
        support = effective_permissions(db.session.get(User, ids["customer_support"]))
        assert {"orders.view", "customers.support"} <= support and "refunds.issue" not in support
        helper = db.session.get(Role, role_id)
        assert helper.permission_keys == {"pages.view"}  # custom roles unchanged

        products = db.session.scalars(db.select(Product).order_by(Product.id)).all()
        assert len(products) == 6
        live = [p for p in products if p.status == "published"]
        assert len(live) == 5 and all(p.sales_status == "coming_soon" for p in live)
        assert all(p.page_count is None and p.published_snapshot for p in live)
        bundle = products[-1]
        assert bundle.product_type == "bundle" and bundle.status == "draft"
        assert len(bundle.bundle_items) == 3
        assert db.session.scalar(db.select(db.func.count(ProductPrice.id))) == 0
        db.session.rollback()
        db.session.remove()
        upgrade(directory=MIGRATIONS)  # the code catalogue is ahead of this revision
        assert set(sync_rbac().values()) == {0}
        db.session.rollback()
        db.session.remove()

        downgrade(directory=MIGRATIONS, revision="de3d968df6ce")
        tables = {t.upper() for t in inspect(db.engine).get_table_names()}
        assert not tables & COMMERCE_TABLES
        assert (
            db.session.execute(text("SELECT COUNT(*) FROM users")).scalar_one() == before["users"]
        )
        available = db.session.execute(
            text("SELECT is_available FROM permissions WHERE key = 'products.view'")
        ).scalar_one()
        assert not available
        db.session.remove()
        upgrade(directory=MIGRATIONS)
        assert db.session.scalar(db.select(db.func.count(Product.id))) == 6


def test_starter_catalogue_never_overwrites_admin_products(app):
    import secrets

    from app.models import Product
    from app.services.seed_service import seed_commerce_catalogue

    with app.app_context():
        db.session.add(
            Product(
                public_id=secrets.token_hex(8),
                slug="the-power-of-starting-again",
                product_type="ebook",
                title="Our real edition",
                status="draft",
            )
        )
        db.session.commit()
        first = seed_commerce_catalogue()
        second = seed_commerce_catalogue()
        db.session.commit()
        assert first["products"] == 5 and second["products"] == 0
        mine = db.session.scalar(
            db.select(Product).where(Product.slug == "the-power-of-starting-again")
        )
        assert mine.title == "Our real edition" and mine.status == "draft"


NEWSLETTER_TABLES = {
    "SUBSCRIBERS",
    "SUBSCRIBER_TAGS",
    "SUBSCRIBER_TAG_LINKS",
    "SUBSCRIBER_EVENTS",
    "SUBSCRIBER_SEGMENTS",
    "EMAIL_SUPPRESSIONS",
    "EMAIL_TEMPLATES",
    "EMAIL_CAMPAIGNS",
    "EMAIL_MESSAGES",
    "EMAIL_AUTOMATIONS",
    "EMAIL_AUTOMATION_STEPS",
    "EMAIL_AUTOMATION_ENROLLMENTS",
    "EMAIL_AUTOMATION_EVENTS",
    "LEAD_MAGNETS",
    "LEAD_MAGNET_CLAIMS",
}


def test_batch06_upgrade_adds_newsletter_tables_only_and_preserves_data(tmp_path):
    app = _app(tmp_path, "batch06.db")
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="758d4c510551")
        conn = db.session
        now = "2026-10-23 09:00:00"
        ids = {}
        for email, role in (
            ("editor@example.org", "editor"),
            ("news@example.org", "newsletter_manager"),
            ("mkt@example.org", "marketing_manager"),
        ):
            uid = conn.execute(
                text(
                    "INSERT INTO users (email, display_name, password_hash, status, "
                    "session_version, created_at, updated_at) VALUES (:e, 'U', 'x', 'active', 1, "
                    ":n, :n) RETURNING id"
                ),
                {"e": email, "n": now},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO user_roles (user_id, role_id, assigned_at) "
                    "SELECT :u, id, :n FROM roles WHERE name = :r"
                ),
                {"u": uid, "r": role, "n": now},
            )
            ids[role] = uid
        conn.execute(
            text(
                "INSERT INTO customers (public_id, email, display_name, status, "
                "is_test_account, support_notes, created_at, updated_at) "
                "VALUES ('c1', 'buyer@example.com', 'B', 'active', 0, '', :n, :n)"
            ),
            {"n": now},
        )
        conn.commit()
        tables = ("users", "roles", "user_roles", "customers", "products", "site_settings", "pages")
        before = {t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one() for t in tables}
        conn.remove()

        statements = []

        def capture(_conn, _cursor, statement, *_args):
            statements.append(statement.upper())

        event.listen(db.engine, "before_cursor_execute", capture)
        upgrade(directory=MIGRATIONS, revision="0ded798b0061")
        event.remove(db.engine, "before_cursor_execute", capture)
        assert not [s for s in statements if "DROP TABLE" in s or "_ALEMBIC_TMP" in s]
        assert not [s for s in statements if s.lstrip().startswith("ALTER TABLE")]
        created = {
            s.split("CREATE TABLE ")[1].split(" ")[0].strip()
            for s in statements
            if "CREATE TABLE" in s
        }
        assert created == NEWSLETTER_TABLES
        after = {
            t: db.session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one() for t in before
        }
        assert after == before
        # Customers are never turned into subscribers.
        assert db.session.execute(text("SELECT COUNT(*) FROM subscribers")).scalar_one() == 0

        from app.models import User

        editor = effective_permissions(db.session.get(User, ids["editor"]))
        assert not {p for p in editor if p.split(".")[0] in ("newsletters", "subscribers")}
        news = effective_permissions(db.session.get(User, ids["newsletter_manager"]))
        assert {"newsletters.send", "subscribers.export", "lead_magnets.manage"} <= news
        assert "email_settings.manage" not in news
        mkt = effective_permissions(db.session.get(User, ids["marketing_manager"]))
        assert "newsletters.edit" in mkt and "newsletters.send" not in mkt
        db.session.rollback()
        db.session.remove()

        downgrade(directory=MIGRATIONS, revision="758d4c510551")
        names = {t.upper() for t in inspect(db.engine).get_table_names()}
        assert not names & NEWSLETTER_TABLES
        available = db.session.execute(
            text("SELECT is_available FROM permissions WHERE key = 'subscribers.view'")
        ).scalar_one()
        assert not available
        db.session.remove()
        upgrade(directory=MIGRATIONS)  # the code catalogue is ahead of this revision
        assert set(sync_rbac().values()) == {0}
        db.session.rollback()


PARTNERSHIP_TABLES = {
    "AD_PLACEMENTS",
    "AFFILIATE_PROGRAMS",
    "AUDIENCE_METRICS",
    "COMMERCIAL_EVENTS",
    "RATE_CARDS",
    "PARTNERS",
    "PARTNER_CONTACTS",
    "PARTNERSHIP_OPPORTUNITIES",
    "AFFILIATE_LINKS",
    "PARTNERSHIP_INQUIRIES",
    "SPONSORSHIP_CAMPAIGNS",
    "AD_BOOKINGS",
    "AFFILIATE_CLICK_DAILY",
    "AFFILIATE_COMMISSIONS",
    "ARTICLE_SPONSORSHIPS",
    "NEWSLETTER_SPONSORSHIPS",
    "PARTNERSHIP_FINANCE_ENTRIES",
}


def test_batch07_upgrade_adds_partnership_tables_only_and_preserves_data(tmp_path):
    app = _app(tmp_path, "batch07.db")
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="0ded798b0061")
        conn = db.session
        now = "2026-10-26 09:00:00"
        ids = {}
        for email, role in (
            ("writer@example.org", "content_writer"),
            ("pm@example.org", "partnerships_manager"),
            ("fin@example.org", "finance_manager"),
        ):
            uid = conn.execute(
                text(
                    "INSERT INTO users (email, display_name, password_hash, status, "
                    "session_version, created_at, updated_at) VALUES (:e, 'U', 'x', 'active', 1, "
                    ":n, :n) RETURNING id"
                ),
                {"e": email, "n": now},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO user_roles (user_id, role_id, assigned_at) "
                    "SELECT :u, id, :n FROM roles WHERE name = :r"
                ),
                {"u": uid, "r": role, "n": now},
            )
            ids[role] = uid
        conn.commit()
        tables = ("users", "roles", "user_roles", "site_settings", "pages", "email_campaigns")
        before = {t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one() for t in tables}
        conn.remove()

        statements = []

        def capture(_conn, _cursor, statement, *_args):
            statements.append(statement.upper())

        event.listen(db.engine, "before_cursor_execute", capture)
        upgrade(directory=MIGRATIONS, revision="4a65b8174c82")
        event.remove(db.engine, "before_cursor_execute", capture)
        assert not [s for s in statements if "DROP TABLE" in s or "_ALEMBIC_TMP" in s]
        assert not [s for s in statements if s.lstrip().startswith("ALTER TABLE")]
        created = {
            s.split("CREATE TABLE ")[1].split(" ")[0].strip()
            for s in statements
            if "CREATE TABLE" in s
        }
        assert created == PARTNERSHIP_TABLES
        after = {
            t: db.session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one() for t in before
        }
        assert after == before

        from app.models import User

        writer = effective_permissions(db.session.get(User, ids["content_writer"]))
        commercial = ("partnerships", "sponsorships", "advertising", "affiliates", "media_kit")
        assert not {p for p in writer if p.split(".")[0] in commercial or "partnership" in p}
        pm = effective_permissions(db.session.get(User, ids["partnerships_manager"]))
        assert {"partnerships.manage", "advertising.manage_bookings"} <= pm
        assert "partnership_finance.manage" not in pm
        fin = effective_permissions(db.session.get(User, ids["finance_manager"]))
        assert {"partnership_finance.manage", "partnership_reports.export"} <= fin
        assert set(sync_rbac().values()) == {0}
        db.session.rollback()
        db.session.remove()

        downgrade(directory=MIGRATIONS, revision="0ded798b0061")
        names = {t.upper() for t in inspect(db.engine).get_table_names()}
        assert not names & PARTNERSHIP_TABLES
        db.session.remove()
        upgrade(directory=MIGRATIONS)


def test_batch076_guest_checkout_upgrade_preserves_orders_and_downgrades_safely(tmp_path):
    import pytest

    app = _app(tmp_path, "batch076.db")
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision="4a65b8174c82")
        conn = db.session
        now = "2026-10-26 09:00:00"
        cid = conn.execute(
            text(
                "INSERT INTO customers (public_id, email, display_name, password_hash, status, "
                "is_test_account, support_notes, created_at, updated_at) VALUES "
                "('c1', 'reader@example.com', 'Reader', 'x', 'active', 0, '', :n, :n) "
                "RETURNING id"
            ),
            {"n": now},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO orders (number, public_id, customer_id, email, status, currency, "
                "subtotal_minor, discount_minor, tax_minor, total_minor, refunded_minor, provider, "
                "mode, idempotency_key, cart_hash, terms_version, needs_review, review_reason, "
                "notes, created_at, updated_at) VALUES ('TPA-1', 'o1', :c, 'reader@example.com', "
                "'paid', 'USD', 1500, 0, 0, 1500, 0, 'paystack', 'test', 'k1', 'h1', 'v1', 0, '', "
                "'', :n, :n)"
            ),
            {"c": cid, "n": now},
        )
        conn.execute(
            text(
                "INSERT INTO customer_tokens (customer_id, purpose, token_hash, expires_at, "
                "created_at) VALUES (:c, 'verify_email', 'h', :n, :n)"
            ),
            {"c": cid, "n": now},
        )
        conn.execute(
            text(
                "INSERT INTO customer_sessions (customer_id, token_hash, csrf_hash, created_at, "
                "last_seen_at, expires_at, user_agent) VALUES (:c, 's', 'c', :n, :n, :n, '')"
            ),
            {"c": cid, "n": now},
        )
        conn.commit()
        # customer_sessions/customer_tokens cascade on delete: a careless rebuild of
        # "customers" would silently empty them.
        counts = ("customers", "orders", "customer_tokens", "customer_sessions")
        before = {t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one() for t in counts}
        conn.remove()

        upgrade(directory=MIGRATIONS, revision="a136d95dd67c")
        after = {
            t: db.session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one() for t in counts
        }
        assert after == before
        assert db.session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert db.session.execute(text("PRAGMA foreign_key_check")).fetchall() == []
        row = db.session.execute(
            text("SELECT number, status, is_guest, guest_token_hash FROM orders")
        ).one()
        assert tuple(row) == ("TPA-1", "paid", 0, None)  # existing orders are account orders
        db.session.execute(
            text(
                "INSERT INTO customers (public_id, email, display_name, status, is_test_account, "
                "support_notes, created_at, updated_at) VALUES ('g1', 'guest@example.com', '', "
                "'guest', 0, '', :n, :n)"
            ),
            {"n": now},
        )
        db.session.commit()
        db.session.remove()
        # Guest buyer records would violate the old constraint: the downgrade refuses.
        with pytest.raises(SystemExit):  # Flask-Migrate reports the RuntimeError and exits
            downgrade(directory=MIGRATIONS, revision="4a65b8174c82")
        db.session.remove()
        assert db.session.execute(text("SELECT COUNT(*) FROM customers")).scalar_one() == 2
        db.session.execute(text("DELETE FROM customers WHERE status = 'guest'"))
        db.session.commit()
        db.session.remove()
        downgrade(directory=MIGRATIONS, revision="4a65b8174c82")
        columns = {c["name"] for c in inspect(db.engine).get_columns("orders")}
        assert "is_guest" not in columns and "guest_token_hash" not in columns
        assert db.session.execute(text("SELECT number FROM orders")).scalar_one() == "TPA-1"
        db.session.remove()
        upgrade(directory=MIGRATIONS)
