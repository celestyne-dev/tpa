"""Run the real Alembic migrations against a fresh SQLite file."""

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db

MIGRATIONS = str(Path(__file__).resolve().parents[1] / "migrations")


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
        roles = {r[0] for r in db.session.execute(text("SELECT name FROM roles"))}
        assert roles == {"super_admin", "editor", "moderator", "analyst"}

        with db.engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), db.metadata)
        assert diff == [], f"Models and migrations differ: {diff}"

        db.session.remove()
        downgrade(directory=MIGRATIONS, revision="base")
        assert set(inspect(db.engine).get_table_names()) <= {"alembic_version"}


def test_app_startup_does_not_create_tables(tmp_path):
    url = f"sqlite:///{tmp_path / 'empty.db'}"
    app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": url, "SQLALCHEMY_ENGINE_OPTIONS": {}})
    with app.app_context():
        assert inspect(db.engine).get_table_names() == []
