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

    if app.config.get("MEDIA_SERVE_FROM_FLASK"):
        _register_media_route(app)
    _register_redirect_fallback(app)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO)

    return app


def _register_media_route(app: Flask) -> None:
    """Development/test only: serve public media derivatives (Nginx does this in production)."""
    from flask import abort, send_file

    from .storage import StorageError, get_storage

    prefix = app.config["MEDIA_PUBLIC_BASE_URL"]
    if not prefix.startswith("/"):
        return

    @app.get(f"{prefix.rstrip('/')}/<path:key>")
    def media_file(key: str):
        try:
            path = get_storage().public_file(key)
        except (StorageError, AttributeError):
            abort(404)
        if not path.is_file():
            abort(404)
        response = send_file(path, conditional=True, max_age=31536000)
        # Variant paths are versioned, so they never change once written.
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _register_redirect_fallback(app: Flask) -> None:
    """Nginx asks this endpoint about paths that have no static file (see deploy/nginx).

    It answers with the CMS redirect (real 301/302/307/308) or 404, so redirects
    take effect immediately without regenerating or reloading the Nginx config.
    """
    from flask import abort, redirect

    @app.route("/_redirect/<path:path>", methods=["GET", "HEAD"])
    def redirect_fallback(path: str):
        from .services.redirect_service import resolve

        found = resolve("/" + path)
        if found is None:
            abort(404)
        response = redirect(found["destination"], code=found["status_code"])
        response.headers["Cache-Control"] = "public, max-age=300"
        return response
