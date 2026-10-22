"""Run the real Alembic migrations against a fresh SQLite file."""

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from sqlalchemy import event, inspect, text

from app import create_app
from app.auth.permissions import ROLE_SPECS, TEMPLATE_ROLES
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
        return fk is not None and [c.name for c in fk.columns] == ["approved_by_id"]

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
        upgrade(directory=MIGRATIONS)
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
        assert effective_permissions(editor) == set(
            ROLE_SPECS["editor"].permissions | ROLE_SPECS["analyst"].permissions
        )
        invite = db.session.scalar(db.select(AccountToken))
        assert invite.roles == ["editor"] and invite.used_at is None
        assert set(sync_rbac().values()) == {0}
        db.session.rollback()
        db.session.remove()

        downgrade(directory=MIGRATIONS, revision="5e0cca7bc654")
        assert db.session.execute(text("SELECT COUNT(*) FROM users")).scalar_one() == 3
        assert db.session.execute(text("SELECT COUNT(*) FROM user_roles")).scalar_one() == 4
        assert db.session.execute(text("SELECT COUNT(*) FROM account_tokens")).scalar_one() == 1
        assert {r[0] for r in db.session.execute(text("SELECT name FROM roles"))} == set(role_ids)
