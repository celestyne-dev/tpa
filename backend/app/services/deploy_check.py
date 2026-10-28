"""Pre-deployment configuration check (``flask deploy check``, Batch 12.3).

Run on the server, with the production ``.env`` loaded, before (re)starting services.
It complements ``ProductionConfig.validate`` (which refuses to start on missing secrets)
and ``flask storage check`` (folders, disk, backups) with the settings that only cause
trouble at runtime behind Nginx: proxy trust, shared rate limits, HTTPS origins, secure
cookies, payment safety and the database revision.

Output never contains secret values: secrets are reported by presence and length only,
and the database URL is never printed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from flask import current_app
from sqlalchemy import text

OK, WARNING, ERROR = "ok", "warning", "error"
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def _result(check: str, level: str, message: str) -> dict[str, str]:
    return {"check": check, "level": level, "message": message}


def _https(url: str) -> bool:
    return urlsplit(url or "").scheme == "https"


def _origin(url: str) -> str:
    parts = urlsplit(url or "")
    return f"{parts.scheme}://{parts.netloc}" if parts.netloc else ""


def _secrets(cfg) -> list[dict[str, str]]:
    out = []
    values = {}
    for name in ("SECRET_KEY", "JWT_SECRET_KEY"):
        value = str(cfg.get(name) or "")
        values[name] = value
        if len(value) < 32:
            out.append(_result(name, ERROR, f"{name} must be at least 32 random characters."))
        elif "change" in value.lower() or len(set(value)) < 10:
            out.append(_result(name, ERROR, f"{name} looks like a placeholder; generate one."))
        else:
            out.append(_result(name, OK, f"set ({len(value)} characters)."))
    if values["SECRET_KEY"] and values["SECRET_KEY"] == values["JWT_SECRET_KEY"]:
        out.append(_result("secrets_distinct", ERROR, "SECRET_KEY and JWT_SECRET_KEY must differ."))
    return out


def _database(cfg) -> list[dict[str, str]]:
    uri = str(cfg.get("SQLALCHEMY_DATABASE_URI") or "")
    if not uri.startswith("postgresql"):
        return [_result("database", ERROR, "DATABASE_URL must point at PostgreSQL.")]
    from ..extensions import db

    try:
        db.session.execute(text("SELECT 1"))
        current = db.session.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:
        db.session.rollback()
        return [_result("database", ERROR, "Can't connect or read alembic_version.")]
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(MIGRATIONS))
    head = ScriptDirectory.from_config(alembic_cfg).get_current_head()
    if current != head:
        return [
            _result(
                "database",
                ERROR,
                f"Schema at {current or 'none'}, code expects {head}: run `flask db upgrade` "
                "(after a backup).",
            )
        ]
    return [_result("database", OK, f"PostgreSQL reachable, schema at head ({head}).")]


def _rate_limits(cfg) -> list[dict[str, str]]:
    out = []
    if cfg.get("TRUST_PROXY"):
        out.append(_result("TRUST_PROXY", OK, "client IPs come from Nginx (one proxy)."))
    else:
        out.append(
            _result(
                "TRUST_PROXY",
                ERROR,
                "Set TRUST_PROXY=1 behind Nginx; otherwise every visitor shares 127.0.0.1 and "
                "one person's failed logins lock everyone out.",
            )
        )
    uri = str(cfg.get("RATELIMIT_STORAGE_URI") or "")
    if not uri.startswith(("redis://", "rediss://", "unix://")):
        out.append(
            _result(
                "RATELIMIT_STORAGE_URI",
                ERROR,
                "Use Redis (redis://127.0.0.1:6379/0): with several Gunicorn workers, memory:// "
                "counts per worker and limits are several times too lenient.",
            )
        )
        return out
    from ..extensions import limiter

    try:
        reachable = limiter.storage.check()
    except Exception:
        reachable = False
    out.append(
        _result("RATELIMIT_STORAGE_URI", OK, "Redis reachable.")
        if reachable
        else _result("RATELIMIT_STORAGE_URI", ERROR, "Redis is not reachable.")
    )
    return out


def _urls(cfg) -> list[dict[str, str]]:
    out = []
    site = str(cfg.get("SITE_URL") or "")
    for name in ("SITE_URL", "ADMIN_BASE_URL"):
        value = str(cfg.get(name) or "")
        out.append(
            _result(name, OK, f"{value}")
            if _https(value)
            else _result(name, ERROR, f"{name} must be an https:// URL (got {value or 'empty'}).")
        )
    origins = [o.rstrip("/") for o in cfg.get("CORS_ORIGINS") or []]
    if not origins or not all(_https(o) for o in origins):
        out.append(_result("CORS_ORIGINS", ERROR, "List only https:// origins."))
    elif _origin(site) not in origins:
        out.append(_result("CORS_ORIGINS", WARNING, "Doesn't include the SITE_URL origin."))
    else:
        out.append(_result("CORS_ORIGINS", OK, ", ".join(origins)))
    return out


def _cookies(cfg) -> list[dict[str, str]]:
    problems = []
    if not cfg.get("JWT_COOKIE_SECURE"):
        problems.append("admin session cookies are not Secure")
    if not cfg.get("CUSTOMER_COOKIE_SECURE"):
        problems.append("customer session cookies are not Secure")
    if not cfg.get("JWT_COOKIE_CSRF_PROTECT"):
        problems.append("admin CSRF protection is off")
    if str(cfg.get("JWT_COOKIE_SAMESITE") or "").lower() not in ("strict", "lax"):
        problems.append("admin cookies need SameSite=Strict or Lax")
    if problems:
        return [_result("cookies", ERROR, "; ".join(problems) + ".")]
    return [_result("cookies", OK, "Secure, CSRF-protected, SameSite.")]


def _payments(cfg) -> list[dict[str, str]]:
    out = []
    if cfg.get("PAYMENTS_LIVE_ALLOWED"):
        out.append(
            _result(
                "PAYMENTS_LIVE_ALLOWED",
                ERROR,
                "Live payments are not approved: set PAYMENTS_LIVE_ALLOWED=false.",
            )
        )
    else:
        out.append(_result("PAYMENTS_LIVE_ALLOWED", OK, "false (no real-money checkout)."))
    secret = str(cfg.get("PAYSTACK_SECRET_KEY") or "")
    if secret.startswith("sk_live_"):
        out.append(_result("PAYSTACK_SECRET_KEY", WARNING, "A live key is configured."))
    elif secret.startswith("sk_test_"):
        out.append(_result("PAYSTACK_SECRET_KEY", OK, "test key."))
    else:
        out.append(_result("PAYSTACK_SECRET_KEY", OK, "not set (checkout unavailable)."))
    if cfg.get("PAYMENTS_TEST_CHECKOUT_PUBLIC"):
        out.append(_result("PAYMENTS_TEST_CHECKOUT_PUBLIC", ERROR, "Development only."))
    mode = str(cfg.get("MEMBERSHIP_BILLING_MODE") or "disabled")
    out.append(
        _result("MEMBERSHIP_BILLING_MODE", OK, mode)
        if mode in ("disabled", "test")
        else _result("MEMBERSHIP_BILLING_MODE", ERROR, "Use disabled or test.")
    )
    try:
        from ..payments.config import get_settings

        stored = get_settings()["payments.checkout_mode"]
    except Exception:
        stored = None
    if stored == "live":
        out.append(_result("checkout_mode", ERROR, "Admin checkout mode is live; set test."))
    elif stored is not None:
        out.append(_result("checkout_mode", OK, f"{stored} (admin setting)."))
    return out


def _services(cfg) -> list[dict[str, str]]:
    out = []
    backend = str(cfg.get("MAIL_BACKEND") or "none")
    out.append(
        _result("MAIL_BACKEND", OK, "smtp")
        if backend == "smtp" and cfg.get("MAIL_SMTP_HOST")
        else _result(
            "MAIL_BACKEND",
            WARNING,
            "No email is sent (invitations, password resets, receipts): set smtp.",
        )
    )
    if cfg.get("MEDIA_SERVE_FROM_FLASK"):
        out.append(_result("MEDIA_SERVE_FROM_FLASK", WARNING, "Let Nginx serve /media/."))
    if not cfg.get("PRODUCT_FILES_ACCEL_REDIRECT_PREFIX"):
        out.append(
            _result(
                "PRODUCT_FILES_ACCEL_REDIRECT_PREFIX",
                WARNING,
                "Downloads are streamed by Gunicorn workers; set /_protected_downloads.",
            )
        )
    host = urlsplit(str(cfg.get("PUBLISH_API_URL") or "")).hostname
    if host not in ("127.0.0.1", "localhost", "::1"):
        out.append(
            _result(
                "PUBLISH_API_URL",
                WARNING,
                "Prerender should call Gunicorn on loopback (http://127.0.0.1:8000/api/v1).",
            )
        )
    if not cfg.get("BACKUP_STATUS_FILE"):
        out.append(
            _result(
                "BACKUP_STATUS_FILE",
                WARNING,
                "Not set: /admin/storage can't show backup results.",
            )
        )
    return out


def run_checks(*, database: bool = True) -> list[dict[str, str]]:
    cfg = current_app.config
    results = [
        _result("environment", OK, "production")
        if cfg.get("ENV_NAME") == "production"
        else _result("environment", ERROR, "Set FLASK_CONFIG=production.")
    ]
    results += _secrets(cfg)
    if database:
        results += _database(cfg)
    results += _rate_limits(cfg) + _urls(cfg) + _cookies(cfg) + _payments(cfg)
    results += _services(cfg)
    return results


def summary(results: list[dict[str, Any]]) -> str:
    levels = {r["level"] for r in results}
    return ERROR if ERROR in levels else WARNING if WARNING in levels else OK
