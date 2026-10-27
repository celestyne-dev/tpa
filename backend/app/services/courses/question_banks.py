"""Reusable question banks (Batch 09.2, phase 2).

- ``question_banks.view``: list banks and read their questions without answer keys.
- ``question_banks.manage``: create, edit, archive and delete banks and questions; only
  this permission sees answer keys and explanations.

Banks are shared across courses. A quiz or practice exam draws from them with selection
rules (``Assessment.selection``: ``[{"bank_id", "count", "tags"}]``); each started attempt
copies the questions it drew (``assessments.build_snapshot``), so editing, retiring or
deleting bank questions never changes an attempt already started. Changes that would
leave a published assessment unable to fill its draws are refused.

Questions are validated by the same rules as assessment questions
(``assessments.clean_question``) and scored by the same scorer.
"""

from __future__ import annotations

import random
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...extensions import db
from ...models import Assessment, BankQuestion, QuestionBank, User
from ...models.courses import QUESTION_KINDS
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from ...utils.validation import plain_text_problem
from .. import audit_service
from ..admin.common import paginate
from ..serializers import iso
from .admin import require
from .assessments import GRADED_KINDS, QUESTION_FIELDS, clean_question, question_copy
from .assignment_admin import check_lock, new_id

MAX_RULES = 10
MAX_DRAW = 100
_TAG = re.compile(r"^[a-z0-9][a-z0-9 _-]{0,39}$")
BANK_FIELDS = {"title", "description", "status", "lock_version"}
BANK_QUESTION_FIELDS = QUESTION_FIELDS | {"tags", "status", "lock_version"}


def _with_key(actor: User) -> bool:
    return P.QUESTION_BANKS_MANAGE.value in effective_permissions(actor)


def get_bank(public_id: str) -> QuestionBank:
    bank = db.session.scalar(select(QuestionBank).where(QuestionBank.public_id == public_id))
    if bank is None:
        raise NotFoundError("Question bank not found.")
    return bank


def get_bank_question(bank: QuestionBank, public_id: str) -> BankQuestion:
    question = db.session.scalar(
        select(BankQuestion).where(
            BankQuestion.public_id == public_id, BankQuestion.bank_id == bank.id
        )
    )
    if question is None:
        raise NotFoundError("Question not found.")
    return question


# ---- serialisation ------------------------------------------------------------------------


def _counts(bank: QuestionBank) -> dict[str, int]:
    rows = db.session.execute(
        select(BankQuestion.status, func.count(BankQuestion.id))
        .where(BankQuestion.bank_id == bank.id)
        .group_by(BankQuestion.status)
    ).all()
    counts = dict(rows)
    return {"active": counts.get("active", 0), "retired": counts.get("retired", 0)}


def bank_dict(bank: QuestionBank) -> dict[str, Any]:
    return {
        "id": bank.public_id,
        "title": bank.title,
        "description": bank.description,
        "status": bank.status,
        "question_counts": _counts(bank),
        "lock_version": bank.lock_version,
        "archived_at": iso(bank.archived_at),
        "created_at": iso(bank.created_at),
        "updated_at": iso(bank.updated_at),
    }


def bank_detail(bank: QuestionBank, actor: User) -> dict[str, Any]:
    require(actor, P.QUESTION_BANKS_VIEW)
    return {
        **bank_dict(bank),
        "tags": sorted({t for q in bank.questions for t in q.tags or []}),
        "used_by": [
            {"assessment_id": a.id, "course_id": a.course_id, "title": a.title, "status": a.status}
            for a in referencing_assessments(bank)
        ],
        "answer_key_visible": _with_key(actor),
    }


def bank_question_dict(question: BankQuestion, *, with_key: bool) -> dict[str, Any]:
    data = {
        "id": question.public_id,
        "kind": question.kind,
        "graded": question.graded,
        "prompt": question.prompt,
        "help_text": question.help_text,
        "options": question.options or [],
        "settings": question.settings or {},
        "points": question.points,
        "required": question.required,
        "tags": question.tags or [],
        "status": question.status,
        "version": question.version,
        "lock_version": question.lock_version,
        "updated_at": iso(question.updated_at),
    }
    if with_key:
        data["correct"] = question.correct or []
        data["explanation"] = question.explanation
    return data


def list_banks(actor: User, args: dict[str, str]) -> tuple[list[dict], dict]:
    require(actor, P.QUESTION_BANKS_VIEW)
    stmt = select(QuestionBank).order_by(QuestionBank.title, QuestionBank.id)
    status = args.get("status")
    if status in ("active", "archived"):
        stmt = stmt.where(QuestionBank.status == status)
    q = (args.get("q") or "").strip()[:100]
    if q:
        stmt = stmt.where(QuestionBank.title.ilike(f"%{q}%"))
    page, size = _page(args)
    items, meta = paginate(stmt, page, size)
    return [bank_dict(b) for b in items], meta


def list_questions(bank: QuestionBank, actor: User, args: dict[str, str]) -> tuple[list, dict]:
    require(actor, P.QUESTION_BANKS_VIEW)
    stmt = select(BankQuestion).where(BankQuestion.bank_id == bank.id).order_by(BankQuestion.id)
    status = args.get("status")
    if status in ("active", "retired"):
        stmt = stmt.where(BankQuestion.status == status)
    if args.get("kind") in QUESTION_KINDS:
        stmt = stmt.where(BankQuestion.kind == args["kind"])
    q = (args.get("q") or "").strip()[:100]
    if q:
        stmt = stmt.where(BankQuestion.prompt.ilike(f"%{q}%"))
    tag = (args.get("tag") or "").strip().lower()
    page, size = _page(args)
    if tag:
        # Tags live in JSON; filter in Python (banks stay small enough for this).
        rows = [r for r in db.session.scalars(stmt) if tag in (r.tags or [])]
        total = len(rows)
        rows = rows[(page - 1) * size : page * size]
        meta = {"page": page, "page_size": size, "total": total}
    else:
        rows, meta = paginate(stmt, page, size)
    with_key = _with_key(actor)
    return [bank_question_dict(r, with_key=with_key) for r in rows], meta


def _page(args: dict[str, str]) -> tuple[int, int]:
    try:
        page = max(1, int(args.get("page", 1)))
        size = min(100, max(1, int(args.get("page_size", 50))))
    except (TypeError, ValueError):
        raise ValidationError(details={"page": ["Use whole numbers."]}) from None
    return page, size


# ---- selection rules ----------------------------------------------------------------------


def _clean_tags(value: Any, errors: dict, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 10:
        errors[field] = ["Use a list of at most 10 tags."]
        return []
    tags = []
    for tag in value:
        tag = tag.strip().lower() if isinstance(tag, str) else ""
        if not _TAG.match(tag):
            errors[field] = ["Tags are 1-40 lower-case letters, numbers, spaces, - or _."]
            return []
        if tag not in tags:
            tags.append(tag)
    return tags


def clean_selection(value: Any, errors: dict) -> list[dict[str, Any]] | None:
    """Validate selection rules; the banks must exist and be active."""
    if value is None or value == []:
        return None
    if not isinstance(value, list) or len(value) > MAX_RULES:
        errors["selection"] = [f"Use a list of at most {MAX_RULES} draws."]
        return None
    rules = []
    for i, rule in enumerate(value):
        if not isinstance(rule, dict) or set(rule) - {"bank_id", "count", "tags"}:
            errors["selection"] = [f"Draw {i + 1} is invalid."]
            return None
        bank = (
            db.session.scalar(select(QuestionBank).where(QuestionBank.public_id == rule["bank_id"]))
            if isinstance(rule.get("bank_id"), str)
            else None
        )
        if bank is None or bank.status != "active":
            errors["selection"] = [f"Draw {i + 1}: choose an active question bank."]
            return None
        count = rule.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_DRAW:
            errors["selection"] = [f"Draw {i + 1}: draw 1 to {MAX_DRAW} questions."]
            return None
        tags = _clean_tags(rule.get("tags"), errors, "selection")
        if "selection" in errors:
            return None
        rules.append({"bank_id": bank.public_id, "count": count, "tags": tags})
    return rules


def _pool(rule: dict[str, Any], excluded: set[int] = frozenset()) -> list[BankQuestion]:
    """Active questions of an active bank matching the rule (any of its tags), by id."""
    bank = db.session.scalar(select(QuestionBank).where(QuestionBank.public_id == rule["bank_id"]))
    if bank is None or bank.status != "active":
        return []
    rows = db.session.scalars(
        select(BankQuestion)
        .where(BankQuestion.bank_id == bank.id, BankQuestion.status == "active")
        .order_by(BankQuestion.id)
    )
    tags = set(rule.get("tags") or [])
    return [q for q in rows if q.id not in excluded and (not tags or tags & set(q.tags or []))]


def selection_problems(assessment: Assessment, excluded: set[int] = frozenset()) -> list[str]:
    """Why the draws couldn't be filled (empty when they can). ``excluded``: bank
    question ids to treat as unavailable (a pending retire/delete)."""
    problems = []
    per_bank: dict[str, tuple[set[int], int]] = {}
    for i, rule in enumerate(assessment.selection or []):
        pool = _pool(rule, excluded)
        if len(pool) < rule["count"]:
            problems.append(
                f"Draw {i + 1} needs {rule['count']} active question(s); {len(pool)} available."
            )
        ids, wanted = per_bank.get(rule["bank_id"], (set(), 0))
        per_bank[rule["bank_id"]] = (ids | {q.id for q in pool}, wanted + rule["count"])
    if not problems:
        for ids, wanted in per_bank.values():
            if len(ids) < wanted:
                problems.append(f"The draws from one bank need {wanted} different questions.")
    return problems


def selection_has_graded(assessment: Assessment) -> bool:
    return any(q.kind in GRADED_KINDS for r in assessment.selection or [] for q in _pool(r))


def draw(assessment: Assessment, rng: random.Random) -> list[dict[str, Any]]:
    """Copies of the questions drawn for one attempt (never the same question twice)."""
    drawn: list[dict[str, Any]] = []
    taken: set[int] = set()
    for rule in assessment.selection or []:
        pool = _pool(rule, taken)
        if len(pool) < rule["count"]:
            raise ConflictError(
                "This assessment can't be started right now: its question bank doesn't have "
                "enough questions. Please try again later."
            )
        for question in rng.sample(pool, rule["count"]):
            taken.add(question.id)
            drawn.append(
                question_copy(
                    question,
                    qid=f"b{question.id}",
                    source={
                        "type": "bank",
                        "bank_id": rule["bank_id"],
                        "question_id": question.public_id,
                        "version": question.version,
                    },
                )
            )
    return drawn


def referencing_assessments(bank: QuestionBank) -> list[Assessment]:
    rows = db.session.scalars(select(Assessment).where(Assessment.selection.is_not(None)))
    return [a for a in rows if any(r.get("bank_id") == bank.public_id for r in a.selection or [])]


def _guard_published(bank: QuestionBank, excluded: set[int], *, archiving: bool = False) -> None:
    """Refuse changes that would leave a published assessment unable to fill its draws."""
    blocked = []
    for assessment in referencing_assessments(bank):
        if assessment.status != "published":
            continue
        if archiving or selection_problems(assessment, excluded):
            blocked.append(assessment.title)
    if blocked:
        raise ConflictError(
            "Published assessments draw from these questions: "
            + ", ".join(sorted(blocked))
            + ". Change or unpublish them first.",
        )


# ---- commands -----------------------------------------------------------------------------


def _clean_bank(data: Any, bank: QuestionBank | None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    errors: dict[str, Any] = {}
    unknown = set(data) - BANK_FIELDS
    if unknown:
        errors["_unknown"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]
    clean: dict[str, Any] = {}
    for field, limit, required in (
        ("title", 200, bank is None),
        ("description", 1000, False),
    ):
        if field in data or required:
            value = data.get(field)
            if not isinstance(value, str) or (required and not value.strip()):
                errors[field] = ["This field is required." if required else "Must be text."]
            elif len(value.strip()) > limit or plain_text_problem(value):
                errors[field] = [f"Plain text of at most {limit} characters."]
            else:
                clean[field] = value.strip()
    if "status" in data:
        if data["status"] not in ("active", "archived"):
            errors["status"] = ["Use active or archived."]
        else:
            clean["status"] = data["status"]
    if errors:
        raise ValidationError("Some fields need attention.", details=errors)
    return clean


def create_bank(data: Any, actor: User) -> QuestionBank:
    require(actor, P.QUESTION_BANKS_VIEW, P.QUESTION_BANKS_MANAGE)
    clean = _clean_bank(data, None)
    clean.pop("status", None)
    bank = QuestionBank(public_id=new_id(), created_by_id=actor.id, **clean)
    db.session.add(bank)
    db.session.flush()
    audit_service.record(
        "question_bank.created",
        "question_bank",
        bank.id,
        actor=actor,
        details={"title": bank.title},
    )
    return bank


def update_bank(bank: QuestionBank, data: Any, actor: User) -> QuestionBank:
    require(actor, P.QUESTION_BANKS_VIEW, P.QUESTION_BANKS_MANAGE)
    clean = _clean_bank(data, bank)
    check_lock(bank, data)
    status = clean.pop("status", bank.status)
    if status != bank.status:
        if status == "archived":
            _guard_published(bank, set(), archiving=True)
            bank.archived_at = datetime.now(UTC)
        else:
            bank.archived_at = None
        bank.status = status
    for key, value in clean.items():
        setattr(bank, key, value)
    bank.lock_version += 1
    db.session.flush()
    audit_service.record(
        "question_bank.updated",
        "question_bank",
        bank.id,
        actor=actor,
        details={"title": bank.title, "status": bank.status},
    )
    return bank


def delete_bank(bank: QuestionBank, actor: User) -> None:
    require(actor, P.QUESTION_BANKS_VIEW, P.QUESTION_BANKS_MANAGE)
    used = referencing_assessments(bank)
    if used:
        raise ConflictError(
            "Assessments draw from this bank: "
            + ", ".join(sorted(a.title for a in used))
            + ". Archive it instead, or remove it from their draws first."
        )
    audit_service.record(
        "question_bank.deleted",
        "question_bank",
        bank.id,
        actor=actor,
        details={"title": bank.title},
    )
    db.session.delete(bank)
    db.session.flush()


_CONTENT = ("kind", "prompt", "help_text", "options", "correct", "explanation", "settings")


def save_bank_question(
    bank: QuestionBank, data: Any, actor: User, question: BankQuestion | None = None
) -> BankQuestion:
    require(actor, P.QUESTION_BANKS_VIEW, P.QUESTION_BANKS_MANAGE)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    if bank.status == "archived":
        raise ConflictError("Restore this bank before changing its questions.")
    if question is not None:
        check_lock(question, data)
    errors: dict[str, Any] = {}
    tags = (
        _clean_tags(data["tags"], errors, "tags")
        if "tags" in data
        else (question.tags if question else [])
    )
    status = data.get("status", question.status if question else "active")
    if status not in ("active", "retired"):
        errors["status"] = ["Use active or retired."]
    question_data = {k: v for k, v in data.items() if k not in ("tags", "status", "lock_version")}
    try:
        clean = clean_question(QUESTION_KINDS, question_data, question)
    except ValidationError as exc:
        raise ValidationError(
            "Some fields need attention.", details={**(exc.details or {}), **errors}
        ) from None
    if errors:
        raise ValidationError("Some fields need attention.", details=errors)
    if question is not None and status == "retired" and question.status == "active":
        _guard_published(bank, {question.id})
    created = question is None
    if question is None:
        question = BankQuestion(bank_id=bank.id, public_id=new_id(), version=1, lock_version=1)
        db.session.add(question)
    else:
        if any(getattr(question, k) != clean[k] for k in _CONTENT) or (
            question.points != clean["points"] or question.required != clean["required"]
        ):
            question.version += 1  # attempts already started keep their own copy
        question.lock_version += 1
    for key, value in clean.items():
        setattr(question, key, value)
    question.tags = tags
    question.status = status
    db.session.flush()
    audit_service.record(
        "question_bank.question_created" if created else "question_bank.question_updated",
        "question_bank",
        bank.id,
        actor=actor,
        details={"question_id": question.public_id, "version": question.version},
    )
    return question


def delete_bank_question(bank: QuestionBank, question: BankQuestion, actor: User) -> None:
    require(actor, P.QUESTION_BANKS_VIEW, P.QUESTION_BANKS_MANAGE)
    _guard_published(bank, {question.id})
    audit_service.record(
        "question_bank.question_deleted",
        "question_bank",
        bank.id,
        actor=actor,
        details={"question_id": question.public_id},
    )
    db.session.delete(question)
    db.session.flush()
