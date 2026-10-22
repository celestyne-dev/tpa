"""Think Positive Always API — application factory."""

from __future__ import annotations

import logging

from flask import Flask

from .config import INSTANCE_DIR, get_config
from .extensions import cors, db, migrate
from .utils.errors import register_error_handlers


def create_app(config_name: str | None = None) -> Flask:
    config = get_config(config_name)
    if hasattr(config, "validate"):
        config.validate()

    app = Flask(__name__, instance_path=str(INSTANCE_DIR))
    app.config.from_object(config)
    app.json.sort_keys = False
    app.config["ENV_NAME"] = config.__name__.removesuffix("Config").lower()
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

    if app.config.get("TRUST_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db)
    # CORS only for the API, only for explicitly approved origins, no credentials yet.
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        methods=["GET", "OPTIONS"],
        supports_credentials=False,
        max_age=600,
    )

    from . import models  # noqa: F401  (register models for Flask-Migrate)
    from .api import api_v1

    app.register_blueprint(api_v1)
    register_error_handlers(app)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO)

    return app
