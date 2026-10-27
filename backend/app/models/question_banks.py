"""Reusable question banks (Batch 09.2, phase 2).

A bank is a library of quiz questions that any course's quiz or practice exam can draw
from (``Assessment.selection``). Bank questions have the same shape as
``AssessmentQuestion``; ``correct`` is the answer key and never leaves the server for
learners. Each edit bumps ``version``. Attempts copy the questions they drew into
``AssessmentAttempt.snapshot``, so later edits, retirements or deletions in a bank never
change an attempt already started.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .base import TimestampMixin
from .courses import QUESTION_KINDS
from .types import JSONType, UTCDateTime

BANK_STATUSES = ("active", "archived")
BANK_QUESTION_STATUSES = ("active", "retired")


class QuestionBank(TimestampMixin, db.Model):
    __tablename__ = "question_banks"
    __table_args__ = (CheckConstraint(f"status IN {BANK_STATUSES}", name="status_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    lock_version: Mapped[int] = mapped_column(default=1, nullable=False)

    questions: Mapped[list[BankQuestion]] = relationship(
        back_populates="bank", cascade="all, delete-orphan", order_by="BankQuestion.id"
    )


class BankQuestion(TimestampMixin, db.Model):
    """``correct`` is the answer key: never sent to learners before they submit."""

    __tablename__ = "bank_questions"
    __table_args__ = (
        CheckConstraint(f"kind IN {QUESTION_KINDS}", name="kind_valid"),
        CheckConstraint(f"status IN {BANK_QUESTION_STATUSES}", name="status_valid"),
        CheckConstraint("points >= 0", name="points_non_negative"),
        Index("ix_bank_questions_bank_status", "bank_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    bank_id: Mapped[int] = mapped_column(
        ForeignKey("question_banks.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt: Mapped[str] = mapped_column(String(1000), nullable=False)
    help_text: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    correct: Mapped[list[Any]] = mapped_column(JSONType, default=list, nullable=False)
    explanation: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    points: Mapped[int] = mapped_column(default=1, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Lower-case labels used by selection rules (e.g. a topic or difficulty).
    tags: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    lock_version: Mapped[int] = mapped_column(default=1, nullable=False)

    bank: Mapped[QuestionBank] = relationship(back_populates="questions")

    @property
    def graded(self) -> bool:
        return self.kind in ("single_choice", "multiple_select", "true_false")
