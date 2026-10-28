from flask import current_app
from flask_restful import Resource
from sqlalchemy import text

from ..extensions import db, limiter
from ..utils.responses import success


class HealthResource(Resource):
    """Liveness: the API process answers (no dependencies checked)."""

    def get(self):
        return success(
            {
                "status": "ok",
                "service": "tpa-api",
                "version": "v1",
                "environment": current_app.config.get("ENV_NAME", "unknown"),
            }
        )


def _database() -> str:
    try:
        db.session.execute(text("SELECT 1"))
        return "ok"
    except Exception:  # never leak connection details
        db.session.rollback()
        current_app.logger.warning("Readiness: database unavailable", exc_info=True)
        return "unavailable"


def _rate_limit_storage() -> str:
    try:
        return "ok" if limiter.storage.check() else "unavailable"
    except Exception:
        current_app.logger.warning("Readiness: rate-limit storage unavailable", exc_info=True)
        return "unavailable"


class ReadinessResource(Resource):
    """Readiness for deploy checks and monitoring: the database and the rate-limit
    storage (Redis in production) answer. 503 when either is down. Only ok/unavailable
    is reported; no hostnames, versions or errors."""

    def get(self):
        checks = {"database": _database(), "rate_limit_storage": _rate_limit_storage()}
        ready = all(v == "ok" for v in checks.values())
        return success(
            {"status": "ready" if ready else "unavailable", "checks": checks},
            status=200 if ready else 503,
        )
