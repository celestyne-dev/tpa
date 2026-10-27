"""Written exercises and assessments.

- ``quiz``: graded. Single choice, multiple select and true/false questions are scored
  automatically; written answers in a quiz are kept but never scored.
- ``reflection``: ungraded written answers. Submitting counts as done; nothing is marked
  right or wrong.
- ``self_assessment``: ungraded rating scales (and optional notes) the learner uses to
  reflect on their own progress.

The answer key (``AssessmentQuestion.correct``) and explanations never leave the server
before an attempt is submitted; afterwards they are revealed according to
``show_answers``. Every submission is validated and scored server-side.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...extensions import db
from ...models import (
    Assessment,
    AssessmentAttempt,
    AssessmentQuestion,
    Course,
    CourseEnrollment,
    CourseLesson,
    User,
)
from ...models.courses import ASSESSMENT_KINDS, QUESTION_KINDS, SHOW_ANSWERS
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from ...utils.validation import plain_text_problem
from .. import audit_service
from ..serializers import iso
from .admin import require

GRADED_KINDS = ("single_choice", "multiple_select", "true_false")
KINDS_BY_ASSESSMENT = {
    "quiz": QUESTION_KINDS,
    "reflection": ("short_text", "rating"),
    "self_assessment": ("rating", "short_text"),
}
TRUE_FALSE = [{"id": "true", "text": "True"}, {"id": "false", "text": "False"}]
_OPTION_ID = re.compile(r"^[a-z0-9]{1,8}$")


def get_assessment(course: Course, assessment_id: int) -> Assessment:
    assessment = db.session.get(Assessment, assessment_id)
    if assessment is None or assessment.course_id != course.id:
        raise NotFoundError("Assessment not found.")
    return assessment


def get_question(assessment: Assessment, question_id: int) -> AssessmentQuestion:
    question = db.session.get(AssessmentQuestion, question_id)
    if question is None or question.assessment_id != assessment.id:
        raise NotFoundError("Question not found.")
    return question


def _attempt_count(assessment: Assessment) -> int:
    return (
        db.session.scalar(
            select(func.count(AssessmentAttempt.id)).where(
                AssessmentAttempt.assessment_id == assessment.id
            )
        )
        or 0
    )


# ---- serialisation ----------------------------------------------------------------------


def assessment_summary(assessment: Assessment) -> dict[str, Any]:
    return {
        "id": assessment.id,
        "kind": assessment.kind,
        "graded": assessment.graded,
        "title": assessment.title,
        "status": assessment.status,
        "lesson_id": assessment.lesson_id,
        "question_count": len(assessment.questions),
        "required_for_completion": assessment.required_for_completion,
        "passing_score": assessment.passing_score,
        "max_attempts": assessment.max_attempts,
        "show_answers": assessment.show_answers,
        "position": assessment.position,
    }


def question_admin_dict(question: AssessmentQuestion, *, with_key: bool) -> dict[str, Any]:
    data = {
        "id": question.id,
        "kind": question.kind,
        "graded": question.graded,
        "prompt": question.prompt,
        "help_text": question.help_text,
        "options": question.options or [],
        "settings": question.settings or {},
        "points": question.points,
        "required": question.required,
        "position": question.position,
    }
    if with_key:
        data["correct"] = question.correct or []
        data["explanation"] = question.explanation
    return data


def assessment_admin_detail(assessment: Assessment, actor: User) -> dict[str, Any]:
    with_key = P.COURSES_MANAGE_ASSESSMENTS.value in effective_permissions(actor)
    return {
        **assessment_summary(assessment),
        "description": assessment.description,
        "attempt_count": _attempt_count(assessment),
        "questions": [question_admin_dict(q, with_key=with_key) for q in assessment.questions],
        "answer_key_visible": with_key,
    }


def _learner_question(question: AssessmentQuestion) -> dict[str, Any]:
    """What a learner sees before submitting: never the answer key or explanations."""
    data = {
        "id": question.id,
        "kind": question.kind,
        "prompt": question.prompt,
        "help_text": question.help_text,
        "required": question.required,
        "graded": question.graded,
    }
    if question.kind in ("single_choice", "multiple_select", "true_false"):
        data["options"] = [{"id": o["id"], "text": o["text"]} for o in question.options or []]
    if question.kind == "rating":
        settings = question.settings or {}
        data["scale"] = settings.get("scale", 5)
        data["min_label"] = settings.get("min_label", "")
        data["max_label"] = settings.get("max_label", "")
    if question.kind == "short_text":
        data["max_length"] = (question.settings or {}).get("max_length", 2000)
    return data


def reveal_answers(assessment: Assessment, attempt: AssessmentAttempt) -> bool:
    if assessment.show_answers == "after_submit":
        return True
    if assessment.show_answers == "after_pass":
        return bool(attempt.passed)
    return False


def attempt_dict(assessment: Assessment, attempt: AssessmentAttempt) -> dict[str, Any]:
    reveal = reveal_answers(assessment, attempt)
    results = []
    for item in attempt.results or []:
        entry = {
            "question_id": item["question_id"],
            "kind": item["kind"],
            "prompt": item["prompt"],
            "answer": item.get("answer"),
            "graded": item.get("graded", False),
        }
        if item.get("graded") and assessment.show_answers != "never":
            entry["correct"] = item.get("correct")
            entry["points"] = item.get("points", 0)
        if reveal and item.get("graded"):
            entry["correct_answer"] = item.get("correct_answer")
            entry["options"] = item.get("options")
        if reveal and item.get("explanation"):
            entry["explanation"] = item["explanation"]
        results.append(entry)
    return {
        "id": attempt.id,
        "attempt_number": attempt.attempt_number,
        "score": attempt.score,
        "max_score": attempt.max_score,
        "percent": attempt.percent,
        "passed": attempt.passed,
        "graded": assessment.graded,
        "answers_revealed": reveal,
        "results": results,
        "submitted_at": iso(attempt.submitted_at),
    }


def learner_assessment(assessment: Assessment, enrollment: CourseEnrollment) -> dict[str, Any]:
    attempts = list(
        db.session.scalars(
            select(AssessmentAttempt)
            .where(
                AssessmentAttempt.assessment_id == assessment.id,
                AssessmentAttempt.enrollment_id == enrollment.id,
            )
            .order_by(AssessmentAttempt.attempt_number)
        )
    )
    used = len(attempts)
    return {
        "id": assessment.id,
        "kind": assessment.kind,
        "graded": assessment.graded,
        "title": assessment.title,
        "description": assessment.description,
        "lesson_id": assessment.lesson_id,
        "passing_score": assessment.passing_score if assessment.graded else None,
        "max_attempts": assessment.max_attempts,
        "attempts_used": used,
        "attempts_left": None
        if assessment.max_attempts is None
        else max(0, assessment.max_attempts - used),
        "required_for_completion": assessment.required_for_completion,
        "status": assessment_state(assessment, attempts),
        "questions": [_learner_question(q) for q in assessment.questions],
        "attempts": [attempt_dict(assessment, a) for a in reversed(attempts)],
    }


def assessment_state(assessment: Assessment, attempts: list[AssessmentAttempt]) -> str:
    """not_started | submitted (ungraded) | passed | failed (latest graded, none passed)."""
    if not attempts:
        return "not_started"
    if not assessment.graded:
        return "submitted"
    return "passed" if any(a.passed for a in attempts) else "failed"


# ---- admin commands ---------------------------------------------------------------------

ASSESSMENT_FIELDS = {
    "kind",
    "title",
    "description",
    "lesson_id",
    "passing_score",
    "max_attempts",
    "show_answers",
    "required_for_completion",
}


def save_assessment(
    course: Course, data: dict[str, Any], actor: User, assessment: Assessment | None = None
) -> Assessment:
    require(actor, P.COURSES_MANAGE_ASSESSMENTS)
    if course.status == "archived":
        raise ConflictError("Restore this course before changing its assessments.")
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    errors: dict[str, Any] = {}
    unknown = set(data) - ASSESSMENT_FIELDS
    if unknown:
        errors["_unknown"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]
    kind = data.get("kind", assessment.kind if assessment else "quiz")
    if kind not in ASSESSMENT_KINDS:
        errors["kind"] = [f"Choose one of: {', '.join(ASSESSMENT_KINDS)}."]
    elif assessment is not None and kind != assessment.kind and _attempt_count(assessment):
        errors["kind"] = ["Learners have attempted this; its type can't change."]
    elif assessment is not None and kind != assessment.kind:
        allowed = KINDS_BY_ASSESSMENT[kind]
        if any(q.kind not in allowed for q in assessment.questions):
            errors["kind"] = ["Remove questions this type doesn't support first."]
    for field, limit, required in (
        ("title", 200, assessment is None),
        ("description", 1000, False),
    ):
        if field in data or required:
            value = data.get(field)
            if not isinstance(value, str) or (required and not value.strip()):
                errors[field] = ["This field is required." if required else "Must be text."]
            elif len(value.strip()) > limit or plain_text_problem(value):
                errors[field] = [f"Plain text of at most {limit} characters."]
    if data.get("lesson_id") is not None:
        lesson = (
            db.session.get(CourseLesson, data["lesson_id"])
            if isinstance(data["lesson_id"], int)
            else None
        )
        if lesson is None or lesson.course_id != course.id:
            errors["lesson_id"] = ["Choose a lesson of this course."]
    graded = kind == "quiz"
    passing = data.get(
        "passing_score", assessment.passing_score if assessment else (70 if graded else None)
    )
    if graded:
        if not isinstance(passing, int) or isinstance(passing, bool) or not 0 <= passing <= 100:
            errors["passing_score"] = ["Use a passing score from 0 to 100 percent."]
    else:
        passing = None
    if (
        "max_attempts" in data
        and data["max_attempts"] is not None
        and (
            not isinstance(data["max_attempts"], int)
            or isinstance(data["max_attempts"], bool)
            or not 1 <= data["max_attempts"] <= 100
        )
    ):
        errors["max_attempts"] = ["Use 1 to 100 attempts, or leave empty for unlimited."]
    if "show_answers" in data and data["show_answers"] not in SHOW_ANSWERS:
        errors["show_answers"] = [f"Choose one of: {', '.join(SHOW_ANSWERS)}."]
    if "required_for_completion" in data and not isinstance(data["required_for_completion"], bool):
        errors["required_for_completion"] = ["Must be true or false."]
    if errors:
        raise ValidationError("Some fields need attention.", details=errors)
    created = assessment is None
    if assessment is None:
        last = db.session.scalar(
            select(func.max(Assessment.position)).where(Assessment.course_id == course.id)
        )
        assessment = Assessment(
            course_id=course.id, position=(last if last is not None else -1) + 1
        )
        db.session.add(assessment)
    assessment.kind = kind
    assessment.passing_score = passing
    for field in ("title", "description"):
        if field in data:
            setattr(assessment, field, data[field].strip())
    for field in ("lesson_id", "max_attempts", "show_answers", "required_for_completion"):
        if field in data:
            setattr(assessment, field, data[field])
    db.session.flush()
    audit_service.record(
        "course.assessment_created" if created else "course.assessment_updated",
        "course",
        course.id,
        actor=actor,
        details={"assessment_id": assessment.id, "title": assessment.title},
    )
    return assessment


def set_assessment_status(course: Course, assessment: Assessment, status: str, actor: User) -> None:
    require(actor, P.COURSES_PUBLISH)
    if status not in ("draft", "published"):
        raise ValidationError(details={"status": ["Use draft or published."]})
    if status == "published":
        if not assessment.questions:
            raise ValidationError("Add at least one question first.")
        if assessment.graded and not any(q.graded for q in assessment.questions):
            raise ValidationError("A quiz needs at least one automatically scored question.")
    assessment.status = status
    audit_service.record(
        "course.assessment_" + ("published" if status == "published" else "unpublished"),
        "course",
        course.id,
        actor=actor,
        details={"assessment_id": assessment.id},
    )


def delete_assessment(course: Course, assessment: Assessment, actor: User) -> None:
    require(actor, P.COURSES_MANAGE_ASSESSMENTS)
    if _attempt_count(assessment):
        raise ConflictError("Learners have attempted this assessment. Unpublish it instead.")
    audit_service.record(
        "course.assessment_deleted",
        "course",
        course.id,
        actor=actor,
        details={"assessment_id": assessment.id, "title": assessment.title},
    )
    db.session.delete(assessment)
    db.session.flush()
    remaining = [a for a in course.assessments if a.id != assessment.id]
    _renumber(remaining)


def _renumber(rows: list) -> None:
    for index, row in enumerate(rows):
        row.position = -(index + 1)
    db.session.flush()
    for index, row in enumerate(rows):
        row.position = index
    db.session.flush()


def reorder_assessments(course: Course, ids: Any, actor: User) -> None:
    require(actor, P.COURSES_MANAGE_ASSESSMENTS)
    current = {a.id: a for a in course.assessments}
    if not isinstance(ids, list) or sorted(ids, key=str) != sorted(current, key=str):
        raise ValidationError(details={"ids": ["Include every assessment of this course once."]})
    _renumber([current[i] for i in ids])
    db.session.expire(course, ["assessments"])


QUESTION_FIELDS = {
    "kind",
    "prompt",
    "help_text",
    "options",
    "correct",
    "explanation",
    "settings",
    "points",
    "required",
}


def _clean_question(
    assessment: Assessment, data: dict, question: AssessmentQuestion | None
) -> dict:
    errors: dict[str, Any] = {}
    unknown = set(data) - QUESTION_FIELDS
    if unknown:
        errors["_unknown"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]
    kind = data.get("kind", question.kind if question else None)
    allowed = KINDS_BY_ASSESSMENT[assessment.kind]
    if kind not in allowed:
        errors["kind"] = [f"This assessment accepts: {', '.join(allowed)}."]
        raise ValidationError("Some fields need attention.", details=errors)
    clean: dict[str, Any] = {"kind": kind}
    prompt = data.get("prompt", question.prompt if question else None)
    if (
        not isinstance(prompt, str)
        or not prompt.strip()
        or len(prompt.strip()) > 1000
        or plain_text_problem(prompt)
    ):
        errors["prompt"] = ["A plain-text question of at most 1000 characters is required."]
    else:
        clean["prompt"] = prompt.strip()
    for field, limit in (("help_text", 500), ("explanation", 1000)):
        value = data.get(field, getattr(question, field) if question else "")
        if not isinstance(value, str) or len(value) > limit or plain_text_problem(value):
            errors[field] = [f"Plain text of at most {limit} characters."]
        else:
            clean[field] = value.strip()
    options = data.get("options", question.options if question else [])
    correct = data.get("correct", question.correct if question else [])
    settings = data.get("settings", question.settings if question else {})
    if kind == "true_false":
        options = TRUE_FALSE
        if correct in ([True], [False]):
            correct = ["true" if correct[0] else "false"]
        if correct not in (["true"], ["false"]):
            errors["correct"] = ["Choose whether the statement is true or false."]
    elif kind in ("single_choice", "multiple_select"):
        if not isinstance(options, list) or not 2 <= len(options) <= 10:
            errors["options"] = ["Add between 2 and 10 options."]
            options = []
        clean_options, seen = [], set()
        for i, option in enumerate(options):
            if not isinstance(option, dict) or set(option) - {"id", "text"}:
                errors["options"] = [f"Option {i + 1} is invalid."]
                continue
            oid, text = option.get("id"), option.get("text")
            if not isinstance(oid, str) or not _OPTION_ID.match(oid) or oid in seen:
                errors["options"] = ["Each option needs its own short id (letters/numbers)."]
            if (
                not isinstance(text, str)
                or not text.strip()
                or len(text) > 300
                or plain_text_problem(text)
            ):
                errors["options"] = [f"Option {i + 1} needs plain text of at most 300 characters."]
            seen.add(oid)
            clean_options.append({"id": oid, "text": (text or "").strip()})
        options = clean_options
        if (
            not isinstance(correct, list)
            or not all(isinstance(c, str) for c in correct)
            or not set(correct) <= seen
            or not correct
        ):
            errors["correct"] = ["Mark the correct option(s)."]
        elif kind == "single_choice" and len(correct) != 1:
            errors["correct"] = ["Single-choice questions have exactly one correct option."]
        else:
            correct = sorted(set(correct))
    else:
        options, correct = [], []
    if kind == "short_text":
        max_length = (
            (settings or {}).get("max_length", 2000) if isinstance(settings, dict) else None
        )
        if (
            not isinstance(max_length, int)
            or isinstance(max_length, bool)
            or not 50 <= max_length <= 5000
        ):
            errors["settings"] = ["Answer length must be between 50 and 5000 characters."]
        settings = {"max_length": max_length}
    elif kind == "rating":
        settings = settings if isinstance(settings, dict) else {}
        scale = settings.get("scale", 5)
        if not isinstance(scale, int) or isinstance(scale, bool) or not 3 <= scale <= 10:
            errors["settings"] = ["Use a scale from 3 to 10."]
        labels = {}
        for key in ("min_label", "max_label"):
            value = settings.get(key, "")
            if not isinstance(value, str) or len(value) > 60 or plain_text_problem(value):
                errors["settings"] = ["Scale labels are plain text of at most 60 characters."]
            labels[key] = (value or "").strip()
        settings = {"scale": scale, **labels}
    else:
        settings = {}
    points = data.get("points", question.points if question else 1)
    if kind not in GRADED_KINDS:
        points = 0
    elif not isinstance(points, int) or isinstance(points, bool) or not 0 <= points <= 100:
        errors["points"] = ["Use 0 to 100 points."]
    required = data.get("required", question.required if question else True)
    if not isinstance(required, bool):
        errors["required"] = ["Must be true or false."]
    if errors:
        raise ValidationError("Some fields need attention.", details=errors)
    return clean | {
        "options": options,
        "correct": correct,
        "settings": settings,
        "points": points,
        "required": required,
    }


def save_question(
    assessment: Assessment,
    data: dict[str, Any],
    actor: User,
    question: AssessmentQuestion | None = None,
) -> AssessmentQuestion:
    require(actor, P.COURSES_MANAGE_ASSESSMENTS)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    clean = _clean_question(assessment, data, question)
    created = question is None
    if question is None:
        last = db.session.scalar(
            select(func.max(AssessmentQuestion.position)).where(
                AssessmentQuestion.assessment_id == assessment.id
            )
        )
        question = AssessmentQuestion(
            assessment_id=assessment.id, position=(last if last is not None else -1) + 1
        )
        db.session.add(question)
    for key, value in clean.items():
        setattr(question, key, value)
    db.session.flush()
    audit_service.record(
        "course.question_created" if created else "course.question_updated",
        "course",
        assessment.course_id,
        actor=actor,
        details={"assessment_id": assessment.id, "question_id": question.id},
    )
    return question


def delete_question(assessment: Assessment, question: AssessmentQuestion, actor: User) -> None:
    require(actor, P.COURSES_MANAGE_ASSESSMENTS)
    if assessment.status == "published" and len(assessment.questions) == 1:
        raise ConflictError("A published assessment needs at least one question.")
    audit_service.record(
        "course.question_deleted",
        "course",
        assessment.course_id,
        actor=actor,
        details={"assessment_id": assessment.id, "question_id": question.id},
    )
    db.session.delete(question)
    db.session.flush()
    _renumber([q for q in assessment.questions if q.id != question.id])


def reorder_questions(assessment: Assessment, ids: Any, actor: User) -> None:
    require(actor, P.COURSES_MANAGE_ASSESSMENTS)
    current = {q.id: q for q in assessment.questions}
    if not isinstance(ids, list) or sorted(ids, key=str) != sorted(current, key=str):
        raise ValidationError(details={"ids": ["Include every question once."]})
    _renumber([current[i] for i in ids])
    db.session.expire(assessment, ["questions"])


# ---- submissions ------------------------------------------------------------------------


class AttemptsExhaustedError(ConflictError):
    code = "attempts_exhausted"
    message = "You have used all attempts for this assessment."


def _check_answer(question: AssessmentQuestion, value: Any, errors: dict) -> Any:
    key = str(question.id)
    missing = value is None or value == "" or value == []
    if missing:
        if question.required:
            errors[key] = ["Please answer this question."]
        return None
    option_ids = {o["id"] for o in question.options or []}
    if question.kind in ("single_choice", "true_false"):
        if not isinstance(value, str) or value not in option_ids:
            errors[key] = ["Choose one of the options."]
            return None
        return value
    if question.kind == "multiple_select":
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(v, str) for v in value)
            or not set(value) <= option_ids
        ):
            errors[key] = ["Choose one or more of the options."]
            return None
        return sorted(set(value))
    if question.kind == "short_text":
        limit = (question.settings or {}).get("max_length", 2000)
        if not isinstance(value, str) or len(value) > limit or plain_text_problem(value):
            errors[key] = [f"Write plain text of at most {limit} characters."]
            return None
        return value.strip()
    if question.kind == "rating":
        scale = (question.settings or {}).get("scale", 5)
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= scale:
            errors[key] = [f"Choose a number from 1 to {scale}."]
            return None
        return value
    return None


def submit(assessment: Assessment, enrollment: CourseEnrollment, answers: Any) -> AssessmentAttempt:
    """Validate, score and store one attempt. Concurrent duplicates fail cleanly."""
    if not isinstance(answers, dict):
        raise ValidationError(details={"answers": ["Send your answers."]})
    used = (
        db.session.scalar(
            select(func.count(AssessmentAttempt.id)).where(
                AssessmentAttempt.assessment_id == assessment.id,
                AssessmentAttempt.enrollment_id == enrollment.id,
            )
        )
        or 0
    )
    if assessment.max_attempts is not None and used >= assessment.max_attempts:
        raise AttemptsExhaustedError()
    questions = {str(q.id): q for q in assessment.questions}
    unknown = set(answers) - set(questions)
    if unknown:
        raise ValidationError(details={"answers": ["Some answers don't match this assessment."]})
    errors: dict[str, Any] = {}
    clean = {key: _check_answer(q, answers.get(key), errors) for key, q in questions.items()}
    if errors:
        raise ValidationError("Some answers need attention.", details={"answers": errors})
    score = max_score = 0
    results = []
    for key, question in questions.items():
        answer = clean[key]
        entry: dict[str, Any] = {
            "question_id": question.id,
            "kind": question.kind,
            "prompt": question.prompt,
            "answer": answer,
            "graded": assessment.graded and question.graded,
            "explanation": question.explanation,
        }
        if entry["graded"]:
            expected = sorted(question.correct or [])
            given = (
                sorted(answer)
                if isinstance(answer, list)
                else ([answer] if answer is not None else [])
            )
            correct = given == expected
            max_score += question.points
            awarded = question.points if correct else 0
            score += awarded
            entry |= {
                "correct": correct,
                "points": awarded,
                "correct_answer": expected,
                "options": question.options or [],
            }
        results.append(entry)
    percent = passed = None
    if assessment.graded:
        percent = round(100 * score / max_score) if max_score else 100
        passed = percent >= (assessment.passing_score or 0)
    attempt = AssessmentAttempt(
        assessment_id=assessment.id,
        enrollment_id=enrollment.id,
        attempt_number=used + 1,
        answers=clean,
        results=results,
        score=score,
        max_score=max_score,
        percent=percent,
        passed=passed,
    )
    try:
        with db.session.begin_nested():
            db.session.add(attempt)
            db.session.flush()
    except IntegrityError:
        raise ConflictError(
            "This attempt was already submitted. Refresh to see your result."
        ) from None
    return attempt
