"""Certificates of completion.

Issuance
- A certificate is issued automatically when the server records a completion award (see
  ``learning.recompute``) for a course with certificates enabled, using the learner's
  profile name; without a usable name the learner enters the name to print. Enrolment
  alone never qualifies.
- At most one *valid* certificate per enrolment (a partial unique index); concurrent
  requests return the same certificate. Each certificate snapshots the name, course title,
  completion date and signatory, so later profile or course edits don't change it.
- Completions recorded before completion awards existed (no ``completion_snapshot``) are
  re-checked against the course's current requirements before a certificate is issued.
  Existing certificates are never regenerated or changed by this.

Revocation and reissuance (``courses.manage_enrollments``, audited)
- Revoking keeps the record; the verification page then says "revoked". A revoked
  certificate is never replaced or restored automatically: completing again, recalculating
  progress or asking again does not issue a new one.
- Reissuing is an explicit staff action with a reason. It revokes the current certificate
  (if still valid) and issues a new one with a new code that records the one it replaces.
- Reinstating a revoked certificate is also explicit, and refused once it has a replacement.

Verification: ``/certificates/<code>`` shows valid, revoked or unavailable (the learner's
account was deleted), with the name, course, dates and issuer only: never an email
address, internal id or private record.

Email: one notification per issued certificate, sent after the request's transaction has
committed (``send_queued``). The certificate row is claimed (``pending``/``failed`` →
``sending``, with ``email_claimed_at``) before sending, so retries and parallel workers
can't send it twice, and an email problem never undoes the completion or the certificate.
``flask courses send-certificate-emails`` (run by the ``tpa-certificate-emails`` timer)
first recovers rows left in ``sending`` by a process that died mid-send (claim older than
``STALE_SENDING_AFTER``, recovered by one conditional update so only one runner wins),
then retries pending and failed ones, at most ``EMAIL_RETRY_LIMIT`` attempts each. The
only possible duplicate is a crash in the instant after the mail server accepted the
message and before the result was recorded; no email channel can rule that out.

Certificates are platform-issued certificates of completion, not accredited
qualifications, and say so.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app, has_request_context, request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import CourseCertificate, CourseEnrollment, Customer, User
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from ...utils.validation import plain_text_problem
from .. import audit_service
from ..serializers import iso
from .admin import require

logger = logging.getLogger("tpa.certificates")

ISSUER = "Think Positive Always"
DISCLAIMER = (
    "This is a platform-issued certificate of completion from Think Positive Always. "
    "It is not an accredited qualification, degree or professional licence."
)
DELETED_ACCOUNT = "Account deleted"
_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # no 0/O, 1/I/L
_EMAIL_QUEUE = "tpa_certificate_emails"
EMAIL_RETRY_LIMIT = 5
# A send claims its row ("sending") for at most the SMTP timeout (15 s); a claim this old
# means the process sending it died, so the row is recovered and retried.
STALE_SENDING_AFTER = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(UTC)


def _code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(12))
    return f"TPA-{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def _clean_name(name: Any) -> str:
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 120 or plain_text_problem(name):
        raise ValidationError(details={"name": ["Enter the name to show (2 to 120 characters)."]})
    return " ".join(name.split())


def _reason(value: Any, field: str = "reason") -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 300
        or plain_text_problem(value)
    ):
        raise ValidationError(details={field: ["Explain why (at most 300 characters)."]})
    return value.strip()


def _site() -> str:
    site = (current_app.config.get("SITE_URL") or "").rstrip("/")
    if not site and has_request_context():
        site = request.host_url.rstrip("/")
    return site


def verify_url(certificate: CourseCertificate) -> str:
    return f"{_site()}/certificates/{certificate.code}"


# ---- lookups ------------------------------------------------------------------------------


def active_for(enrollment_id: int) -> CourseCertificate | None:
    return db.session.scalar(
        select(CourseCertificate).where(
            CourseCertificate.enrollment_id == enrollment_id,
            CourseCertificate.revoked_at.is_(None),
        )
    )


def history(enrollment_id: int) -> list[CourseCertificate]:
    return list(
        db.session.scalars(
            select(CourseCertificate)
            .where(CourseCertificate.enrollment_id == enrollment_id)
            .order_by(CourseCertificate.issued_at, CourseCertificate.id)
        )
    )


def latest_for(enrollment_id: int) -> CourseCertificate | None:
    """The valid certificate, otherwise the most recent revoked one."""
    rows = history(enrollment_id)
    return next((c for c in rows if c.revoked_at is None), rows[-1] if rows else None)


def _replacement(certificate: CourseCertificate) -> CourseCertificate | None:
    return db.session.scalar(
        select(CourseCertificate).where(CourseCertificate.replaces_id == certificate.id)
    )


def get_by_code(code: Any) -> CourseCertificate:
    if not isinstance(code, str) or len(code) > 32:
        raise NotFoundError("Certificate not found.")
    certificate = db.session.scalar(
        select(CourseCertificate).where(CourseCertificate.code == code.strip().upper())
    )
    if certificate is None:
        raise NotFoundError("Certificate not found.")
    return certificate


# ---- eligibility and issuance -------------------------------------------------------------


def eligibility(enrollment: CourseEnrollment, *, record: bool = False) -> tuple[bool, str]:
    """Whether the enrolment's completion qualifies for a certificate, and why not.

    ``record``: for a completion recorded before completion awards existed that meets the
    course's current requirements, store the award now (``completion_snapshot``)."""
    if enrollment.completed_at is None:
        return False, "Complete every required lesson and assessment to receive a certificate."
    if enrollment.completion_snapshot is not None:
        return True, ""
    from . import learning

    state = learning.progress(enrollment)
    if not state["complete"]:
        return False, (
            "The course requirements have changed since you finished it. Complete the "
            "outstanding requirements to receive a certificate."
        )
    if record:
        enrollment.completion_snapshot = learning.completion_snapshot(
            enrollment, state, recorded="re-checked"
        )
    return True, ""


def _signatory() -> tuple[str, str]:
    from ..settings_service import get_values

    values = get_values()
    return (
        (values.get("certificates.signatory_name") or "").strip(),
        (values.get("certificates.signatory_title") or "").strip(),
    )


def _create(
    enrollment: CourseEnrollment,
    recipient: str,
    *,
    replaces: CourseCertificate | None = None,
    reason: str = "",
    actor: User | None = None,
) -> CourseCertificate:
    signatory_name, signatory_title = _signatory()
    course = enrollment.course
    for _ in range(5):
        certificate = CourseCertificate(
            code=_code(),
            enrollment_id=enrollment.id,
            customer_id=enrollment.customer_id,
            course_id=enrollment.course_id,
            recipient_name=recipient,
            course_title=course.title,
            course_slug=course.slug,
            completed_at=enrollment.completed_at,
            signatory_name=signatory_name,
            signatory_title=signatory_title,
            replaces_id=replaces.id if replaces else None,
            reissue_reason=reason,
            email_status="pending",
            email_attempts=0,
            updated_by_id=actor.id if actor else None,
        )
        try:
            with db.session.begin_nested():
                db.session.add(certificate)
                db.session.flush()
        except IntegrityError:
            existing = active_for(enrollment.id)
            if existing is not None:  # issued concurrently: the same certificate for both
                return existing
            continue  # code collision (practically impossible): try another code
        audit_service.record(
            "course.certificate_reissued" if replaces else "course.certificate_issued",
            "course",
            enrollment.course_id,
            actor=actor,
            details={
                "enrollment_id": enrollment.id,
                "code": certificate.code,
                **({"replaces": replaces.code, "reason": reason} if replaces else {}),
            },
        )
        _queue_email(certificate)
        return certificate
    raise ConflictError("Couldn't issue the certificate. Please try again.")


def issue(enrollment: CourseEnrollment, name: str | None = None) -> CourseCertificate:
    """Issue the enrolment's certificate, or return the valid one it already has."""
    existing = active_for(enrollment.id)
    if existing is not None:
        return existing
    # Decide from one read of the history: a certificate issued by a concurrent request
    # since the check above is valid (returned), not revoked.
    rows = history(enrollment.id)
    concurrent = next((c for c in rows if c.revoked_at is None), None)
    if concurrent is not None:
        return concurrent
    if rows:
        raise ConflictError(
            "The certificate for this course was revoked. Contact us if you think this is a "
            "mistake."
        )
    if not enrollment.course.certificate_enabled:
        raise ConflictError("This course doesn't issue certificates.")
    if enrollment.status != "active":
        raise ConflictError("This enrolment is no longer active.")
    ok, why = eligibility(enrollment, record=True)
    if not ok:
        raise ConflictError(why)
    recipient = _clean_name(name if name is not None else enrollment.customer.display_name)
    return _create(enrollment, recipient)


def issue_on_completion(enrollment: CourseEnrollment) -> CourseCertificate | None:
    """Called when a completion award is recorded. Never fails the completion: without a
    usable profile name the learner is asked for one instead."""
    if not enrollment.course.certificate_enabled:
        return None
    name = (enrollment.customer.display_name or "").strip()
    if not name:
        return None
    try:
        return issue(enrollment)
    except (ConflictError, ValidationError):
        return None


# ---- what people see ----------------------------------------------------------------------


def status(certificate: CourseCertificate) -> str:
    if certificate.revoked_at is not None and certificate.revoked_reason == DELETED_ACCOUNT:
        return "unavailable"
    return "revoked" if certificate.revoked_at else "valid"


def verify_dict(certificate: CourseCertificate) -> dict[str, Any]:
    """What anyone may see when checking a certificate code."""
    state = status(certificate)
    replaced = certificate.revoked_at is not None and _replacement(certificate) is not None
    if state == "unavailable":
        return {
            "code": certificate.code,
            "status": state,
            "recipient_name": None,
            "course_title": None,
            "issued_at": None,
            "completed_at": None,
            "issuer": ISSUER,
            "signatory_name": None,
            "signatory_title": None,
            "statement": DISCLAIMER,
            "revoked_at": iso(certificate.revoked_at),
            "replaced": False,
        }
    return {
        "code": certificate.code,
        "status": state,
        "recipient_name": certificate.recipient_name,
        "course_title": certificate.course_title,
        "issued_at": iso(certificate.issued_at),
        "completed_at": iso(certificate.completed_at),
        "issuer": ISSUER,
        "signatory_name": certificate.signatory_name or None,
        "signatory_title": certificate.signatory_title or None,
        "statement": DISCLAIMER,
        "revoked_at": iso(certificate.revoked_at),
        # A newer certificate was issued in its place (its code is not disclosed here).
        "replaced": replaced,
    }


def learner_dict(certificate: CourseCertificate | None) -> dict[str, Any] | None:
    if certificate is None:
        return None
    return {
        "code": certificate.code,
        "recipient_name": certificate.recipient_name,
        "issued_at": iso(certificate.issued_at),
        "completed_at": iso(certificate.completed_at),
        "revoked": certificate.revoked_at is not None,
        "verify_url": verify_url(certificate),
    }


def admin_dict(certificate: CourseCertificate) -> dict[str, Any]:
    replaces = (
        db.session.get(CourseCertificate, certificate.replaces_id)
        if certificate.replaces_id
        else None
    )
    replacement = _replacement(certificate)
    return verify_dict(certificate) | {
        "id": certificate.id,
        "enrollment_id": certificate.enrollment_id,
        "recipient_name": certificate.recipient_name,
        "course_title": certificate.course_title,
        "issued_at": iso(certificate.issued_at),
        "completed_at": iso(certificate.completed_at),
        "revoked_reason": certificate.revoked_reason,
        "corrected_at": iso(certificate.corrected_at),
        "correction_note": certificate.correction_note,
        "replaces_code": replaces.code if replaces else None,
        "replaced_by_code": replacement.code if replacement else None,
        "reissue_reason": certificate.reissue_reason,
        "email_status": certificate.email_status,
        "email_attempts": certificate.email_attempts,
        "emailed_at": iso(certificate.emailed_at),
        # Left "sending" by a process that died; recovered by the next email run.
        "email_stuck": certificate.email_status == "sending" and _stale(certificate),
        "verify_url": verify_url(certificate),
    }


# ---- staff actions ------------------------------------------------------------------------


def _revoke(certificate: CourseCertificate, reason: str, actor: User) -> None:
    certificate.revoked_at = _now()
    certificate.revoked_reason = reason
    certificate.updated_by_id = actor.id
    audit_service.record(
        "course.certificate_revoked",
        "course",
        certificate.course_id,
        actor=actor,
        details={"code": certificate.code, "reason": reason},
    )


def revoke(certificate: CourseCertificate, reason: Any, actor: User) -> CourseCertificate:
    require(actor, P.COURSES_MANAGE_ENROLLMENTS)
    reason = _reason(reason)
    if certificate.revoked_at is not None:
        raise ConflictError("This certificate is already revoked.")
    _revoke(certificate, reason, actor)
    return certificate


def reinstate(certificate: CourseCertificate, reason: Any, actor: User) -> CourseCertificate:
    """Explicitly restore a revoked certificate (never done automatically)."""
    require(actor, P.COURSES_MANAGE_ENROLLMENTS)
    if certificate.revoked_at is None:
        raise ConflictError("This certificate is not revoked.")
    reason = _reason(reason)
    if certificate.revoked_reason == DELETED_ACCOUNT:
        raise ConflictError("The learner's account was deleted; this certificate stays revoked.")
    if _replacement(certificate) is not None or active_for(certificate.enrollment_id):
        raise ConflictError(
            "A newer certificate replaces this one. Revoke that one before restoring this."
        )
    certificate.revoked_at = None
    certificate.revoked_reason = ""
    certificate.updated_by_id = actor.id
    audit_service.record(
        "course.certificate_reinstated",
        "course",
        certificate.course_id,
        actor=actor,
        details={"code": certificate.code, "reason": reason},
    )
    return certificate


def reissue(certificate: CourseCertificate, data: Any, actor: User) -> CourseCertificate:
    """Controlled reissuance: revoke this certificate (if still valid) and issue a new one
    (new code) that records what it replaces. Optionally with a corrected name."""
    require(actor, P.COURSES_MANAGE_ENROLLMENTS)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    reason = _reason(data.get("reason"))
    name = data.get("recipient_name")
    recipient = _clean_name(name) if name not in (None, "") else certificate.recipient_name
    if certificate.revoked_reason == DELETED_ACCOUNT:
        raise ConflictError("The learner's account was deleted; certificates can't be reissued.")
    if _replacement(certificate) is not None:
        raise ConflictError("This certificate has already been replaced.")
    current = active_for(certificate.enrollment_id)
    if current is not None and current.id != certificate.id:
        raise ConflictError("This learner already has a newer valid certificate. Reissue that one.")
    enrollment = db.session.get(CourseEnrollment, certificate.enrollment_id)
    if enrollment is None or enrollment.completed_at is None:
        raise ConflictError("This learner's completion is no longer recorded.")
    if certificate.revoked_at is None:
        _revoke(certificate, f"Replaced by a reissued certificate: {reason}", actor)
        db.session.flush()
    return _create(enrollment, recipient, replaces=certificate, reason=reason, actor=actor)


def correct(certificate: CourseCertificate, data: Any, actor: User) -> CourseCertificate:
    require(actor, P.COURSES_MANAGE_ENROLLMENTS)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    name = _clean_name(data.get("recipient_name"))
    note = data.get("note")
    if not isinstance(note, str) or not note.strip() or len(note) > 300 or plain_text_problem(note):
        raise ValidationError(
            details={"note": ["Explain the correction (at most 300 characters)."]}
        )
    if certificate.revoked_at is not None:
        raise ConflictError("Revoked certificates can't be corrected. Reissue instead.")
    before = certificate.recipient_name
    certificate.recipient_name = name
    certificate.corrected_at = _now()
    history_note = certificate.correction_note
    entry = f"{iso(certificate.corrected_at)}: “{before}” → “{name}” ({note.strip()})"
    certificate.correction_note = f"{history_note}\n{entry}".strip()[-4000:]
    certificate.updated_by_id = actor.id
    audit_service.record(
        "course.certificate_corrected",
        "course",
        certificate.course_id,
        actor=actor,
        details={"code": certificate.code, "from": before, "to": name, "note": note.strip()},
    )
    return certificate


def resend_email(certificate: CourseCertificate, actor: User) -> None:
    """Staff: send the certificate email again (after the request commits)."""
    require(actor, P.COURSES_MANAGE_ENROLLMENTS)
    if certificate.revoked_at is not None:
        raise ConflictError("Revoked certificates aren't emailed.")
    if certificate.email_status == "sending" and not _stale(certificate):
        raise ConflictError("The email is being sent right now.")
    certificate.email_status = "pending"
    certificate.email_claimed_at = None
    audit_service.record(
        "course.certificate_email_requested",
        "course",
        certificate.course_id,
        actor=actor,
        details={"code": certificate.code},
    )
    _queue_email(certificate)


# ---- the PDF ------------------------------------------------------------------------------


def render_pdf(certificate: CourseCertificate) -> bytes:
    if certificate.revoked_at is not None:
        raise ConflictError("This certificate has been revoked.")
    from .certificate_pdf import CertificateContent, render

    return render(
        CertificateContent(
            recipient_name=certificate.recipient_name,
            course_title=certificate.course_title,
            code=certificate.code,
            issued_at=certificate.issued_at,
            completed_at=certificate.completed_at,
            verify_url=verify_url(certificate),
            issuer=ISSUER,
            signatory_name=certificate.signatory_name,
            signatory_title=certificate.signatory_title,
            statement=DISCLAIMER,
        )
    )


# ---- email --------------------------------------------------------------------------------


def _queue_email(certificate: CourseCertificate) -> None:
    db.session.info.setdefault(_EMAIL_QUEUE, set()).add(certificate.id)


def has_queued() -> bool:
    return bool(db.session.info.get(_EMAIL_QUEUE))


def discard_queued() -> None:
    db.session.info.pop(_EMAIL_QUEUE, None)


def send_queued() -> list[str]:
    """Send the emails for certificates issued in this request (after it committed)."""
    ids = sorted(db.session.info.pop(_EMAIL_QUEUE, set()))
    out = []
    for certificate_id in ids:
        try:
            result = notify(certificate_id)
        except Exception:  # noqa: BLE001 - email must never break the learner's request
            db.session.rollback()
            logger.exception("certificate email %s could not be sent", certificate_id)
            continue
        if result:
            out.append(result)
    return out


def notify(certificate_id: int, *, include_sent: bool = False) -> str | None:
    """Send one certificate email if it is due. Returns the outcome, or None when another
    process has it or it isn't due (never sends twice)."""
    from ..commerce import emails

    statuses = ["pending", "failed"] + (["sent", "not_configured"] if include_sent else [])
    claimed = db.session.execute(
        update(CourseCertificate)
        .where(
            CourseCertificate.id == certificate_id,
            CourseCertificate.revoked_at.is_(None),
            CourseCertificate.email_status.in_(statuses),
        )
        .values(
            email_status="sending",
            email_attempts=CourseCertificate.email_attempts + 1,
            email_claimed_at=_now(),
        )
        .execution_options(synchronize_session=False)
    )
    db.session.commit()
    if claimed.rowcount != 1:
        return None
    certificate = db.session.get(CourseCertificate, certificate_id)
    db.session.refresh(certificate)
    customer = db.session.get(Customer, certificate.customer_id)
    if customer is None or not customer.email:
        certificate.email_status = "failed"
        certificate.email_claimed_at = None
        db.session.commit()
        return "failed"
    context = {
        "name": customer.display_name or certificate.recipient_name,
        "course_title": certificate.course_title,
        "code": certificate.code,
        "link": f"{_site()}/learn/{certificate.course_slug}"
        if certificate.course_slug
        else f"{_site()}/account/learning",
        "verify_url": verify_url(certificate),
        "reissued": certificate.replaces_id is not None,
    }
    outcome = emails.send(
        "certificate_reissued" if certificate.replaces_id else "certificate_issued",
        customer.email,
        context,
        customer=customer,
    )
    if outcome in ("sent", "development_console", "memory"):
        certificate.email_status = "sent"
        certificate.emailed_at = _now()
    elif outcome == "not_configured":
        certificate.email_status = "not_configured"
    else:
        certificate.email_status = "failed"
    certificate.email_claimed_at = None
    db.session.commit()
    return certificate.email_status


def _stale(certificate: CourseCertificate, now: datetime | None = None) -> bool:
    claimed = certificate.email_claimed_at
    if claimed is not None and claimed.tzinfo is None:
        claimed = claimed.replace(tzinfo=UTC)
    return claimed is None or claimed < (now or _now()) - STALE_SENDING_AFTER


def recover_stale_sends(now: datetime | None = None) -> int:
    """Rows stuck in ``sending`` (the sender died): back to ``failed`` so they are retried.

    Each row is released by a conditional update on the claim it was stuck with, so a
    parallel runner (or a sender that is somehow still alive and records its result) wins
    at most once and nothing is sent twice by the recovery itself."""
    cutoff = (now or _now()) - STALE_SENDING_AFTER
    stuck = db.session.execute(
        select(CourseCertificate.id, CourseCertificate.email_claimed_at).where(
            CourseCertificate.email_status == "sending",
            (CourseCertificate.email_claimed_at.is_(None))
            | (CourseCertificate.email_claimed_at < cutoff),
        )
    ).all()
    recovered = 0
    for certificate_id, claimed_at in stuck:
        claim = (
            CourseCertificate.email_claimed_at.is_(None)
            if claimed_at is None
            else CourseCertificate.email_claimed_at == claimed_at
        )
        result = db.session.execute(
            update(CourseCertificate)
            .where(
                CourseCertificate.id == certificate_id,
                CourseCertificate.email_status == "sending",
                claim,
            )
            .values(email_status="failed", email_claimed_at=None)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 1:
            recovered += 1
            logger.warning("certificate email %s was stuck sending; will retry", certificate_id)
    db.session.commit()
    return recovered


def retry_emails(limit: int = 50) -> dict[str, int]:
    """Recover stuck sends, then send pending and failed certificate emails (a few attempts
    each; never one already sent)."""
    recovered = recover_stale_sends()
    ids = list(
        db.session.scalars(
            select(CourseCertificate.id)
            .where(
                CourseCertificate.revoked_at.is_(None),
                CourseCertificate.email_status.in_(("pending", "failed")),
                CourseCertificate.email_attempts < EMAIL_RETRY_LIMIT,
            )
            .order_by(CourseCertificate.issued_at)
            .limit(limit)
        )
    )
    counts: dict[str, int] = {"recovered": recovered} if recovered else {}
    for certificate_id in ids:
        result = notify(certificate_id)
        if result:
            counts[result] = counts.get(result, 0) + 1
    return counts
