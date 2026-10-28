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
    # ---- Private digital product files (never public; see app/storage/private_files.py) ----
    PRODUCT_FILES_STORAGE = os.environ.get("PRODUCT_FILES_STORAGE", "local")
    PRODUCT_FILES_ROOT = os.environ.get("PRODUCT_FILES_ROOT") or str(INSTANCE_DIR / "product-files")
    PRODUCT_FILE_MAX_MB = _int("PRODUCT_FILE_MAX_MB", 300)
    PRODUCT_ZIP_MAX_UNCOMPRESSED_MB = _int("PRODUCT_ZIP_MAX_UNCOMPRESSED_MB", 1024)
    PRODUCT_ZIP_MAX_ENTRIES = _int("PRODUCT_ZIP_MAX_ENTRIES", 2000)
    PRODUCT_ZIP_MAX_RATIO = _int("PRODUCT_ZIP_MAX_RATIO", 100)
    # Written resource formats accepted for premium files (comma-separated keys from
    # app/commerce/files.py: pdf, epub, docx, xlsx, zip).
    RESOURCE_FILE_FORMATS = [
        f.strip().lower()
        for f in os.environ.get("RESOURCE_FILE_FORMATS", "pdf,epub,docx,xlsx,zip").split(",")
        if f.strip()
    ]
    PRODUCT_FILES_MIN_FREE_MB = _int("PRODUCT_FILES_MIN_FREE_MB", 500)
    # Batch 09.2: learners' supporting documents for assignments (private storage).
    SUBMISSION_FILE_MAX_MB = _int("SUBMISSION_FILE_MAX_MB", 20)
    SUBMISSION_MAX_FILES = _int("SUBMISSION_MAX_FILES", 5)
    SUBMISSION_FILE_FORMATS = [
        f.strip()
        for f in os.environ.get("SUBMISSION_FILE_FORMATS", "pdf,docx").split(",")
        if f.strip()
    ]
    # Optional malware scanner as a JSON argv list run by the background worker (no shell),
    # e.g. ["clamdscan", "--no-summary", "--fdpass", "{path}"]. Exit 0 = clean, 1 = infected.
    PRODUCT_FILES_SCAN_COMMAND = os.environ.get("PRODUCT_FILES_SCAN_COMMAND", "")
    PRODUCT_FILES_SCAN_TIMEOUT_SECONDS = _int("PRODUCT_FILES_SCAN_TIMEOUT_SECONDS", 300)
    # Nginx "internal" location that maps to PRODUCT_FILES_ROOT (X-Accel-Redirect). Empty:
    # Flask streams the file itself.
    PRODUCT_FILES_ACCEL_REDIRECT_PREFIX = os.environ.get("PRODUCT_FILES_ACCEL_REDIRECT_PREFIX", "")
    # Uploads in progress (request bodies spooled to disk, files being validated) live here,
    # never in the final storage areas. Put it on the same filesystem as the storage roots
    # so finished files are moved into place atomically. Stale files are removed by
    # `flask storage cleanup-temp` (systemd timer).
    UPLOAD_TEMP_ROOT = os.environ.get("UPLOAD_TEMP_ROOT") or str(INSTANCE_DIR / "tmp-uploads")
    UPLOAD_TEMP_MAX_AGE_HOURS = _int("UPLOAD_TEMP_MAX_AGE_HOURS", 6)
    # Disk space warnings in /admin/storage and `flask storage check` (percent free).
    STORAGE_WARN_FREE_PERCENT = _int("STORAGE_WARN_FREE_PERCENT", 15)
    STORAGE_CRITICAL_FREE_PERCENT = _int("STORAGE_CRITICAL_FREE_PERCENT", 5)
    # Written by deploy/backup/tpa-backup.sh after every run (read-only for the app).
    BACKUP_STATUS_FILE = os.environ.get("BACKUP_STATUS_FILE", "")
    BACKUP_MAX_AGE_HOURS = _int("BACKUP_MAX_AGE_HOURS", 36)
    DOWNLOAD_LINK_TTL_SECONDS = _int("DOWNLOAD_LINK_TTL_SECONDS", 300)
    DOWNLOAD_LINK_MAX_USES = _int("DOWNLOAD_LINK_MAX_USES", 5)
    RATELIMIT_DOWNLOADS = os.environ.get("RATELIMIT_DOWNLOADS", "30 per minute;300 per day")
    MAX_CONTENT_LENGTH = (
        (max(_int("MEDIA_MAX_UPLOAD_MB", 20), _int("PRODUCT_FILE_MAX_MB", 300)) + 1) * 1024 * 1024
    )

    # ---- Customer accounts (separate from administrators) ----
    CUSTOMER_SESSION_DAYS = _int("CUSTOMER_SESSION_DAYS", 30)  # "keep me signed in"
    # Sessions without "keep me signed in": browser-session cookie, server expiry in hours.
    CUSTOMER_SHORT_SESSION_HOURS = _int("CUSTOMER_SHORT_SESSION_HOURS", 12)
    CUSTOMER_COOKIE_SECURE = _bool("CUSTOMER_COOKIE_SECURE", False)
    CUSTOMER_VERIFY_TTL_HOURS = _int("CUSTOMER_VERIFY_TTL_HOURS", 48)
    CUSTOMER_RESET_TTL_MINUTES = _int("CUSTOMER_RESET_TTL_MINUTES", 60)
    RATELIMIT_CUSTOMER_REGISTER = os.environ.get(
        "RATELIMIT_CUSTOMER_REGISTER", "5 per minute;30 per hour"
    )
    RATELIMIT_CHECKOUT = os.environ.get("RATELIMIT_CHECKOUT", "10 per minute;60 per hour")
    # ---- Guest checkout (buying without an account) ----
    # Emailed link to a buyer's guest-checkout purchases; each new link replaces the last.
    GUEST_ACCESS_TTL_HOURS = _int("GUEST_ACCESS_TTL_HOURS", 72)
    # How long the buyer's browser can open a guest order with its order token, and how long
    # after payment it can download from the order page (after that: the emailed link).
    GUEST_ORDER_ACCESS_HOURS = _int("GUEST_ORDER_ACCESS_HOURS", 168)
    GUEST_ORDER_DOWNLOAD_HOURS = _int("GUEST_ORDER_DOWNLOAD_HOURS", 24)
    RATELIMIT_GUEST_ACCESS = os.environ.get("RATELIMIT_GUEST_ACCESS", "3 per minute;10 per hour")

    # ---- Payments (Paystack). Secrets stay in the environment, never in the database ----
    PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY", "")
    PAYSTACK_API_BASE = os.environ.get("PAYSTACK_API_BASE", "https://api.paystack.co").rstrip("/")
    PAYSTACK_TIMEOUT_SECONDS = _int("PAYSTACK_TIMEOUT_SECONDS", 20)
    # Optional extra check on webhook source addresses (comma-separated). Signatures are
    # always verified regardless.
    PAYSTACK_WEBHOOK_IPS = _list("PAYSTACK_WEBHOOK_IPS", "")
    # Deployment-level switch: live (real money) checkout can only be enabled when true,
    # in addition to the Super Admin readiness checklist in the admin.
    PAYMENTS_LIVE_ALLOWED = _bool("PAYMENTS_LIVE_ALLOWED", False)
    # Development only: let any signed-in customer use test-mode checkout (otherwise only
    # accounts staff mark as test accounts). Refused in production.
    PAYMENTS_TEST_CHECKOUT_PUBLIC = _bool("PAYMENTS_TEST_CHECKOUT_PUBLIC", False)
    # Membership subscriptions (Batch 10.2). "test" asserts that recurring USD charges were
    # verified in the Paystack *test* dashboard; anything else keeps membership checkout
    # closed. Live subscriptions are not supported yet and are always refused.
    MEMBERSHIP_BILLING_MODE = os.environ.get("MEMBERSHIP_BILLING_MODE", "disabled").strip().lower()

    # ---- Newsletter & email marketing (The Positive Reset) ----
    # Delivery backend for newsletter mail: none | console (development) | memory (tests) |
    # smtp. Defaults to MAIL_BACKEND. Credentials stay in the environment.
    NEWSLETTER_MAIL_BACKEND = os.environ.get("NEWSLETTER_MAIL_BACKEND", "")
    # Sender address on a domain with SPF, DKIM and DMARC configured for the provider.
    NEWSLETTER_FROM_EMAIL = os.environ.get("NEWSLETTER_FROM_EMAIL", "")
    # Optional separate SMTP account for bulk mail (falls back to MAIL_SMTP_*).
    NEWSLETTER_SMTP_HOST = os.environ.get("NEWSLETTER_SMTP_HOST", "")
    NEWSLETTER_SMTP_PORT = _int("NEWSLETTER_SMTP_PORT", 0)
    NEWSLETTER_SMTP_USERNAME = os.environ.get("NEWSLETTER_SMTP_USERNAME", "")
    NEWSLETTER_SMTP_PASSWORD = os.environ.get("NEWSLETTER_SMTP_PASSWORD", "")
    NEWSLETTER_SEND_RATE_PER_MINUTE = _int("NEWSLETTER_SEND_RATE_PER_MINUTE", 60)
    NEWSLETTER_BATCH_SIZE = _int("NEWSLETTER_BATCH_SIZE", 50)
    NEWSLETTER_MAX_ATTEMPTS = _int("NEWSLETTER_MAX_ATTEMPTS", 5)
    NEWSLETTER_STALE_CLAIM_MINUTES = _int("NEWSLETTER_STALE_CLAIM_MINUTES", 15)
    # Addresses that receive mail while the sending mode is "test" (comma-separated).
    NEWSLETTER_TEST_RECIPIENTS = _list("NEWSLETTER_TEST_RECIPIENTS", "")
    NEWSLETTER_CONFIRM_TTL_HOURS = _int("NEWSLETTER_CONFIRM_TTL_HOURS", 72)
    # Deployment-level switch: live (bulk) sending can only be enabled when true, in
    # addition to the readiness checklist in /admin/email-settings.
    NEWSLETTER_LIVE_ALLOWED = _bool("NEWSLETTER_LIVE_ALLOWED", False)
    # Shared secret for signed bounce/complaint/delivery feedback (HMAC-SHA256).
    EMAIL_FEEDBACK_SECRET = os.environ.get("EMAIL_FEEDBACK_SECRET", "")
    LEAD_MAGNET_LINK_TTL_HOURS = _int("LEAD_MAGNET_LINK_TTL_HOURS", 72)
    LEAD_MAGNET_MAX_DOWNLOADS = _int("LEAD_MAGNET_MAX_DOWNLOADS", 10)
    RATELIMIT_NEWSLETTER_SIGNUP = os.environ.get(
        "RATELIMIT_NEWSLETTER_SIGNUP", "5 per minute;30 per hour"
    )

    # ---- Partnerships ----
    # Internal address notified of new partnership inquiries (only when MAIL_BACKEND sends).
    PARTNERSHIP_NOTIFY_EMAIL = os.environ.get("PARTNERSHIP_NOTIFY_EMAIL", "").strip()
    RATELIMIT_PARTNERSHIP_INQUIRY = os.environ.get(
        "RATELIMIT_PARTNERSHIP_INQUIRY", "5 per minute;20 per hour"
    )

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
    # Tolerate small wall-clock steps (WSL/VM time sync can move the clock backwards by a
    # second or two, making a fresh token's iat look "in the future"). Testing only:
    # production keeps the default of zero leeway.
    JWT_DECODE_LEEWAY = 5
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
    PRODUCT_FILES_ROOT = str(INSTANCE_DIR / "test-product-files")  # overridden in tests
    PAYSTACK_SECRET_KEY = ""
    PAYSTACK_PUBLIC_KEY = ""
    PAYSTACK_API_BASE = "https://api.paystack.co"
    PAYMENTS_LIVE_ALLOWED = False
    PAYMENTS_TEST_CHECKOUT_PUBLIC = False
    PRODUCT_FILES_SCAN_COMMAND = ""
    MEDIA_SERVE_FROM_FLASK = True
    PUBLISH_DEBOUNCE_SECONDS = 0
    NEWSLETTER_MAIL_BACKEND = "memory"
    NEWSLETTER_FROM_EMAIL = "newsletter@example.org"
    NEWSLETTER_LIVE_ALLOWED = False
    NEWSLETTER_TEST_RECIPIENTS = ["tester@example.org"]
    EMAIL_FEEDBACK_SECRET = "testing-feedback-secret"


class ProductionConfig(BaseConfig):
    DEBUG = False
    JWT_COOKIE_SECURE = True
    CUSTOMER_COOKIE_SECURE = True
    ALLOW_SAMPLE_SEED = False
    PAYMENTS_TEST_CHECKOUT_PUBLIC = False

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
        secret = os.environ.get("PAYSTACK_SECRET_KEY", "")
        if secret and not secret.startswith(("sk_test_", "sk_live_")):
            missing.append("PAYSTACK_SECRET_KEY (must start with sk_test_ or sk_live_)")
        api_base = os.environ.get("PAYSTACK_API_BASE", "https://api.paystack.co").rstrip("/")
        if api_base != "https://api.paystack.co":
            missing.append("PAYSTACK_API_BASE (must be https://api.paystack.co in production)")
        if os.environ.get("NEWSLETTER_MAIL_BACKEND", "").lower() in {"console", "memory"}:
            missing.append("NEWSLETTER_MAIL_BACKEND (console/memory are not allowed in production)")
        if _bool("PAYMENTS_TEST_CHECKOUT_PUBLIC"):
            missing.append("PAYMENTS_TEST_CHECKOUT_PUBLIC (development only)")
        missing.extend(storage_layout_problems(cls))
        if missing:
            raise RuntimeError(f"Missing required production settings: {', '.join(missing)}")


def _inside(child: str, parent: str) -> bool:
    child_path, parent_path = Path(child).resolve(), Path(parent).resolve()
    return child_path == parent_path or parent_path in child_path.parents


def storage_layout_problems(cfg) -> list[str]:
    """Storage roots that would expose private files or lose data. Used at production
    start-up and by `flask storage check`."""
    problems = []
    roots = {
        "MEDIA_ROOT": cfg.MEDIA_ROOT,
        "PRODUCT_FILES_ROOT": cfg.PRODUCT_FILES_ROOT,
        "UPLOAD_TEMP_ROOT": cfg.UPLOAD_TEMP_ROOT,
    }
    for name, value in roots.items():
        if not value or not os.path.isabs(value):
            problems.append(f"{name} (must be an absolute path)")
    if problems:
        return problems
    public_roots = [str(Path(cfg.MEDIA_ROOT) / "public")]
    for name in ("PUBLISH_RELEASES_DIR", "PUBLISH_CURRENT_LINK"):
        value = getattr(cfg, name, "")
        if value:
            public_roots.append(value)
    for name in ("PRODUCT_FILES_ROOT", "UPLOAD_TEMP_ROOT"):
        for public in public_roots:
            if _inside(roots[name], public):
                problems.append(f"{name} (must be outside the public web root {public})")
    if _inside(cfg.PRODUCT_FILES_ROOT, cfg.MEDIA_ROOT) or _inside(
        cfg.MEDIA_ROOT, cfg.PRODUCT_FILES_ROOT
    ):
        problems.append("PRODUCT_FILES_ROOT (must not overlap MEDIA_ROOT)")
    return problems


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
