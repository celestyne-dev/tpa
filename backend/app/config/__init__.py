"""Environment-specific configuration classes.

Secrets and environment-dependent values are read from the process
environment (loaded from backend/.env by python-dotenv in wsgi.py).
"""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
INSTANCE_DIR = BACKEND_DIR / "instance"


def _bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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

    # Public business settings (exposed via GET /api/v1/site).
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
    SQLALCHEMY_DATABASE_URI = BaseConfig.SQLALCHEMY_DATABASE_URI or (
        f"sqlite:///{INSTANCE_DIR / 'tpa-dev.db'}"
    )


class TestingConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "testing-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    CORS_ORIGINS = ["http://localhost:5173"]
    CONTACT_EMAIL = ""
    PARTNERSHIPS_EMAIL = ""
    NEWSLETTER_OPEN = False
    MEDIA_KIT_URL = ""
    SOCIAL_LINKS = {}


class ProductionConfig(BaseConfig):
    DEBUG = False

    @classmethod
    def validate(cls) -> None:
        missing = []
        if not os.environ.get("SECRET_KEY"):
            missing.append("SECRET_KEY")
        if not cls.SQLALCHEMY_DATABASE_URI:
            missing.append("DATABASE_URL")
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
