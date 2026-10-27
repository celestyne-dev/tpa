"""Lesson content blocks.

Lessons reuse the article blocks (text, headings, lists, quotes, callouts, images,
galleries, tables, dividers) validated by ``app/cms/blocks.py`` and add written-learning
blocks. Video, embeds and promotional blocks are not accepted in lessons.

- ``key_points``: highlighted takeaways;
- ``example``: an example or case study;
- ``exercise``: a reflection question or task (``id`` is stable so progress can record
  that the learner did it; ``required`` exercises must be marked done to complete the
  lesson);
- ``checklist``: items a learner can tick while reading;
- ``download``: one of the course product's private files (delivered through the
  secure download authorisation, never by a public address);
- ``further_reading``: links to articles, resources or external reading.
"""

from __future__ import annotations

import re
from typing import Any

from ...cms.blocks import blocks_word_count, safe_href, validate_blocks
from ...utils.errors import ValidationError
from ...utils.validation import plain_text_problem

ARTICLE_BLOCKS = (
    "paragraph",
    "heading",
    "quote",
    "pullquote",
    "callout",
    "list",
    "divider",
    "image",
    "gallery",
    "table",
)
LESSON_BLOCKS = ("key_points", "example", "exercise", "checklist", "download", "further_reading")
EXAMPLE_VARIANTS = ("example", "case_study")
MAX_LESSON_BLOCKS = 300
WORDS_PER_MINUTE = 225
_EXERCISE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_FILE_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

_FIELDS: dict[str, set[str]] = {
    "key_points": {"title", "items"},
    "example": {"title", "text", "variant"},
    "exercise": {"id", "title", "prompt", "required", "allow_response"},
    "checklist": {"title", "items"},
    "download": {"file_id", "title", "description"},
    "further_reading": {"title", "items"},
}


def _text(value: Any, label: str, limit: int, errors: list[str], required: bool) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            errors.append(f"{label} is required.")
        return None
    if not isinstance(value, str):
        errors.append(f"{label} must be text.")
        return None
    value = value.strip()
    if len(value) > limit:
        errors.append(f"{label} must be at most {limit} characters.")
    if problem := plain_text_problem(value):
        errors.append(f"{label}: {problem}")
    return value


def _items(value: Any, label: str, low: int, high: int, limit: int, errors: list[str]) -> list:
    if not isinstance(value, list) or not low <= len(value) <= high:
        errors.append(f"{label} needs between {low} and {high} items.")
        return []
    out = []
    for i, item in enumerate(value):
        if (text := _text(item, f"Item {i + 1}", limit, errors, True)) is not None:
            out.append(text)
    return out


def _lesson_block(block: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    kind = block["type"]
    unknown = set(block) - {"type"} - _FIELDS[kind]
    if unknown:
        errors.append(f"Unknown field(s): {', '.join(sorted(unknown))}.")
    out: dict[str, Any] = {"type": kind}

    def put(field: str, label: str, limit: int, required: bool = False) -> None:
        if (value := _text(block.get(field), label, limit, errors, required)) is not None:
            out[field] = value

    if kind == "key_points":
        put("title", "Title", 120)
        out["items"] = _items(block.get("items"), "Key points", 1, 12, 500, errors)
    elif kind == "example":
        put("title", "Title", 160, True)
        put("text", "Text", 5000, True)
        variant = block.get("variant", "example")
        if variant not in EXAMPLE_VARIANTS:
            errors.append("Choose example or case study.")
        out["variant"] = variant
    elif kind == "exercise":
        exercise_id = block.get("id")
        if not isinstance(exercise_id, str) or not _EXERCISE_ID.match(exercise_id):
            errors.append("Exercise id must be short lowercase letters, numbers and hyphens.")
        out["id"] = exercise_id
        put("title", "Title", 160)
        put("prompt", "Prompt", 2000, True)
        for flag, default in (("required", False), ("allow_response", True)):
            value = block.get(flag, default)
            if not isinstance(value, bool):
                errors.append(f"{flag.replace('_', ' ').capitalize()} must be true or false.")
            out[flag] = bool(value)
    elif kind == "checklist":
        put("title", "Title", 160)
        out["items"] = _items(block.get("items"), "Checklist", 1, 30, 300, errors)
    elif kind == "download":
        file_id = block.get("file_id")
        if not isinstance(file_id, str) or not _FILE_ID.match(file_id):
            errors.append("Choose a worksheet file.")
        out["file_id"] = file_id
        put("title", "Title", 160)
        put("description", "Description", 400)
    elif kind == "further_reading":
        put("title", "Title", 120)
        items = block.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 12:
            errors.append("Further reading needs between 1 and 12 links.")
            items = []
        clean = []
        for i, item in enumerate(items):
            if not isinstance(item, dict) or set(item) - {"label", "href", "note"}:
                errors.append(f"Link {i + 1} is invalid.")
                continue
            entry: dict[str, Any] = {}
            if label := _text(item.get("label"), f"Link {i + 1} label", 200, errors, True):
                entry["label"] = label
            href = item.get("href")
            if not isinstance(href, str) or len(href) > 500 or not safe_href(href.strip()):
                errors.append(f"Link {i + 1} must be a site path or https:// URL.")
            else:
                entry["href"] = href.strip()
            if note := _text(item.get("note"), f"Link {i + 1} note", 300, errors, False):
                entry["note"] = note
            clean.append(entry)
        out["items"] = clean
    return out


def validate_lesson_blocks(blocks: Any, *, file_ids: set[str] | None = None) -> list[dict]:
    """Validate lesson content. ``file_ids``: public ids of files a download may use."""
    if not isinstance(blocks, list):
        raise ValidationError(details={"body": ["Content must be a list of blocks."]})
    if len(blocks) > MAX_LESSON_BLOCKS:
        raise ValidationError(details={"body": [f"At most {MAX_LESSON_BLOCKS} blocks."]})
    cleaned: list[dict[str, Any]] = []
    problems: dict[str, list[str]] = {}
    exercise_ids: set[str] = set()
    for index, block in enumerate(blocks):
        errors: list[str] = []
        kind = block.get("type") if isinstance(block, dict) else None
        if kind in LESSON_BLOCKS:
            out = _lesson_block(block, errors)
            if kind == "exercise" and isinstance(out.get("id"), str):
                if out["id"] in exercise_ids:
                    errors.append("Each exercise needs its own id.")
                exercise_ids.add(out["id"])
            if kind == "download" and isinstance(out.get("file_id"), str):
                if file_ids is None:
                    errors.append("Link the course to a product with files to add downloads.")
                elif out["file_id"] not in file_ids:
                    errors.append("This file is not one of the course's worksheets.")
        elif kind in ARTICLE_BLOCKS:
            try:
                out = validate_blocks([block])[0]
            except ValidationError as exc:
                details = exc.details.get("body") if isinstance(exc.details, dict) else None
                found = details.get("0") if isinstance(details, dict) else None
                errors.extend(found or [exc.message])
                out = {"type": kind}
        else:
            allowed = ", ".join(ARTICLE_BLOCKS + LESSON_BLOCKS)
            problems[str(index)] = [f"Unknown block type. Use one of: {allowed}."]
            continue
        if errors:
            problems[str(index)] = errors
        cleaned.append(out)
    if problems:
        raise ValidationError("Some content blocks are invalid.", details={"body": problems})
    return cleaned


def lesson_word_count(blocks: list[dict[str, Any]]) -> int:
    words = blocks_word_count(blocks)
    count = lambda text: len(str(text or "").split())  # noqa: E731
    for block in blocks or []:
        kind = block.get("type")
        if kind in ("key_points", "checklist"):
            words += count(block.get("title")) + sum(count(i) for i in block.get("items", []))
        elif kind == "example":
            words += count(block.get("title")) + count(block.get("text"))
        elif kind == "exercise":
            words += count(block.get("title")) + count(block.get("prompt"))
    return words


def reading_minutes(blocks: list[dict[str, Any]]) -> int:
    return max(1, round(lesson_word_count(blocks) / WORDS_PER_MINUTE))


def exercises(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [b for b in blocks or [] if b.get("type") == "exercise"]


def required_exercise_ids(blocks: list[dict[str, Any]]) -> set[str]:
    return {b["id"] for b in exercises(blocks) if b.get("required")}


def download_file_ids(blocks: list[dict[str, Any]]) -> list[str]:
    return [b["file_id"] for b in blocks or [] if b.get("type") == "download"]
