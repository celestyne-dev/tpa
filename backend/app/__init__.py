"""Think Positive Always API — application factory."""

from __future__ import annotations

import logging

from flask import Flask
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .config import INSTANCE_DIR, get_config
from .extensions import cors, db, jwt, limiter, migrate
from .utils.errors import register_error_handlers


@event.listens_for(Engine, "connect")
def _sqlite_foreign_keys(dbapi_connection, _record):
    # Enforce foreign keys on SQLite (PostgreSQL always does).
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    config = get_config(config_name)
    if hasattr(config, "validate"):
        config.validate()

    app = Flask(__name__, instance_path=str(INSTANCE_DIR))
    app.config.from_object(config)
    if overrides:
        app.config.update(overrides)
    app.json.sort_keys = False
    app.config["ENV_NAME"] = config.__name__.removesuffix("Config").lower()
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

    if app.config.get("TRUST_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # No db.create_all() here: the schema is managed only by explicit migrations.
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)
    # Public API only, approved origins only, no credentials. The admin API is
    # served same-origin (Vite proxy / Nginx), so it needs no CORS at all.
    cors.init_app(
        app,
        resources={r"/api/v1/(?!admin).*": {"origins": app.config["CORS_ORIGINS"]}},
        methods=["GET", "OPTIONS"],
        supports_credentials=False,
        max_age=600,
    )

    from . import models  # noqa: F401  (register models for Flask-Migrate)
    from .api import api_v1
    from .auth.session import init_jwt_callbacks
    from .cli import register_cli

    init_jwt_callbacks(app)
    app.register_blueprint(api_v1)
    register_error_handlers(app)
    register_cli(app)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO)

    return app
