"""Durable static-site publishing jobs.

Every change that affects public pages calls ``request_build`` (through
``publication_service.record_public_change``). Requests are persisted as
PublishJob rows and bursts are coalesced into one pending job whose start is
debounced (``PUBLISH_DEBOUNCE_SECONDS``, capped by ``PUBLISH_MAX_DELAY_SECONDS``).

A separate worker process (``flask publish worker``, run by systemd) claims
due jobs one at a time, builds the site and releases it atomically (see
``site_builder``). HTTP requests never run build commands.
"""

from __future__ import annotations

import os
import socket
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import func, select, update

from ..extensions import db
from ..models import PublishJob, User
from ..utils.errors import ConflictError, NotFoundError
from . import audit_service
from .serializers import iso

MAX_REASONS = 50


def _now() -> datetime:
    return datetime.now(UTC)


def request_build(reason: str, actor: User | None = None, trigger: str = "content") -> PublishJob:
    cfg = current_app.config
    now = _now()
    debounce = timedelta(seconds=cfg["PUBLISH_DEBOUNCE_SECONDS"])
    job = db.session.scalar(
        select(PublishJob).where(PublishJob.status == "pending").order_by(PublishJob.id).limit(1)
    )
    if job is None:
        job = PublishJob(
            status="pending",
            reasons=[reason],
            trigger=trigger,
            requested_by_id=actor.id if actor else None,
            created_at=now,
            not_before=now if trigger == "manual" else now + debounce,
            max_attempts=cfg["PUBLISH_MAX_ATTEMPTS"],
        )
        db.session.add(job)
        return job
    if reason not in job.reasons:
        job.reasons = [*job.reasons, reason][-MAX_REASONS:]
    if trigger == "manual":
        job.not_before = now
        job.trigger = "manual"
    else:
        cap = job.created_at + timedelta(seconds=cfg["PUBLISH_MAX_DELAY_SECONDS"])
        job.not_before = min(max(job.not_before, now + debounce), max(cap, now))
    return job


def job_dict(job: PublishJob) -> dict[str, Any]:
    duration = None
    if job.started_at and job.finished_at:
        duration = round((job.finished_at - job.started_at).total_seconds(), 1)
    return {
        "id": job.id,
        "status": job.status,
        "reasons": job.reasons,
        "trigger": job.trigger,
        "requested_by": {"id": job.requested_by.id, "display_name": job.requested_by.display_name}
        if job.requested_by
        else None,
        "created_at": iso(job.created_at),
        "not_before": iso(job.not_before),
        "started_at": iso(job.started_at),
        "finished_at": iso(job.finished_at),
        "duration_seconds": duration,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "release": job.release,
        "error": job.error,
        "log_tail": job.log_tail,
        "details": job.details,
    }


def list_jobs(args: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stmt = select(PublishJob)
    if args.get("status"):
        stmt = stmt.where(PublishJob.status == args["status"])
    stmt = stmt.order_by(PublishJob.id.desc())
    page, size = args.get("page", 1), args.get("page_size", 20)
    total = db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.session.scalars(stmt.offset((page - 1) * size).limit(size)).all()
    pages = max(1, -(-total // size))
    return [job_dict(j) for j in rows], {
        "page": page,
        "page_size": size,
        "total": total,
        "total_pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


def get_job(job_id: int) -> PublishJob:
    job = db.session.get(PublishJob, job_id)
    if job is None:
        raise NotFoundError("Publishing job not found.")
    return job


def retry(job: PublishJob, actor: User) -> PublishJob:
    if job.status not in ("failed", "cancelled"):
        raise ConflictError("Only failed or cancelled jobs can be retried.")
    new = request_build(f"retry_of_{job.id}", actor, trigger="manual")
    audit_service.record("publish.retry", "publish_job", job.id, actor=actor)
    return new


def cancel(job: PublishJob, actor: User) -> PublishJob:
    if job.status != "pending":
        raise ConflictError("Only pending jobs can be cancelled.")
    job.status = "cancelled"
    job.finished_at = _now()
    audit_service.record("publish.cancelled", "publish_job", job.id, actor=actor)
    return job


def summary() -> dict[str, Any]:
    def latest(*statuses):
        return db.session.scalar(
            select(PublishJob)
            .where(PublishJob.status.in_(statuses))
            .order_by(PublishJob.id.desc())
            .limit(1)
        )

    last_success, last_failure = latest("succeeded"), latest("failed")
    running, pending = latest("running"), latest("pending")
    return {
        "running": job_dict(running) if running else None,
        "pending": job_dict(pending) if pending else None,
        "last_success": job_dict(last_success) if last_success else None,
        "last_failure": job_dict(last_failure)
        if last_failure and (not last_success or last_failure.id > last_success.id)
        else None,
        "worker_hint": "Run `flask --app wsgi publish worker` (systemd: tpa-publish-worker).",
    }


# ---- worker side ---------------------------------------------------------------------


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"[:100]


def recover_stale() -> int:
    """Running jobs whose worker stopped heartbeating are retried (or failed)."""
    threshold = _now() - timedelta(seconds=current_app.config["PUBLISH_STALE_AFTER_SECONDS"])
    stale = db.session.scalars(
        select(PublishJob).where(
            PublishJob.status == "running",
            func.coalesce(PublishJob.heartbeat_at, PublishJob.started_at) < threshold,
        )
    ).all()
    for job in stale:
        _finish_failure(job, "The worker stopped before the build finished.", "", transient=True)
    if stale:
        db.session.commit()
    return len(stale)


def claim_next() -> PublishJob | None:
    """Atomically claim the next due job. Only one job runs at a time."""
    recover_stale()
    if db.session.scalar(select(func.count(PublishJob.id)).where(PublishJob.status == "running")):
        return None
    now = _now()
    candidate = db.session.scalar(
        select(PublishJob.id)
        .where(PublishJob.status == "pending", PublishJob.not_before <= now)
        .order_by(PublishJob.not_before, PublishJob.id)
        .limit(1)
    )
    if candidate is None:
        return None
    result = db.session.execute(
        update(PublishJob)
        .where(PublishJob.id == candidate, PublishJob.status == "pending")
        .values(
            status="running",
            started_at=now,
            heartbeat_at=now,
            worker=worker_id(),
            attempts=PublishJob.attempts + 1,
            error=None,
        )
    )
    db.session.commit()
    if result.rowcount != 1:
        return None  # another worker won the race
    return db.session.get(PublishJob, candidate)


def heartbeat(job_id: int) -> None:
    db.session.execute(
        update(PublishJob)
        .where(PublishJob.id == job_id, PublishJob.status == "running")
        .values(heartbeat_at=_now())
    )
    db.session.commit()


def _finish_failure(job: PublishJob, error: str, log: str, *, transient: bool) -> None:
    job.finished_at = _now()
    job.error = error[:500]
    job.log_tail = log[-8000:] if log else job.log_tail
    if transient and job.attempts < job.max_attempts:
        # Exponential backoff: 1, 2, 4 ... minutes.
        job.status = "pending"
        job.not_before = _now() + timedelta(minutes=2 ** max(job.attempts - 1, 0))
        job.started_at = job.heartbeat_at = None
        audit_service.record(
            "publish.retry_scheduled",
            "publish_job",
            job.id,
            details={"attempt": job.attempts, "error": job.error},
        )
    else:
        job.status = "failed"
        audit_service.record("publish.failed", "publish_job", job.id, details={"error": job.error})


def run_job(job: PublishJob, builder) -> PublishJob:
    from .site_builder import BuildError

    try:
        outcome = builder.run(job, lambda: heartbeat(job.id))
    except BuildError as exc:
        db.session.rollback()
        job = db.session.get(PublishJob, job.id)
        _finish_failure(job, str(exc), exc.log, transient=exc.transient)
        db.session.commit()
        return job
    except Exception as exc:  # unexpected: record safely, never crash the worker loop
        db.session.rollback()
        job = db.session.get(PublishJob, job.id)
        current_app.logger.exception("Publishing job %s crashed", job.id)
        _finish_failure(job, f"Unexpected error: {type(exc).__name__}", "", transient=True)
        db.session.commit()
        return job
    job = db.session.get(PublishJob, job.id)
    job.status = "succeeded"
    job.finished_at = _now()
    job.release = outcome.release
    job.log_tail = outcome.log[-8000:]
    job.details = outcome.details
    audit_service.record(
        "publish.succeeded",
        "publish_job",
        job.id,
        details={"release": outcome.release, **(outcome.details or {})},
    )
    db.session.commit()
    return job
