"""Text-based courses (Batch 09): curriculum, assessments, enrolments, progress, certificates.

Courses are written learning: modules of lessons made of text blocks, exercises, quizzes,
reflections and downloadable written resources. There are no video fields anywhere.

Pricing and payment stay in commerce. A premium course points at one product of type
``course``; buying that product (or holding any usable entitlement to it) is what gives
access, so refunds, revocations and expiry apply without a second access system. Course
worksheets are that product's private files, delivered by the existing download
authorisation.

Ordering is protected by unique (parent, position) constraints; the services renumber
in two steps so a reorder never collides with itself.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .base import TimestampMixin
from .types import JSONType, NullableJSONType, UTCDateTime, utcnow

COURSE_STATUSES = ("draft", "scheduled", "published", "archived")
COURSE_ACCESS = ("free", "premium")
COURSE_AVAILABILITY = ("available", "coming_soon")
COURSE_LEVELS = ("beginner", "intermediate", "advanced", "all_levels")
LESSON_STATUSES = ("draft", "published")
ASSESSMENT_KINDS = ("quiz", "reflection", "self_assessment")
ASSESSMENT_STATUSES = ("draft", "published")
SHOW_ANSWERS = ("after_submit", "after_pass", "never")
QUESTION_KINDS = ("single_choice", "multiple_select", "true_false", "short_text", "rating")
ATTEMPT_STATUSES = ("in_progress", "submitted", "expired")
ENROLLMENT_SOURCES = ("free", "purchase", "manual", "membership")
ENROLLMENT_STATUSES = ("active", "revoked")
REVISION_ACTIONS = ("migrated", "published", "restored")
ANCHOR_STATUSES = ("anchored", "orphaned")
HIGHLIGHT_COLORS = ("yellow", "green", "blue", "pink")


course_topics = Table(
    "course_topics",
    db.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("topic_id", Integer, ForeignKey("topics.id", ondelete="RESTRICT"), primary_key=True),
    Index("ix_course_topics_topic_id", "topic_id"),
)


class CourseCategory(TimestampMixin, db.Model):
    __tablename__ = "course_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Course(TimestampMixin, db.Model):
    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint(f"status IN {COURSE_STATUSES}", name="status_valid"),
        CheckConstraint(f"access_type IN {COURSE_ACCESS}", name="access_type_valid"),
        CheckConstraint(f"availability IN {COURSE_AVAILABILITY}", name="availability_valid"),
        CheckConstraint(f"level IN {COURSE_LEVELS}", name="level_valid"),
        CheckConstraint("access_days IS NULL OR access_days > 0", name="access_days_positive"),
        CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes > 0", name="estimated_minutes_positive"
        ),
        Index("ix_courses_status_featured", "status", "is_featured"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    summary: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    description: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType, default=list, nullable=False
    )
    outcomes: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    prerequisites: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    audience: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    level: Mapped[str] = mapped_column(String(20), default="all_levels", nullable=False)
    # Editor's figure; when empty the lessons' reading times are added up.
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_categories.id", ondelete="SET NULL"), index=True, nullable=True
    )
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("authors.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    cover_media_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=True
    )
    social_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    access_type: Mapped[str] = mapped_column(String(10), default="free", nullable=False)
    availability: Mapped[str] = mapped_column(String(20), default="available", nullable=False)
    # New enrolments allowed (existing learners keep access when closed).
    enrollment_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Free courses: access ends this many days after enrolling (None: lifetime). Premium
    # courses follow the access period of their product's entitlement.
    access_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Premium courses: the commerce product that is bought. Free courses may link one
    # too (its files become the course worksheets, granted on enrolment).
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), unique=True, nullable=True
    )
    certificate_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    featured_order: Mapped[int] = mapped_column(default=0, nullable=False)
    seo_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    noindex: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    # Publication time (in the future while scheduled).
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    first_published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    lock_version: Mapped[int] = mapped_column(default=1, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    category: Mapped[CourseCategory | None] = relationship(lazy="joined")
    author = relationship("Author", lazy="joined")
    product = relationship("Product", lazy="joined")
    topics = relationship("Topic", secondary=course_topics, lazy="selectin")
    modules: Mapped[list[CourseModule]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="CourseModule.position",
        lazy="selectin",
    )
    assessments: Mapped[list[Assessment]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="Assessment.position",
        lazy="selectin",
    )


class CourseModule(TimestampMixin, db.Model):
    __tablename__ = "course_modules"
    __table_args__ = (UniqueConstraint("course_id", "position", name="uq_course_modules_position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    objectives: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)

    course: Mapped[Course] = relationship(back_populates="modules")
    lessons: Mapped[list[CourseLesson]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="CourseLesson.position",
        lazy="selectin",
    )


class CourseLesson(TimestampMixin, db.Model):
    __tablename__ = "course_lessons"
    __table_args__ = (
        CheckConstraint(f"status IN {LESSON_STATUSES}", name="status_valid"),
        CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes > 0", name="estimated_minutes_positive"
        ),
        UniqueConstraint("course_id", "slug", name="uq_course_lessons_slug"),
        UniqueConstraint("module_id", "position", name="uq_course_lessons_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Denormalised from the module so lesson slugs are unique per course.
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    module_id: Mapped[int] = mapped_column(
        ForeignKey("course_modules.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    body: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    # Readable by anyone from the course page (a free sample of a published course).
    is_preview: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completion_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Batch 09.1: the columns above (title, summary, body, minutes, flags) are the LIVE
    # content learners read. Editors work on ``draft`` (a full working copy of those
    # fields, None when it matches the live content); publishing copies it to the live
    # columns and records a numbered revision. ``lock_version`` guards concurrent edits.
    draft: Mapped[dict[str, Any] | None] = mapped_column(NullableJSONType, nullable=True)
    lock_version: Mapped[int] = mapped_column(default=1, server_default="1", nullable=False)
    draft_saved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    draft_saved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Number of the revision learners currently read (None: never published).
    live_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    module: Mapped[CourseModule] = relationship(back_populates="lessons")


class LessonRevision(db.Model):
    """An immutable snapshot of a lesson's content as it was published (or restored)."""

    __tablename__ = "course_lesson_revisions"
    __table_args__ = (
        CheckConstraint(f"action IN {REVISION_ACTIONS}", name="action_valid"),
        UniqueConstraint("lesson_id", "number", name="uq_course_lesson_revisions_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("course_lessons.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    body: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_preview: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completion_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    restored_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Assessment(TimestampMixin, db.Model):
    """A graded quiz, an ungraded written reflection or a self-assessment."""

    __tablename__ = "course_assessments"
    __table_args__ = (
        CheckConstraint(f"kind IN {ASSESSMENT_KINDS}", name="kind_valid"),
        CheckConstraint(f"status IN {ASSESSMENT_STATUSES}", name="status_valid"),
        CheckConstraint(f"show_answers IN {SHOW_ANSWERS}", name="show_answers_valid"),
        CheckConstraint(
            "passing_score IS NULL OR (passing_score >= 0 AND passing_score <= 100)",
            name="passing_score_range",
        ),
        CheckConstraint("max_attempts IS NULL OR max_attempts > 0", name="max_attempts_positive"),
        CheckConstraint(
            "time_limit_minutes IS NULL OR (time_limit_minutes > 0 AND time_limit_minutes <= 600)",
            name="time_limit_range",
        ),
        UniqueConstraint("course_id", "position", name="uq_course_assessments_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    # Shown at the end of this lesson; None: listed after the modules (e.g. a final quiz).
    lesson_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_lessons.id", ondelete="SET NULL"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="quiz", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    # Quizzes only: percentage of the graded points needed to pass.
    passing_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    show_answers: Mapped[str] = mapped_column(String(20), default="after_submit", nullable=False)
    required_for_completion: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    # Batch 09.2 phase 2. Practice exams never count towards completion or certificates.
    practice: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    # None: untimed. Timed attempts get a fixed server-side deadline when started.
    time_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Random draws from question banks: [{"bank_id": public id, "count": n, "tags": [...]}]
    # added to the fixed questions when an attempt starts.
    selection: Mapped[list[dict[str, Any]] | None] = mapped_column(NullableJSONType, nullable=True)
    shuffle_questions: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    shuffle_options: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    course: Mapped[Course] = relationship(back_populates="assessments")
    questions: Mapped[list[AssessmentQuestion]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
        order_by="AssessmentQuestion.position",
        lazy="selectin",
    )

    @property
    def graded(self) -> bool:
        return self.kind == "quiz"

    @property
    def needs_start(self) -> bool:
        """Questions are drawn, shuffled or timed: learners start an attempt (which fixes
        its questions and deadline) before they see the questions."""
        return bool(
            self.time_limit_minutes
            or self.selection
            or self.shuffle_questions
            or self.shuffle_options
        )


class AssessmentQuestion(TimestampMixin, db.Model):
    """``correct`` is the answer key: never sent to learners before they submit."""

    __tablename__ = "assessment_questions"
    __table_args__ = (
        CheckConstraint(f"kind IN {QUESTION_KINDS}", name="kind_valid"),
        CheckConstraint("points >= 0", name="points_non_negative"),
        UniqueConstraint("assessment_id", "position", name="uq_assessment_questions_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("course_assessments.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt: Mapped[str] = mapped_column(String(1000), nullable=False)
    help_text: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    # Choice questions: [{"id": "a", "text": "..."}]; rating: scale labels in ``settings``.
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    # Choice: list of option ids; true/false: [true] or [false]; empty for ungraded kinds.
    correct: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    explanation: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    points: Mapped[int] = mapped_column(default=1, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)

    assessment: Mapped[Assessment] = relationship(back_populates="questions")

    @property
    def graded(self) -> bool:
        return self.kind in ("single_choice", "multiple_select", "true_false")


class CourseEnrollment(db.Model):
    """One learner in one course (unique). Access is re-checked on every request: the
    enrolment must be active and, for premium courses, the product entitlement usable."""

    __tablename__ = "course_enrollments"
    __table_args__ = (
        CheckConstraint(f"source IN {ENROLLMENT_SOURCES}", name="source_valid"),
        CheckConstraint(f"status IN {ENROLLMENT_STATUSES}", name="status_valid"),
        CheckConstraint("progress_percent >= 0 AND progress_percent <= 100", name="progress_range"),
        UniqueConstraint("customer_id", "course_id", name="uq_course_enrollments_learner"),
        Index("ix_course_enrollments_course_status", "course_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    # The entitlement that carries the course files (purchase, or granted on enrolment).
    entitlement_id: Mapped[int | None] = mapped_column(
        ForeignKey("entitlements.id", ondelete="SET NULL"), nullable=True
    )
    enrolled_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    # Free and manual enrolments with an access period; premium access follows the product.
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_lesson_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_lessons.id", ondelete="SET NULL"), nullable=True
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    progress_percent: Mapped[int] = mapped_column(default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    granted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    customer = relationship("Customer", lazy="joined")
    course: Mapped[Course] = relationship(lazy="joined")


class LessonProgress(db.Model):
    __tablename__ = "lesson_progress"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "lesson_id", name="uq_lesson_progress_lesson"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("course_enrollments.id", ondelete="CASCADE"), nullable=False
    )
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("course_lessons.id", ondelete="CASCADE"), index=True, nullable=False
    )
    first_viewed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    last_viewed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Exercise blocks the learner marked as done, and their private written notes.
    acknowledged: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    responses: Mapped[dict[str, str]] = mapped_column(JSONType, default=dict, nullable=False)
    # Batch 09.1: ticked checklist item ids, and the last meaningful reading position
    # ({"block": uid, "percent": 0-100}), saved at most every few seconds by the reader.
    checklist: Mapped[list[str]] = mapped_column(
        JSONType, default=list, server_default="[]", nullable=False
    )
    position: Mapped[dict[str, Any] | None] = mapped_column(NullableJSONType, nullable=True)
    position_saved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class AssessmentAttempt(db.Model):
    __tablename__ = "assessment_attempts"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id", "enrollment_id", "attempt_number", name="uq_assessment_attempts_number"
        ),
        Index("ix_assessment_attempts_enrollment", "enrollment_id"),
        CheckConstraint(f"status IN {ATTEMPT_STATUSES}", name="status_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("course_assessments.id", ondelete="RESTRICT"), nullable=False
    )
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("course_enrollments.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(nullable=False)
    answers: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    # Per-question outcome with the question text as it was (history stays readable).
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    score: Mapped[int] = mapped_column(default=0, nullable=False)
    max_score: Mapped[int] = mapped_column(default=0, nullable=False)
    percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # None for ungraded reflections and self-assessments.
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # None while in progress. Attempts submitted before Batch 09.2 phase 2 are "submitted".
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Batch 09.2 phase 2: started attempts. ``expired``: the deadline passed and only the
    # answers saved in time were scored.
    status: Mapped[str] = mapped_column(
        String(20), default="submitted", server_default="submitted", nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Server-only copy of the questions this attempt was given, answer keys included:
    # {"seed": int, "questions": [...]}. Later edits to the assessment or its banks never
    # change it.
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(NullableJSONType, nullable=True)
    lock_version: Mapped[int] = mapped_column(default=1, server_default="1", nullable=False)

    @property
    def finished(self) -> bool:
        return self.status != "in_progress"


class CourseCertificate(db.Model):
    """A platform-issued certificate of completion (not an accredited qualification)."""

    __tablename__ = "course_certificates"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Random, unguessable verification code shown on the certificate.
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("course_enrollments.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    recipient_name: Mapped[str] = mapped_column(String(160), nullable=False)
    course_title: Mapped[str] = mapped_column(String(200), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    corrected_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    correction_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    enrollment: Mapped[CourseEnrollment] = relationship(lazy="joined")


# ---- Batch 09.1: private study records ---------------------------------------------------
#
# Notes, highlights, bookmarks and reading preferences belong to one customer and are only
# served by the learner API (never by course-management endpoints). They are deleted when
# the account is deleted. A passage ``anchor`` is {"block": uid, "quote", "prefix",
# "suffix", "start", "end"} measured on the block's plain text; when a lesson is
# republished anchors are re-matched, and those that can't be matched safely become
# ``orphaned`` saved excerpts instead of pointing at the wrong text.


class LearnerNote(TimestampMixin, db.Model):
    __tablename__ = "learner_notes"
    __table_args__ = (
        CheckConstraint(
            f"anchor_status IS NULL OR anchor_status IN {ANCHOR_STATUSES}",
            name="anchor_status_valid",
        ),
        Index("ix_learner_notes_customer_course", "customer_id", "course_id"),
        Index("ix_learner_notes_lesson", "lesson_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    lesson_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_lessons.id", ondelete="SET NULL"), nullable=True
    )
    # Kept so the notebook stays readable if the lesson is later removed or renamed.
    lesson_title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    anchor: Mapped[dict[str, Any] | None] = mapped_column(NullableJSONType, nullable=True)
    anchor_status: Mapped[str | None] = mapped_column(String(20), nullable=True)


class LearnerHighlight(TimestampMixin, db.Model):
    __tablename__ = "learner_highlights"
    __table_args__ = (
        CheckConstraint(f"color IN {HIGHLIGHT_COLORS}", name="color_valid"),
        CheckConstraint(f"anchor_status IN {ANCHOR_STATUSES}", name="anchor_status_valid"),
        Index("ix_learner_highlights_customer_course", "customer_id", "course_id"),
        Index("ix_learner_highlights_lesson", "lesson_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    lesson_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_lessons.id", ondelete="SET NULL"), nullable=True
    )
    lesson_title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    color: Mapped[str] = mapped_column(String(16), default="yellow", nullable=False)
    anchor: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    anchor_status: Mapped[str] = mapped_column(String(20), default="anchored", nullable=False)
    # Live revision the anchor was last matched against.
    anchored_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LearnerBookmark(db.Model):
    __tablename__ = "learner_bookmarks"
    __table_args__ = (
        UniqueConstraint("customer_id", "lesson_id", name="uq_learner_bookmarks_lesson"),
        Index("ix_learner_bookmarks_customer_course", "customer_id", "course_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("course_lessons.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class LearnerPreference(db.Model):
    """Reading preferences (font size, spacing, width, theme), one row per customer."""

    __tablename__ = "learner_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    reading: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class LessonSearchDocument(db.Model):
    """Plain text of each live, published lesson for learner search (titles are read from
    the live lesson, module and course rows at query time). Rebuilt when a lesson is
    published or unpublished; PostgreSQL adds a full-text GIN index (migration
    e5a7c3b91d20), other databases fall back to substring matching."""

    __tablename__ = "course_lesson_search"

    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("course_lessons.id", ondelete="CASCADE"), primary_key=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
