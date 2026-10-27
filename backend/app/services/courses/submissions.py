"""Learner submissions for written assignments (Batch 09.2).

Every operation re-checks course access (``learning.require_access``: verified email,
active enrolment, usable entitlement), so refunds and revocations stop work at once.

- A learner has one ``AssignmentSubmission`` per assignment and works in a *draft*
  attempt. Saving a draft needs the draft's ``lock_version`` (two tabs can't silently
  overwrite each other).
- Submitting freezes the attempt: its responses and documents are never changed again.
  The submit request carries an ``idempotency_key``; a retried request returns the attempt
  that was already submitted instead of creating a second one.
- Resubmission follows the assignment's policy (``none`` / ``on_request`` after
  *changes requested* / ``always`` after a grade) and attempt limit, plus any active
  exception. Deadlines: after the (possibly extended) deadline, ``late_policy=block``
  refuses the submission; ``allow`` accepts it and marks it late.
- Supporting documents (PDF/DOCX by default) go through the same content validation as
  premium files (real type sniffing, macro/ActiveX/embedded-object and PDF-script
  rejection), are stored under ``submissions/`` in private storage with random keys, and
  are only delivered through authorised, audited download endpoints.
- Learners see grades and feedback only once published, never private staff notes.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import UTC, datetime
from typing import Any

from flask import current_app
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import set_committed_value

from ...commerce.files import FORMATS, FileRejected, safe_display_name, validate_file
from ...extensions import db
from ...models import (
    AssignmentAttempt,
    AssignmentFile,
    AssignmentGrade,
    AssignmentSubmission,
    Course,
    CourseAssignment,
    CourseEnrollment,
    Customer,
)
from ...storage import StorageError
from ...storage.private_files import get_private_storage
from ...utils.errors import APIError, ConflictError, NotFoundError, ValidationError
from ...utils.validation import plain_text_problem
from .. import audit_service
from ..serializers import iso
from . import assignment_admin as defs

MAX_RESPONSE = 50_000
_WORD = re.compile(r"\S+")


class DeadlinePassedError(APIError):
    status_code = 409
    code = "deadline_passed"
    message = "The deadline for this assignment has passed."


class AttemptsExhaustedError(APIError):
    status_code = 409
    code = "attempts_exhausted"
    message = "You have used every attempt for this assignment."


class ResubmissionNotAllowedError(APIError):
    status_code = 409
    code = "resubmission_not_allowed"
    message = "This assignment can't be resubmitted right now."


def _now() -> datetime:
    return datetime.now(UTC)


def _learning():
    from . import learning

    return learning


def words(text: str) -> int:
    return len(_WORD.findall(text or ""))


# ---- lookups and policy ---------------------------------------------------------------------


def learner_assignment(course: Course, public_id: str) -> CourseAssignment:
    """A published assignment of the course (drafts and archived ones are hidden)."""
    assignment = db.session.scalar(
        select(CourseAssignment).where(
            CourseAssignment.public_id == public_id,
            CourseAssignment.course_id == course.id,
            CourseAssignment.status == "published",
        )
    )
    if assignment is None:
        raise NotFoundError("Assignment not found.")
    return assignment


def submission_for(assignment: CourseAssignment, enrollment: CourseEnrollment):
    return db.session.scalar(
        select(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == assignment.id,
            AssignmentSubmission.enrollment_id == enrollment.id,
        )
    )


def _draft(submission: AssignmentSubmission | None) -> AssignmentAttempt | None:
    if submission is None:
        return None
    return next((a for a in submission.attempts if a.status == "draft"), None)


def _submitted(submission: AssignmentSubmission | None) -> list[AssignmentAttempt]:
    if submission is None:
        return []
    return [a for a in submission.attempts if a.status == "submitted"]


def effective_due(assignment: CourseAssignment, enrollment: CourseEnrollment) -> datetime | None:
    exception = defs.active_exception(assignment.id, enrollment.id)
    if exception is not None and exception.due_at is not None:
        return exception.due_at
    return assignment.due_at


def attempts_allowed(assignment: CourseAssignment, enrollment: CourseEnrollment) -> int | None:
    if assignment.max_attempts is None:
        return None
    exception = defs.active_exception(assignment.id, enrollment.id)
    return assignment.max_attempts + (exception.extra_attempts if exception else 0)


def can_submit(
    assignment: CourseAssignment,
    enrollment: CourseEnrollment,
    submission: AssignmentSubmission | None,
) -> tuple[bool, str | None]:
    """Whether a (new) attempt may be submitted now, and why not."""
    now = _now()
    if assignment.available_from and assignment.available_from > now:
        return False, "not_open"
    used = len(_submitted(submission))
    limit = attempts_allowed(assignment, enrollment)
    if limit is not None and used >= limit:
        return False, "attempts_exhausted"
    if submission is not None and used:
        status = submission.status
        if status == "completed":
            return False, "completed"
        if status in ("pending_review", "under_review", "resubmitted"):
            return False, "awaiting_review"
        policy = assignment.resubmission_policy
        if policy == "none":
            return False, "resubmission_not_allowed"
        if policy == "on_request" and status != "changes_requested":
            return False, "resubmission_not_allowed"
    due = effective_due(assignment, enrollment)
    if due is not None and now > due and assignment.late_policy == "block":
        return False, "deadline_passed"
    return True, None


# ---- serialisation (learner view) --------------------------------------------------------


def file_dict(file: AssignmentFile) -> dict[str, Any]:
    return {
        "id": file.public_id,
        "filename": file.original_filename,
        "format": file.file_format,
        "size_bytes": file.size_bytes,
        "uploaded_at": iso(file.created_at),
    }


def _grade_for(attempt: AssignmentAttempt) -> AssignmentGrade | None:
    return db.session.scalar(
        select(AssignmentGrade).where(AssignmentGrade.attempt_id == attempt.id)
    )


def learner_grade(grade: AssignmentGrade | None) -> dict[str, Any] | None:
    """Only published grades, without private notes or grader identity."""
    if grade is None or grade.status != "published":
        return None
    from ...models import AssignmentRubric

    rubric = db.session.get(AssignmentRubric, grade.rubric_id) if grade.rubric_id else None
    return {
        "outcome": grade.outcome,
        "scores": grade.scores or {},
        "total_points": grade.total_points,
        "max_points": grade.max_points,
        "percent": grade.percent,
        "passed": grade.passed,
        "feedback": grade.feedback,
        "rubric": defs.rubric_dict(rubric),
        "released_at": iso(grade.published_at),
    }


def attempt_dict(attempt: AssignmentAttempt, *, latest_number: int | None) -> dict[str, Any]:
    return {
        "id": attempt.public_id,
        "number": attempt.number,
        "status": attempt.status,
        "latest": attempt.number == latest_number,
        "responses": attempt.responses or {},
        "word_count": attempt.word_count,
        "files": [file_dict(f) for f in attempt.files],
        "lock_version": attempt.lock_version if attempt.status == "draft" else None,
        "submitted_at": iso(attempt.submitted_at),
        "is_late": attempt.is_late,
        "updated_at": iso(attempt.updated_at),
        "grade": learner_grade(_grade_for(attempt)) if attempt.status == "submitted" else None,
    }


def learner_view(assignment: CourseAssignment, enrollment: CourseEnrollment) -> dict[str, Any]:
    submission = submission_for(assignment, enrollment)
    allowed, reason = can_submit(assignment, enrollment, submission)
    submitted = _submitted(submission)
    latest = submitted[-1].number if submitted else None
    draft = _draft(submission)
    return {
        "assignment": defs.assignment_dict(assignment, staff=False)
        | {"due_at": iso(effective_due(assignment, enrollment))},
        "submission": {
            "id": submission.public_id,
            "status": submission.status,
            "completed_at": iso(submission.completed_at),
            "attempts_used": len(submitted),
        }
        if submission
        else None,
        "attempts_allowed": attempts_allowed(assignment, enrollment),
        "can_submit": allowed,
        "blocked_reason": reason,
        "draft": attempt_dict(draft, latest_number=None) if draft else None,
        "history": [attempt_dict(a, latest_number=latest) for a in reversed(submitted)],
    }


def list_for_learner(customer: Customer, course: Course) -> list[dict[str, Any]]:
    enrollment = _learning().require_access(customer, course)
    rows = db.session.scalars(
        select(CourseAssignment)
        .where(CourseAssignment.course_id == course.id, CourseAssignment.status == "published")
        .order_by(CourseAssignment.position)
    )
    out = []
    for assignment in rows:
        submission = submission_for(assignment, enrollment)
        out.append(
            {
                "id": assignment.public_id,
                "title": assignment.title,
                "kind": assignment.kind,
                "required": assignment.required,
                "lesson_id": assignment.lesson_id,
                "due_at": iso(effective_due(assignment, enrollment)),
                "status": submission.status if submission else "not_started",
            }
        )
    return out


def get_for_learner(customer: Customer, course: Course, public_id: str) -> dict[str, Any]:
    enrollment = _learning().require_access(customer, course)
    return learner_view(learner_assignment(course, public_id), enrollment)


# ---- drafts and submission -----------------------------------------------------------------


def _ensure_submission(
    assignment: CourseAssignment, enrollment: CourseEnrollment
) -> AssignmentSubmission:
    submission = submission_for(assignment, enrollment)
    if submission is not None:
        return submission
    submission = AssignmentSubmission(
        public_id=defs.new_id(),
        assignment_id=assignment.id,
        enrollment_id=enrollment.id,
        customer_id=enrollment.customer_id,
        status="draft",
    )
    try:
        with db.session.begin_nested():
            db.session.add(submission)
            db.session.flush()
    except IntegrityError:  # created by a concurrent request
        submission = submission_for(assignment, enrollment)
    return submission


def _ensure_draft(submission: AssignmentSubmission) -> AssignmentAttempt:
    draft = _draft(submission)
    if draft is not None:
        return draft
    number = max((a.number for a in submission.attempts), default=0) + 1
    draft = AssignmentAttempt(
        public_id=defs.new_id(), submission_id=submission.id, number=number, responses={}
    )
    try:
        with db.session.begin_nested():
            db.session.add(draft)
            db.session.flush()
    except IntegrityError:
        db.session.expire(submission, ["attempts"])
        draft = _draft(submission)
        if draft is None:
            raise ConflictError("Your work changed in another window. Reload it.") from None
    db.session.expire(submission, ["attempts"])
    return draft


def claim(model, row, expected: int) -> None:
    """Atomically bump ``lock_version`` from ``expected`` (compare-and-set in the database),
    so two concurrent requests can't both act on the same version."""
    result = db.session.execute(
        update(model)
        .where(model.id == row.id, model.lock_version == expected)
        .values(lock_version=expected + 1)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.session.expire(row)
        raise defs.EditConflictError()
    set_committed_value(row, "lock_version", expected + 1)


def _clean_responses(assignment: CourseAssignment, value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValidationError(details={"responses": ["Send your answers by prompt."]})
    prompts = {p["id"] for p in assignment.prompts or []}
    unknown = set(value) - prompts
    if unknown:
        raise ValidationError(details={"responses": ["Unknown prompt."]})
    out = {}
    for pid, text in value.items():
        if not isinstance(text, str) or len(text) > MAX_RESPONSE:
            raise ValidationError(
                details={
                    "responses": [f"Each answer is text of at most {MAX_RESPONSE} characters."]
                }
            )
        if problem := plain_text_problem(text):
            raise ValidationError(details={"responses": [problem]})
        out[pid] = text
    return out


def save_draft(customer: Customer, course: Course, public_id: str, data: Any) -> dict[str, Any]:
    enrollment = _learning().require_access(customer, course)
    assignment = learner_assignment(course, public_id)
    if not isinstance(data, dict) or set(data) - {"responses", "lock_version"}:
        raise ValidationError("Send your responses and the draft's version.")
    submission = _ensure_submission(assignment, enrollment)
    allowed, reason = can_submit(assignment, enrollment, submission)
    if not allowed and reason in ("completed", "attempts_exhausted", "resubmission_not_allowed"):
        raise ResubmissionNotAllowedError()
    draft = _ensure_draft(submission)
    if "lock_version" in data or draft.lock_version > 1 or draft.responses:
        defs.check_lock(draft, data)
    responses = _clean_responses(assignment, data.get("responses", {}))
    claim(AssignmentAttempt, draft, draft.lock_version)
    draft.responses = {**(draft.responses or {}), **responses}
    draft.word_count = sum(words(t) for t in draft.responses.values())
    draft.updated_at = _now()
    enrollment.last_activity_at = _now()
    db.session.flush()
    return learner_view(assignment, enrollment)


def _check_requirements(assignment: CourseAssignment, draft: AssignmentAttempt) -> None:
    req = defs.requirements(assignment)
    problems = []
    responses = draft.responses or {}
    for prompt in assignment.prompts or []:
        text = responses.get(prompt["id"], "")
        if not text.strip():
            problems.append(f"Answer: “{prompt['text'][:60]}”.")
        elif prompt.get("min_words") and words(text) < prompt["min_words"]:
            problems.append(
                f"Write at least {prompt['min_words']} words for “{prompt['text'][:60]}”."
            )
    total = draft.word_count
    if req.get("min_words") and total < req["min_words"]:
        problems.append(f"Write at least {req['min_words']} words in total.")
    if req.get("max_words") and total > req["max_words"]:
        problems.append(f"Keep your response under {req['max_words']} words.")
    if req.get("files") == "required" and not draft.files:
        problems.append("Attach at least one supporting document.")
    if problems:
        raise ValidationError(
            "Your submission isn't complete yet.", details={"requirements": problems}
        )


def _fingerprint(draft: AssignmentAttempt) -> str:
    payload = json.dumps(
        {"responses": draft.responses or {}, "files": sorted(f.sha256 for f in draft.files)},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def submit(customer: Customer, course: Course, public_id: str, data: Any) -> tuple[dict, bool]:
    """Submit the draft. Returns (learner view, created)."""
    enrollment = _learning().require_access(customer, course)
    assignment = learner_assignment(course, public_id)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    key = data.get("idempotency_key")
    if not isinstance(key, str) or not 8 <= len(key) <= 64 or not key.isascii():
        raise ValidationError(details={"idempotency_key": ["Send a unique request key."]})
    submission = submission_for(assignment, enrollment)
    if submission is not None:
        repeat = next((a for a in submission.attempts if a.idempotency_key == key), None)
        if repeat is not None and repeat.status == "submitted":
            return learner_view(assignment, enrollment), False
    draft = _draft(submission)
    if draft is None:
        raise ValidationError("Save your work before submitting.")
    defs.check_lock(draft, data)
    allowed, reason = can_submit(assignment, enrollment, submission)
    if not allowed:
        if reason == "deadline_passed":
            raise DeadlinePassedError()
        if reason == "attempts_exhausted":
            raise AttemptsExhaustedError()
        if reason == "not_open":
            raise ConflictError("This assignment isn't open for submissions yet.")
        raise ResubmissionNotAllowedError()
    _check_requirements(assignment, draft)
    now = _now()
    due = effective_due(assignment, enrollment)
    previous_status = submission.status
    try:
        claim(AssignmentAttempt, draft, draft.lock_version)
    except defs.EditConflictError:
        # A concurrent request with the same key may have just submitted it.
        db.session.expire(submission, ["attempts"])
        repeat = next((a for a in submission.attempts if a.idempotency_key == key), None)
        if repeat is not None and repeat.status == "submitted":
            return learner_view(assignment, enrollment), False
        raise
    draft.status = "submitted"
    draft.submitted_at = now
    draft.is_late = bool(due and now > due)
    draft.idempotency_key = key
    draft.content_sha256 = _fingerprint(draft)
    try:
        with db.session.begin_nested():
            db.session.flush()
    except IntegrityError:
        raise ConflictError("This submission was already received. Reload the page.") from None
    from .grading import transition

    transition(submission, "resubmitted" if previous_status != "draft" else "pending_review")
    enrollment.last_activity_at = now
    audit_service.record(
        "assignment.submitted",
        "course",
        course.id,
        details={
            "assignment_id": assignment.public_id,
            "submission_id": submission.public_id,
            "attempt": draft.number,
            "customer_id": customer.id,
            "late": draft.is_late,
            "sha256": draft.content_sha256,
        },
    )
    db.session.flush()
    db.session.expire(submission, ["attempts"])
    return learner_view(assignment, enrollment), True


# ---- supporting documents ----------------------------------------------------------------------


def _file_limits() -> dict[str, Any]:
    cfg = current_app.config
    return {
        "max_bytes": cfg["SUBMISSION_FILE_MAX_MB"] * 1024 * 1024,
        "max_uncompressed": cfg["PRODUCT_ZIP_MAX_UNCOMPRESSED_MB"] * 1024 * 1024,
        "max_entries": cfg["PRODUCT_ZIP_MAX_ENTRIES"],
        "max_ratio": cfg["PRODUCT_ZIP_MAX_RATIO"],
        "formats": [
            f for f in cfg["SUBMISSION_FILE_FORMATS"] if f in FORMATS and f in ("pdf", "docx")
        ],
    }


def upload(customer: Customer, course: Course, public_id: str, upload_file) -> dict[str, Any]:
    enrollment = _learning().require_access(customer, course)
    assignment = learner_assignment(course, public_id)
    req = defs.requirements(assignment)
    if req.get("files") == "none":
        raise ValidationError(details={"file": ["This assignment doesn't take documents."]})
    if upload_file is None or not getattr(upload_file, "filename", ""):
        raise ValidationError(details={"file": ["Choose a file to upload."]})
    submission = _ensure_submission(assignment, enrollment)
    allowed, reason = can_submit(assignment, enrollment, submission)
    if not allowed and reason in ("completed", "attempts_exhausted", "resubmission_not_allowed"):
        raise ResubmissionNotAllowedError()
    draft = _ensure_draft(submission)
    limit = min(
        req.get("max_files") or current_app.config["SUBMISSION_MAX_FILES"],
        current_app.config["SUBMISSION_MAX_FILES"],
    )
    if len(draft.files) >= limit:
        raise ValidationError(details={"file": [f"You can attach at most {limit} documents."]})
    storage = get_private_storage()
    limits = _file_limits()
    name = safe_display_name(upload_file.filename)
    try:
        tmp, size, digest = storage.receive(upload_file.stream, limits["max_bytes"])
    except StorageError as exc:
        if str(exc) == "too_large":
            _rejected(course, customer, assignment, name, "too large")
            raise ValidationError(
                details={
                    "file": [f"Documents can be at most {_file_limits()['max_bytes'] // 2**20} MB."]
                }
            ) from None
        raise
    try:
        report = validate_file(tmp, upload_file.filename, limits)
        # Random name; never derived from the uploaded filename (no collisions/traversal).
        key = (
            f"submissions/{submission.id}/a{draft.number}/"
            f"{secrets.token_hex(16)}{report.format.extensions[0]}"
        )
        file = AssignmentFile(
            public_id=defs.new_id(),
            attempt_id=draft.id,
            customer_id=customer.id,
            storage_key=key,
            original_filename=name,
            file_format=report.format.key,
            mime_type=report.format.mime_type,
            size_bytes=size,
            sha256=digest,
        )
        db.session.add(file)
        db.session.flush()
        storage.commit(tmp, key)
    except FileRejected as exc:
        storage.discard(tmp)
        _rejected(course, customer, assignment, name, str(exc)[:200])
        raise ValidationError("The file was not accepted.", details={"file": [str(exc)]}) from None
    except BaseException:
        storage.discard(tmp)
        raise
    claim(AssignmentAttempt, draft, draft.lock_version)
    audit_service.record(
        "assignment.file_uploaded",
        "course",
        course.id,
        details={
            "assignment_id": assignment.public_id,
            "submission_id": submission.public_id,
            "file_id": file.public_id,
            "customer_id": customer.id,
            "format": file.file_format,
            "size_bytes": size,
            "sha256": digest,
        },
    )
    db.session.expire(draft, ["files"])
    return learner_view(assignment, enrollment)


def _rejected(course, customer, assignment, name: str, reason: str) -> None:
    db.session.rollback()
    audit_service.record(
        "assignment.file_rejected",
        "course",
        course.id,
        details={
            "assignment_id": assignment.public_id,
            "customer_id": customer.id,
            "filename": name,
            "reason": reason,
        },
    )
    db.session.commit()


def _own_file(customer: Customer, file_id: str) -> AssignmentFile:
    file = db.session.scalar(
        select(AssignmentFile).where(
            AssignmentFile.public_id == file_id, AssignmentFile.customer_id == customer.id
        )
    )
    if file is None:
        raise NotFoundError("File not found.")
    return file


def _file_context(file: AssignmentFile):
    attempt = file.attempt
    submission = attempt.submission
    return attempt, submission, submission.assignment


def remove_file(customer: Customer, file_id: str) -> None:
    file = _own_file(customer, file_id)
    attempt, submission, assignment = _file_context(file)
    _learning().require_access(customer, assignment.course)
    if attempt.status != "draft":
        raise ConflictError("Submitted documents are kept with your submission.")
    key = file.storage_key
    db.session.delete(file)
    claim(AssignmentAttempt, attempt, attempt.lock_version)
    db.session.flush()
    delete_stored(key)
    audit_service.record(
        "assignment.file_removed",
        "course",
        assignment.course_id,
        details={"file_id": file_id, "customer_id": customer.id},
    )


def delete_stored(key: str) -> None:
    try:
        get_private_storage().delete(key)
    except (OSError, StorageError):  # pragma: no cover - logged and left for orphan checks
        current_app.logger.warning("Could not delete submission file %s", key)


def download_for_learner(customer: Customer, file_id: str):
    from ..commerce.downloads import file_response

    file = _own_file(customer, file_id)
    _, submission, assignment = _file_context(file)
    _learning().require_access(customer, assignment.course)
    audit_service.record(
        "assignment.file_downloaded",
        "course",
        assignment.course_id,
        details={"file_id": file.public_id, "customer_id": customer.id, "by": "learner"},
    )
    db.session.commit()
    return file_response(file, f"submission-{submission.public_id}-{file.public_id}")


# ---- personal data --------------------------------------------------------------------------


def export_learner(customer: Customer) -> list[dict[str, Any]]:
    """The learner's own work and released grades (no staff notes)."""
    out = []
    for submission in db.session.scalars(
        select(AssignmentSubmission).where(AssignmentSubmission.customer_id == customer.id)
    ):
        out.append(
            {
                "assignment": submission.assignment.title,
                "course_id": submission.assignment.course_id,
                "status": submission.status,
                "attempts": [
                    {
                        "number": a.number,
                        "status": a.status,
                        "responses": a.responses or {},
                        "submitted_at": iso(a.submitted_at),
                        "late": a.is_late,
                        "files": [file_dict(f) for f in a.files],
                        "grade": learner_grade(_grade_for(a)),
                    }
                    for a in submission.attempts
                ],
            }
        )
    return out


def erase_learner(customer: Customer) -> None:
    """Account deletion: remove written work, documents (files and rows), feedback and
    staff notes about the learner. Scores and statuses are kept without content so
    course statistics stay consistent (the same policy as quiz attempts)."""
    keys = []
    for submission in db.session.scalars(
        select(AssignmentSubmission).where(AssignmentSubmission.customer_id == customer.id)
    ):
        for attempt in submission.attempts:
            attempt.responses = {}
            for file in list(attempt.files):
                keys.append(file.storage_key)
                db.session.delete(file)
            grade = _grade_for(attempt)
            if grade is not None:
                grade.feedback, grade.private_notes = "", ""
    db.session.flush()
    for key in keys:
        delete_stored(key)
