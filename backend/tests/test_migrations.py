"""Run the real Alembic migrations against a fresh SQLite file."""

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from sqlalchemy import event, inspect, text

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

        article = db.session.scalar(db.select(Article).where(Article.slug == "kept"))
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
