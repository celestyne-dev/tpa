"""Written assignments, submissions and grading (Batch 09.2, phase 1).

- ``CourseAssignment``: a written assignment, practical project, case study, essay or
  structured reflection in a course (optionally attached to a lesson), with prompts,
  submission requirements, availability, an optional deadline (UTC), attempt limits and
  a resubmission policy. Draft / published / archived like the rest of the course CMS.
- ``AssignmentRubric``: immutable, numbered rubric versions. Editing a rubric creates a
  new version; a grade keeps the version it was scored against.
- ``AssignmentSubmission``: one per learner (enrolment) and assignment; carries the
  workflow status. ``AssignmentAttempt``: each attempt; a draft can be edited, a
  submitted attempt is never changed again (the historical record).
- ``AssignmentGrade``: one per attempt (draft, published or retracted) with rubric
  scores, learner-facing feedback and private staff notes.
- ``AssignmentFile``: supporting documents (PDF/DOCX) in private storage.
- ``AssignmentException``: an audited deadline extension or extra attempts for one
  learner. ``CourseAssessor``: staff assigned to grade a course's submissions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .base import TimestampMixin
from .types import JSONType, UTCDateTime, utcnow

ASSIGNMENT_KINDS = ("written", "project", "case_study", "essay", "reflection")
ASSIGNMENT_STATUSES = ("draft", "published", "archived")
RESUBMISSION_POLICIES = ("none", "on_request", "always")
LATE_POLICIES = ("block", "allow")
SUBMISSION_STATUSES = (
    "draft",
    "pending_review",
    "under_review",
    "changes_requested",
    "resubmitted",
    "graded",
    "completed",
)
ATTEMPT_STATUSES = ("draft", "submitted")
GRADE_STATUSES = ("draft", "published", "retracted")
GRADE_OUTCOMES = ("graded", "changes_requested")


class CourseAssignment(TimestampMixin, db.Model):
    __tablename__ = "course_assignments"
    __table_args__ = (
        CheckConstraint(f"kind IN {ASSIGNMENT_KINDS}", name="kind_valid"),
        CheckConstraint(f"status IN {ASSIGNMENT_STATUSES}", name="status_valid"),
        CheckConstraint(
            f"resubmission_policy IN {RESUBMISSION_POLICIES}", name="resubmission_policy_valid"
        ),
        CheckConstraint(f"late_policy IN {LATE_POLICIES}", name="late_policy_valid"),
        CheckConstraint("max_attempts IS NULL OR max_attempts > 0", name="max_attempts_positive"),
        CheckConstraint(
            "passing_percent IS NULL OR (passing_percent >= 0 AND passing_percent <= 100)",
            name="passing_percent_range",
        ),
        UniqueConstraint("course_id", "position", name="uq_course_assignments_position"),
        Index("ix_course_assignments_course_status", "course_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    lesson_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_lessons.id", ondelete="SET NULL"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="written", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # [{"id": "p1", "text": "...", "min_words": 50}] – one prompt for an essay, several for
    # a structured reflection.
    prompts: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    # {"min_words", "max_words", "files": "none"|"optional"|"required", "max_files"}
    requirements: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Used when the assignment has no rubric version: the assessor marks pass/fail.
    passing_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resubmission_policy: Mapped[str] = mapped_column(
        String(20), default="on_request", nullable=False
    )
    available_from: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    late_policy: Mapped[str] = mapped_column(String(10), default="block", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    # Latest rubric version (None: pass/fail grading without a rubric).
    rubric_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # When it first became a published, required assignment (completion policy, see
    # services/courses/assignments.py).
    required_since: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    lock_version: Mapped[int] = mapped_column(default=1, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    course = relationship("Course", lazy="joined")


class AssignmentRubric(db.Model):
    """An immutable rubric version."""

    __tablename__ = "assignment_rubrics"
    __table_args__ = (
        CheckConstraint("total_points > 0", name="total_points_positive"),
        CheckConstraint(
            "passing_percent >= 0 AND passing_percent <= 100", name="passing_percent_range"
        ),
        UniqueConstraint("assignment_id", "version", name="uq_assignment_rubrics_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("course_assignments.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    # [{"id", "title", "description", "max_points", "descriptors": [{"label", "points",
    #   "description"}]}] in display order.
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False)
    total_points: Mapped[int] = mapped_column(nullable=False)
    passing_percent: Mapped[int] = mapped_column(nullable=False)
    feedback_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class AssignmentSubmission(TimestampMixin, db.Model):
    """One learner's work on one assignment (all attempts)."""

    __tablename__ = "assignment_submissions"
    __table_args__ = (
        CheckConstraint(f"status IN {SUBMISSION_STATUSES}", name="status_valid"),
        UniqueConstraint(
            "assignment_id", "enrollment_id", name="uq_assignment_submissions_learner"
        ),
        Index("ix_assignment_submissions_assignment_status", "assignment_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("course_assignments.id", ondelete="RESTRICT"), nullable=False
    )
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("course_enrollments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    lock_version: Mapped[int] = mapped_column(default=1, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    assignment: Mapped[CourseAssignment] = relationship(lazy="joined")
    attempts: Mapped[list[AssignmentAttempt]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="AssignmentAttempt.number",
        lazy="selectin",
    )


class AssignmentAttempt(TimestampMixin, db.Model):
    __tablename__ = "assignment_attempts"
    __table_args__ = (
        CheckConstraint(f"status IN {ATTEMPT_STATUSES}", name="status_valid"),
        UniqueConstraint("submission_id", "number", name="uq_assignment_attempts_number"),
        UniqueConstraint(
            "submission_id", "idempotency_key", name="uq_assignment_attempts_idempotency"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("assignment_submissions.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    # {prompt id: text}
    responses: Mapped[dict[str, str]] = mapped_column(JSONType, default=dict, nullable=False)
    word_count: Mapped[int] = mapped_column(default=0, nullable=False)
    lock_version: Mapped[int] = mapped_column(default=1, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    is_late: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # The client's key for the submit request: a retried submit returns this attempt.
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    submission: Mapped[AssignmentSubmission] = relationship(back_populates="attempts")
    files: Mapped[list[AssignmentFile]] = relationship(
        back_populates="attempt",
        cascade="all, delete-orphan",
        order_by="AssignmentFile.id",
        lazy="selectin",
    )


class AssignmentGrade(TimestampMixin, db.Model):
    __tablename__ = "assignment_grades"
    __table_args__ = (
        CheckConstraint(f"status IN {GRADE_STATUSES}", name="status_valid"),
        CheckConstraint(f"outcome IN {GRADE_OUTCOMES}", name="outcome_valid"),
        CheckConstraint(
            "percent IS NULL OR (percent >= 0 AND percent <= 100)", name="percent_range"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("assignment_attempts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # The rubric version this attempt is scored against (kept when the rubric changes).
    rubric_id: Mapped[int | None] = mapped_column(
        ForeignKey("assignment_rubrics.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), default="graded", nullable=False)
    scores: Mapped[dict[str, int]] = mapped_column(JSONType, default=dict, nullable=False)
    total_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Shown to the learner once published.
    feedback: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Staff only; never sent to learners.
    private_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    lock_version: Mapped[int] = mapped_column(default=1, nullable=False)
    grader_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    graded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    published_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    retracted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    retracted_reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)


class AssignmentFile(db.Model):
    """A supporting document in private storage (never under a public directory)."""

    __tablename__ = "assignment_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("assignment_attempts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(400), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    attempt: Mapped[AssignmentAttempt] = relationship(back_populates="files")


class AssignmentException(db.Model):
    """An authorised exception for one learner: later deadline and/or extra attempts."""

    __tablename__ = "assignment_exceptions"
    __table_args__ = (
        CheckConstraint("extra_attempts >= 0", name="extra_attempts_non_negative"),
        Index("ix_assignment_exceptions_learner", "assignment_id", "enrollment_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("course_assignments.id", ondelete="CASCADE"), nullable=False
    )
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("course_enrollments.id", ondelete="CASCADE"), nullable=False
    )
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    extra_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    granted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class CourseAssessor(db.Model):
    """Staff assigned to review and grade one course's submissions."""

    __tablename__ = "course_assessors"
    __table_args__ = (UniqueConstraint("course_id", "user_id", name="uq_course_assessors_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    added_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
