"""Completion certificates.

A certificate is issued once per enrolment, after the server has recorded that every
completion requirement is met. Its random code (``TPA-XXXX-XXXX-XXXX``) can be checked
by anyone at ``/certificates/<code>``. Certificates are platform-issued certificates of
completion, not accredited qualifications, and say so. Staff with
``courses.manage_enrollments`` can correct the name or revoke a certificate (audited).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import CourseCertificate, CourseEnrollment, User
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from ...utils.validation import plain_text_problem
from .. import audit_service
from ..serializers import iso
from .admin import require
from .pdf import Page, wrap

ISSUER = "Think Positive Always"
DISCLAIMER = (
    "This is a platform-issued certificate of completion from Think Positive Always. "
    "It is not an accredited qualification, degree or professional licence."
)
_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # no 0/O, 1/I/L


def _code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(12))
    return f"TPA-{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def _clean_name(name: Any) -> str:
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 120 or plain_text_problem(name):
        raise ValidationError(details={"name": ["Enter the name to show (2 to 120 characters)."]})
    return " ".join(name.split())


def issue(enrollment: CourseEnrollment, name: str | None = None) -> CourseCertificate:
    """Issue the enrolment's certificate (idempotent)."""
    existing = db.session.scalar(
        select(CourseCertificate).where(CourseCertificate.enrollment_id == enrollment.id)
    )
    if existing is not None:
        return existing
    if enrollment.completed_at is None:
        raise ConflictError("Complete the course to receive a certificate.")
    if not enrollment.course.certificate_enabled:
        raise ConflictError("This course doesn't issue certificates.")
    recipient = _clean_name(name if name is not None else enrollment.customer.display_name)
    for _ in range(5):
        certificate = CourseCertificate(
            code=_code(),
            enrollment_id=enrollment.id,
            customer_id=enrollment.customer_id,
            course_id=enrollment.course_id,
            recipient_name=recipient,
            course_title=enrollment.course.title,
        )
        try:
            with db.session.begin_nested():
                db.session.add(certificate)
                db.session.flush()
        except IntegrityError:
            existing = db.session.scalar(
                select(CourseCertificate).where(CourseCertificate.enrollment_id == enrollment.id)
            )
            if existing is not None:  # issued concurrently
                return existing
            continue  # code collision (practically impossible): try another
        audit_service.record(
            "course.certificate_issued",
            "course",
            enrollment.course_id,
            details={"enrollment_id": enrollment.id, "code": certificate.code},
        )
        return certificate
    raise ConflictError("Couldn't issue the certificate. Please try again.")


def get_by_code(code: Any) -> CourseCertificate:
    if not isinstance(code, str) or len(code) > 32:
        raise NotFoundError("Certificate not found.")
    certificate = db.session.scalar(
        select(CourseCertificate).where(CourseCertificate.code == code.strip().upper())
    )
    if certificate is None:
        raise NotFoundError("Certificate not found.")
    return certificate


def verify_dict(certificate: CourseCertificate) -> dict[str, Any]:
    """What anyone may see when checking a certificate code."""
    return {
        "code": certificate.code,
        "status": "revoked" if certificate.revoked_at else "valid",
        "recipient_name": certificate.recipient_name,
        "course_title": certificate.course_title,
        "issued_at": iso(certificate.issued_at),
        "issuer": ISSUER,
        "statement": DISCLAIMER,
        "revoked_at": iso(certificate.revoked_at),
    }


def admin_dict(certificate: CourseCertificate) -> dict[str, Any]:
    return verify_dict(certificate) | {
        "id": certificate.id,
        "enrollment_id": certificate.enrollment_id,
        "revoked_reason": certificate.revoked_reason,
        "corrected_at": iso(certificate.corrected_at),
        "correction_note": certificate.correction_note,
    }


def revoke(certificate: CourseCertificate, reason: Any, actor: User) -> CourseCertificate:
    require(actor, P.COURSES_MANAGE_ENROLLMENTS)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 300:
        raise ValidationError(details={"reason": ["Explain why (at most 300 characters)."]})
    if certificate.revoked_at is not None:
        raise ConflictError("This certificate is already revoked.")
    certificate.revoked_at = datetime.now(UTC)
    certificate.revoked_reason = reason.strip()
    certificate.updated_by_id = actor.id
    audit_service.record(
        "course.certificate_revoked",
        "course",
        certificate.course_id,
        actor=actor,
        details={"code": certificate.code, "reason": reason.strip()},
    )
    return certificate


def reinstate(certificate: CourseCertificate, reason: Any, actor: User) -> CourseCertificate:
    require(actor, P.COURSES_MANAGE_ENROLLMENTS)
    if certificate.revoked_at is None:
        raise ConflictError("This certificate is not revoked.")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 300:
        raise ValidationError(details={"reason": ["Explain why (at most 300 characters)."]})
    certificate.revoked_at = None
    certificate.revoked_reason = ""
    certificate.updated_by_id = actor.id
    audit_service.record(
        "course.certificate_reinstated",
        "course",
        certificate.course_id,
        actor=actor,
        details={"code": certificate.code, "reason": reason.strip()},
    )
    return certificate


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
    before = certificate.recipient_name
    certificate.recipient_name = name
    certificate.corrected_at = datetime.now(UTC)
    history = certificate.correction_note
    entry = f"{iso(certificate.corrected_at)}: “{before}” → “{name}” ({note.strip()})"
    certificate.correction_note = f"{history}\n{entry}".strip()[-4000:]
    certificate.updated_by_id = actor.id
    audit_service.record(
        "course.certificate_corrected",
        "course",
        certificate.course_id,
        actor=actor,
        details={"code": certificate.code, "from": before, "to": name, "note": note.strip()},
    )
    return certificate


def render_pdf(certificate: CourseCertificate) -> bytes:
    if certificate.revoked_at is not None:
        raise ConflictError("This certificate has been revoked.")
    site = (current_app.config.get("SITE_URL") or "").rstrip("/")
    page = Page()
    page.rect(24, 24, page.width - 48, page.height - 48, line=2)
    page.rect(34, 34, page.width - 68, page.height - 68, line=0.6, rgb=(0.75, 0.66, 0.42))
    page.text(ISSUER.upper(), y=530, size=13, font="bold", gray=0.3)
    page.text("Certificate of Completion", y=478, size=34, font="bold")
    page.line(300, 462, 492, 462)
    page.text("This certifies that", y=420, size=14, gray=0.35)
    page.text(certificate.recipient_name, y=376, size=30, font="bold")
    page.text("has completed the online course", y=338, size=14, gray=0.35)
    y = 298
    for line in wrap(certificate.course_title, "bold", 22, 620, max_lines=2):
        page.text(line, y=y, size=22, font="bold")
        y -= 28
    issued = certificate.issued_at.strftime("%B %d, %Y").replace(" 0", " ")
    page.text(f"Issued {issued}", y=200, size=13, gray=0.3)
    page.text(f"Certificate ID: {certificate.code}", y=176, size=12, gray=0.3)
    if site:
        page.text(f"Verify at {site}/certificates/{certificate.code}", y=158, size=11, gray=0.35)
    y = 100
    for line in wrap(DISCLAIMER, "regular", 9.5, 600, max_lines=3):
        page.text(line, y=y, size=9.5, gray=0.4)
        y -= 13
    return page.render(f"Certificate of Completion — {certificate.course_title}")
