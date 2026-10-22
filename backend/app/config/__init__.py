"""Environment-specific configuration classes.

Secrets and environment-dependent values are read from the process
environment (loaded from backend/.env by python-dotenv in wsgi.py).
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[2]
INSTANCE_DIR = BACKEND_DIR / "instance"
REPO_DIR = BACKEND_DIR.parent


def _bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def normalise_database_url(url: str | None) -> str | None:
    """Accept common PostgreSQL URL spellings and use the psycopg 3 driver."""
    if not url:
        return None
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-insecure-change-me"
    SQLALCHEMY_DATABASE_URI = normalise_database_url(os.environ.get("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    RESTFUL_JSON = {"sort_keys": False}
    PROPAGATE_EXCEPTIONS = False
    CORS_ORIGINS = _list("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    TRUST_PROXY = _bool("TRUST_PROXY")

    # ---- Authentication (Flask-JWT-Extended, HttpOnly cookies) ----
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or "dev-insecure-jwt-secret-change-me"
    JWT_TOKEN_LOCATION = ["cookies"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=_int("ACCESS_TOKEN_MINUTES", 15))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=_int("REFRESH_TOKEN_DAYS", 14))
    JWT_COOKIE_SECURE = _bool("JWT_COOKIE_SECURE", False)
    JWT_COOKIE_SAMESITE = "Strict"
    JWT_COOKIE_DOMAIN = os.environ.get("JWT_COOKIE_DOMAIN") or None
    JWT_SESSION_COOKIE = False
    # Access cookie is sent to the API only; the refresh cookie only to the auth endpoints.
    JWT_ACCESS_COOKIE_PATH = "/api/"
    JWT_REFRESH_COOKIE_PATH = "/api/v1/admin/auth/"
    # Double-submit CSRF protection for every cookie-authenticated mutation.
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_CSRF_IN_COOKIES = True
    JWT_CSRF_CHECK_FORM = False
    JWT_ACCESS_CSRF_COOKIE_PATH = "/"
    JWT_REFRESH_CSRF_COOKIE_PATH = "/"
    JWT_ERROR_MESSAGE_KEY = "message"

    # ---- Rate limiting (Flask-Limiter) ----
    # Use a shared store (e.g. redis://127.0.0.1:6379/0) when running several Gunicorn workers.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_ENABLED = True
    RATELIMIT_LOGIN = os.environ.get("RATELIMIT_LOGIN", "5 per minute;20 per hour")
    RATELIMIT_SENSITIVE = os.environ.get("RATELIMIT_SENSITIVE", "10 per minute")
    RATELIMIT_REFRESH = os.environ.get("RATELIMIT_REFRESH", "30 per minute")

    # ---- Publishing ----
    # The prerender step writes this manifest; admins see whether a rebuild is due.
    FRONTEND_BUILD_MANIFEST = os.environ.get("FRONTEND_BUILD_MANIFEST") or str(
        REPO_DIR / "frontend" / "dist" / "prerender-manifest.json"
    )
    ALLOW_SAMPLE_SEED = True

    # ---- Static publishing pipeline (worker: `flask publish worker`) ----
    FRONTEND_DIR = os.environ.get("FRONTEND_DIR") or str(REPO_DIR / "frontend")
    # Successful builds are copied to RELEASES_DIR/<release> and SITE_CURRENT_LINK is
    # atomically switched to the new release. Nginx serves SITE_CURRENT_LINK.
    PUBLISH_RELEASES_DIR = os.environ.get("PUBLISH_RELEASES_DIR") or str(
        INSTANCE_DIR / "site" / "releases"
    )
    PUBLISH_CURRENT_LINK = os.environ.get("PUBLISH_CURRENT_LINK") or str(
        INSTANCE_DIR / "site" / "current"
    )
    PUBLISH_KEEP_RELEASES = _int("PUBLISH_KEEP_RELEASES", 5)
    PUBLISH_DEBOUNCE_SECONDS = _int("PUBLISH_DEBOUNCE_SECONDS", 30)
    PUBLISH_MAX_DELAY_SECONDS = _int("PUBLISH_MAX_DELAY_SECONDS", 300)
    PUBLISH_MAX_ATTEMPTS = _int("PUBLISH_MAX_ATTEMPTS", 3)
    PUBLISH_BUILD_TIMEOUT_SECONDS = _int("PUBLISH_BUILD_TIMEOUT_SECONDS", 900)
    PUBLISH_STALE_AFTER_SECONDS = _int("PUBLISH_STALE_AFTER_SECONDS", 1800)
    # API the prerender step reads from (the local Gunicorn in production).
    PUBLISH_API_URL = os.environ.get("PUBLISH_API_URL", "http://127.0.0.1:5000/api/v1")
    # Optional post-release hook for remote/cloud deployment, as a JSON argv list
    # (e.g. ["rsync", "-a", "--delete", "{release}/", "deploy@cdn:/site/"]). Not set = off.
    PUBLISH_DEPLOY_COMMAND = os.environ.get("PUBLISH_DEPLOY_COMMAND", "")
    # Build command as a JSON argv list (no shell). Default: ["npm", "run", "build"].
    PUBLISH_BUILD_COMMAND = os.environ.get("PUBLISH_BUILD_COMMAND", "")
    PUBLISH_DIST_DIR = os.environ.get("PUBLISH_DIST_DIR", "")

    # ---- Media library ----
    MEDIA_STORAGE = os.environ.get("MEDIA_STORAGE", "local")
    MEDIA_ROOT = os.environ.get("MEDIA_ROOT") or str(INSTANCE_DIR / "media")
    MEDIA_PUBLIC_BASE_URL = os.environ.get("MEDIA_PUBLIC_BASE_URL", "/media")
    # Flask serves /media/* itself only in development; Nginx serves it in production.
    MEDIA_SERVE_FROM_FLASK = _bool("MEDIA_SERVE_FROM_FLASK", False)
    MEDIA_MAX_UPLOAD_MB = _int("MEDIA_MAX_UPLOAD_MB", 20)
    MEDIA_MAX_PIXELS = _int("MEDIA_MAX_PIXELS", 50_000_000)
    MEDIA_MAX_DIMENSION = _int("MEDIA_MAX_DIMENSION", 12_000)
    # "original": keep the uploaded file privately; "master": keep a metadata-free
    # high-quality copy instead (smaller, still re-processable).
    MEDIA_RETENTION = os.environ.get("MEDIA_RETENTION", "original")
    MEDIA_ENABLE_AVIF = _bool("MEDIA_ENABLE_AVIF", True)
    MEDIA_SUPERSEDED_RETENTION_DAYS = _int("MEDIA_SUPERSEDED_RETENTION_DAYS", 14)
    MAX_CONTENT_LENGTH = (_int("MEDIA_MAX_UPLOAD_MB", 20) + 1) * 1024 * 1024

    # ---- SEO / redirects ----
    # Public website origin (matches VITE_SITE_URL); used for canonical checks and sitemaps.
    SITE_URL = os.environ.get("SITE_URL", "http://localhost:5173").rstrip("/")
    # Hosts redirects may point to besides internal paths (prevents open redirects).
    REDIRECT_ALLOWED_HOSTS = _list("REDIRECT_ALLOWED_HOSTS", "")

    # ---- Email and account links ----
    MAIL_BACKEND = os.environ.get("MAIL_BACKEND", "none")
    MAIL_FROM = os.environ.get("MAIL_FROM", "Think Positive Always <no-reply@localhost>")
    MAIL_SMTP_HOST = os.environ.get("MAIL_SMTP_HOST", "")
    MAIL_SMTP_PORT = _int("MAIL_SMTP_PORT", 587)
    MAIL_SMTP_USERNAME = os.environ.get("MAIL_SMTP_USERNAME", "")
    MAIL_SMTP_PASSWORD = os.environ.get("MAIL_SMTP_PASSWORD", "")
    # Public origin of the admin used in emailed links (activation, password reset).
    ADMIN_BASE_URL = os.environ.get("ADMIN_BASE_URL", "http://localhost:5173").rstrip("/")
    INVITATION_TTL_HOURS = _int("INVITATION_TTL_HOURS", 72)
    PASSWORD_RESET_TTL_MINUTES = _int("PASSWORD_RESET_TTL_MINUTES", 60)

    # ---- Fallback public business settings (CMS site settings take precedence) ----
    CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "").strip()
    PARTNERSHIPS_EMAIL = os.environ.get("PARTNERSHIPS_EMAIL", "").strip()
    NEWSLETTER_OPEN = _bool("NEWSLETTER_OPEN")
    MEDIA_KIT_URL = os.environ.get("MEDIA_KIT_URL", "").strip()
    SOCIAL_LINKS = {
        platform: os.environ.get(f"SOCIAL_{platform.upper()}", "").strip()
        for platform in ("linkedin", "instagram", "facebook", "x", "youtube", "tiktok", "pinterest")
    }


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    MEDIA_SERVE_FROM_FLASK = _bool("MEDIA_SERVE_FROM_FLASK", True)
    # Invitation and reset links are printed to the Flask terminal unless configured otherwise.
    MAIL_BACKEND = os.environ.get("MAIL_BACKEND", "console")
    SQLALCHEMY_DATABASE_URI = BaseConfig.SQLALCHEMY_DATABASE_URI or (
        f"sqlite:///{INSTANCE_DIR / 'tpa-dev.db'}"
    )


class TestingConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "testing-secret"
    JWT_SECRET_KEY = "testing-jwt-secret-with-enough-length-0123456789"
    # Private in-memory database per app instance (one shared connection).
    # Set TEST_DATABASE_URL to run the suite against a disposable PostgreSQL database.
    SQLALCHEMY_DATABASE_URI = (
        normalise_database_url(os.environ.get("TEST_DATABASE_URL")) or "sqlite://"
    )
    SQLALCHEMY_ENGINE_OPTIONS = (
        {}
        if os.environ.get("TEST_DATABASE_URL")
        else {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}
    )
    CORS_ORIGINS = ["http://localhost:5173"]
    RATELIMIT_STORAGE_URI = "memory://"
    CONTACT_EMAIL = ""
    PARTNERSHIPS_EMAIL = ""
    NEWSLETTER_OPEN = False
    MEDIA_KIT_URL = ""
    SOCIAL_LINKS = {}
    FRONTEND_BUILD_MANIFEST = str(INSTANCE_DIR / "does-not-exist-manifest.json")
    MAIL_BACKEND = "memory"
    ADMIN_BASE_URL = "http://localhost:5173"
    MEDIA_ROOT = str(INSTANCE_DIR / "test-media")  # tests override with a temp dir
    MEDIA_SERVE_FROM_FLASK = True
    PUBLISH_DEBOUNCE_SECONDS = 0


class ProductionConfig(BaseConfig):
    DEBUG = False
    JWT_COOKIE_SECURE = True
    ALLOW_SAMPLE_SEED = False

    @classmethod
    def validate(cls) -> None:
        missing = []
        if not os.environ.get("SECRET_KEY"):
            missing.append("SECRET_KEY")
        if len(os.environ.get("JWT_SECRET_KEY", "")) < 32:
            missing.append("JWT_SECRET_KEY (at least 32 characters)")
        if not cls.SQLALCHEMY_DATABASE_URI:
            missing.append("DATABASE_URL")
        if os.environ.get("MAIL_BACKEND", "none").lower() in {"console", "memory"}:
            missing.append("MAIL_BACKEND (console/memory are not allowed in production)")
        if os.environ.get("MAIL_BACKEND", "").lower() == "smtp" and not os.environ.get(
            "MAIL_SMTP_HOST"
        ):
            missing.append("MAIL_SMTP_HOST")
        if missing:
            raise RuntimeError(f"Missing required production settings: {', '.join(missing)}")


CONFIGS: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None) -> type[BaseConfig]:
    key = (name or os.environ.get("FLASK_CONFIG") or "development").lower()
    if key not in CONFIGS:
        raise ValueError(f"Unknown FLASK_CONFIG '{key}'. Use one of: {', '.join(CONFIGS)}")
    return CONFIGS[key]
