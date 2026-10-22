"""Structured article content blocks.

Blocks are plain data rendered by React as text; no HTML or scripts are
accepted. Unknown block types and unknown fields are rejected.
"""

from __future__ import annotations

from typing import Any

from ..utils.errors import ValidationError
from ..utils.validation import plain_text_problem

MAX_BLOCKS = 300
CALLOUT_TONES = ("info", "tip", "warning")

# field -> (required, max_length)
_TEXT_FIELDS: dict[str, dict[str, tuple[bool, int]]] = {
    "paragraph": {"text": (True, 5000)},
    "heading": {"text": (True, 200)},
    "quote": {"text": (True, 1000), "cite": (False, 200)},
    "callout": {"text": (True, 1000), "title": (False, 120)},
    "list": {},
    "divider": {},
}
_EXTRA_FIELDS = {"heading": {"level"}, "list": {"items", "ordered"}, "callout": {"tone"}}
BLOCK_TYPES = tuple(_TEXT_FIELDS)


def _text(value: Any, label: str, max_len: int, errors: list[str], required: bool) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            errors.append(f"{label} is required.")
        return None
    if not isinstance(value, str):
        errors.append(f"{label} must be text.")
        return None
    value = value.strip()
    if len(value) > max_len:
        errors.append(f"{label} must be at most {max_len} characters.")
    problem = plain_text_problem(value)
    if problem:
        errors.append(f"{label}: {problem}")
    return value


def validate_blocks(blocks: Any) -> list[dict[str, Any]]:
    if not isinstance(blocks, list):
        raise ValidationError(details={"body": ["Content must be a list of blocks."]})
    if len(blocks) > MAX_BLOCKS:
        raise ValidationError(details={"body": [f"At most {MAX_BLOCKS} blocks are allowed."]})

    cleaned: list[dict[str, Any]] = []
    problems: dict[str, list[str]] = {}
    for index, block in enumerate(blocks):
        errors: list[str] = []
        if not isinstance(block, dict) or block.get("type") not in _TEXT_FIELDS:
            problems[str(index)] = [f"Unknown block type. Use one of: {', '.join(BLOCK_TYPES)}."]
            continue
        kind = block["type"]
        allowed = {"type", *_TEXT_FIELDS[kind], *_EXTRA_FIELDS.get(kind, set())}
        unknown = set(block) - allowed
        if unknown:
            errors.append(f"Unknown field(s): {', '.join(sorted(unknown))}.")
        out: dict[str, Any] = {"type": kind}
        for field, (required, max_len) in _TEXT_FIELDS[kind].items():
            value = _text(block.get(field), field.capitalize(), max_len, errors, required)
            if value is not None:
                out[field] = value
        if kind == "heading":
            level = block.get("level", 2)
            if level not in (2, 3):
                errors.append("Heading level must be 2 or 3.")
            out["level"] = level
        elif kind == "list":
            items = block.get("items")
            if not isinstance(items, list) or not items:
                errors.append("A list needs at least one item.")
                items = []
            if len(items) > 50:
                errors.append("A list can have at most 50 items.")
            out["items"] = [
                v
                for i, item in enumerate(items[:50])
                if (v := _text(item, f"Item {i + 1}", 1000, errors, True)) is not None
            ]
            ordered = block.get("ordered", False)
            if not isinstance(ordered, bool):
                errors.append("Ordered must be true or false.")
            out["ordered"] = bool(ordered)
        elif kind == "callout":
            tone = block.get("tone", "info")
            if tone not in CALLOUT_TONES:
                errors.append(f"Tone must be one of: {', '.join(CALLOUT_TONES)}.")
            out["tone"] = tone
        if errors:
            problems[str(index)] = errors
        cleaned.append(out)
    if problems:
        raise ValidationError("Some content blocks are invalid.", details={"body": problems})
    return cleaned


def blocks_word_count(blocks: list[dict[str, Any]]) -> int:
    words = 0
    for block in blocks:
        if block.get("type") == "list":
            words += sum(len(i.split()) for i in block.get("items", []))
        else:
            words += len(str(block.get("text", "")).split())
    return words
