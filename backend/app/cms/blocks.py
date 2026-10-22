"""Structured article content blocks.

Blocks are plain data rendered by React as text; no HTML or scripts are
accepted. Unknown block types and unknown fields are rejected. Media are
referenced by id (resolved to optimised images when the article is served),
videos by provider + id (never by embed code), and links must be internal
paths or https URLs.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..utils.errors import ValidationError
from ..utils.validation import is_https_url, plain_text_problem

MAX_BLOCKS = 300
CALLOUT_TONES = ("info", "tip", "warning", "success")
IMAGE_ALIGNS = ("center", "wide", "full", "left", "right")
BUTTON_STYLES = ("primary", "secondary")
RESOURCE_KINDS = ("resource", "product")  # "product" is reserved for future commerce
VIDEO_PROVIDERS = ("youtube", "vimeo")

# field -> (required, max_length)
_TEXT_FIELDS: dict[str, dict[str, tuple[bool, int]]] = {
    "paragraph": {"text": (True, 5000)},
    "heading": {"text": (True, 200)},
    "quote": {"text": (True, 1000), "cite": (False, 200)},
    "pullquote": {"text": (True, 400), "cite": (False, 200)},
    "callout": {"text": (True, 1000), "title": (False, 120)},
    "list": {},
    "divider": {},
    "image": {"alt": (False, 300), "caption": (False, 500)},
    "gallery": {"caption": (False, 500)},
    "video": {"title": (True, 200), "caption": (False, 500)},
    "button": {"label": (True, 60)},
    "cta": {"title": (True, 120), "text": (False, 400), "button_label": (True, 60)},
    "related": {"title": (False, 120)},
    "resource": {"title": (True, 120), "description": (False, 400), "label": (False, 60)},
    "table": {"caption": (False, 200)},
}
_EXTRA_FIELDS = {
    "heading": {"level"},
    "list": {"items", "ordered"},
    "callout": {"tone"},
    "image": {"media_id", "align"},
    "gallery": {"items", "columns"},
    "video": {"provider", "video_id", "url"},
    "button": {"href", "style", "align"},
    "cta": {"button_href"},
    "related": {"article_ids"},
    "resource": {"href", "kind", "media_id"},
    "table": {"rows", "header_row"},
}
BLOCK_TYPES = tuple(_TEXT_FIELDS)

_INTERNAL_PATH = re.compile(
    r"^/(?!/)[A-Za-z0-9/_\-.~%]*(\?[A-Za-z0-9_\-.~%=&]*)?(#[A-Za-z0-9_-]*)?$"
)
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_VIMEO_ID = re.compile(r"^[0-9]{6,12}$")


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


def safe_href(value: Any) -> bool:
    return isinstance(value, str) and (bool(_INTERNAL_PATH.match(value)) or is_https_url(value))


def _href(value: Any, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} is required.")
        return None
    value = value.strip()
    if len(value) > 500 or not safe_href(value):
        errors.append(f"{label} must be a site path (e.g. /topics/confidence) or https:// URL.")
        return None
    return value


def _media_id(value: Any, label: str, errors: list[str], required: bool = True) -> int | None:
    if value is None and not required:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        errors.append(f"{label} must be chosen from the media library.")
        return None
    return value


def parse_video_url(url: str) -> tuple[str, str] | None:
    """Return (provider, id) for approved YouTube/Vimeo URLs, else None."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    if parsed.scheme != "https":
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    path = parsed.path.strip("/")
    if host in ("youtube.com", "youtube-nocookie.com"):
        if path == "watch":
            vid = (parse_qs(parsed.query).get("v") or [""])[0]
        elif path.startswith(("embed/", "shorts/", "live/")):
            vid = path.split("/")[1]
        else:
            return None
        return ("youtube", vid) if _YOUTUBE_ID.match(vid) else None
    if host == "youtu.be":
        return ("youtube", path) if _YOUTUBE_ID.match(path) else None
    if host in ("vimeo.com", "player.vimeo.com"):
        vid = path.split("/")[-1]
        return ("vimeo", vid) if _VIMEO_ID.match(vid) else None
    return None


def _validate_extras(kind: str, block: dict[str, Any], out: dict[str, Any], errors: list[str]):
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
    elif kind == "image":
        out["media_id"] = _media_id(block.get("media_id"), "Image", errors)
        align = block.get("align", "center")
        if align not in IMAGE_ALIGNS:
            errors.append(f"Alignment must be one of: {', '.join(IMAGE_ALIGNS)}.")
        out["align"] = align
    elif kind == "gallery":
        items = block.get("items")
        if not isinstance(items, list) or not 2 <= len(items) <= 12:
            errors.append("A gallery needs between 2 and 12 images.")
            items = items if isinstance(items, list) else []
        clean_items = []
        for i, item in enumerate(items[:12]):
            if not isinstance(item, dict) or set(item) - {"media_id", "caption", "alt"}:
                errors.append(f"Gallery image {i + 1} is invalid.")
                continue
            entry = {"media_id": _media_id(item.get("media_id"), f"Gallery image {i + 1}", errors)}
            for field, limit in (("caption", 300), ("alt", 300)):
                if (
                    v := _text(item.get(field), f"Gallery {field}", limit, errors, False)
                ) is not None:
                    entry[field] = v
            clean_items.append(entry)
        out["items"] = clean_items
        columns = block.get("columns", 3)
        if columns not in (2, 3, 4):
            errors.append("Galleries use 2, 3 or 4 columns.")
        out["columns"] = columns
    elif kind == "video":
        provider, video_id = block.get("provider"), block.get("video_id")
        if block.get("url"):
            parsed = parse_video_url(str(block["url"]))
            if parsed is None:
                errors.append("Only YouTube and Vimeo links are supported.")
            else:
                provider, video_id = parsed
        if provider not in VIDEO_PROVIDERS:
            errors.append("Only YouTube and Vimeo videos can be embedded.")
        elif not isinstance(video_id, str) or not (
            _YOUTUBE_ID if provider == "youtube" else _VIMEO_ID
        ).match(video_id):
            errors.append("The video link is not valid.")
        out["provider"], out["video_id"] = provider, video_id
    elif kind == "button":
        out["href"] = _href(block.get("href"), "Link", errors)
        style = block.get("style", "primary")
        if style not in BUTTON_STYLES:
            errors.append("Button style must be primary or secondary.")
        align = block.get("align", "left")
        if align not in ("left", "center"):
            errors.append("Button alignment must be left or center.")
        out["style"], out["align"] = style, align
    elif kind == "cta":
        out["button_href"] = _href(block.get("button_href"), "Button link", errors)
    elif kind == "related":
        ids = block.get("article_ids")
        if (
            not isinstance(ids, list)
            or not 1 <= len(ids) <= 4
            or not all(isinstance(i, int) and not isinstance(i, bool) and i > 0 for i in ids)
        ):
            errors.append("Choose between 1 and 4 related articles.")
            ids = []
        out["article_ids"] = list(dict.fromkeys(ids))
    elif kind == "resource":
        out["href"] = _href(block.get("href"), "Link", errors)
        resource_kind = block.get("kind", "resource")
        if resource_kind not in RESOURCE_KINDS:
            errors.append("Kind must be resource or product.")
        out["kind"] = resource_kind
        if (media := _media_id(block.get("media_id"), "Image", errors, required=False)) is not None:
            out["media_id"] = media
    elif kind == "table":
        rows = block.get("rows")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 30:
            errors.append("A table needs between 1 and 30 rows.")
            rows = []
        width = len(rows[0]) if rows and isinstance(rows[0], list) else 0
        if not 1 <= width <= 6:
            errors.append("Tables have between 1 and 6 columns.")
        clean_rows = []
        for r, row in enumerate(rows[:30]):
            if not isinstance(row, list) or len(row) != width:
                errors.append(f"Row {r + 1} must have {width} cells.")
                continue
            cells = []
            for c, cell in enumerate(row):
                cell = "" if cell is None else cell
                value = _text(cell, f"Cell {r + 1}.{c + 1}", 300, errors, False)
                cells.append(value or "")
            clean_rows.append(cells)
        out["rows"] = clean_rows
        header = block.get("header_row", True)
        if not isinstance(header, bool):
            errors.append("Header row must be true or false.")
        out["header_row"] = bool(header)


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
            label = field.replace("_", " ").capitalize()
            value = _text(block.get(field), label, max_len, errors, required)
            if value is not None:
                out[field] = value
        _validate_extras(kind, block, out, errors)
        if errors:
            problems[str(index)] = errors
        cleaned.append(out)
    if problems:
        raise ValidationError("Some content blocks are invalid.", details={"body": problems})
    return cleaned


def media_ids(blocks: list[dict[str, Any]]) -> set[int]:
    ids: set[int] = set()
    for block in blocks or []:
        if isinstance(block.get("media_id"), int):
            ids.add(block["media_id"])
        if block.get("type") == "gallery":
            ids |= {i["media_id"] for i in block.get("items", []) if isinstance(i, dict)}
    return {i for i in ids if i}


def related_ids(blocks: list[dict[str, Any]]) -> set[int]:
    return {i for b in blocks or [] if b.get("type") == "related" for i in b.get("article_ids", [])}


_WORD_FIELDS = ("text", "title", "caption", "description", "cite")


def blocks_word_count(blocks: list[dict[str, Any]]) -> int:
    words = 0
    for block in blocks:
        kind = block.get("type")
        if kind == "list":
            words += sum(len(i.split()) for i in block.get("items", []))
        elif kind == "table":
            words += sum(len(c.split()) for row in block.get("rows", []) for c in row)
        elif kind in ("paragraph", "heading", "quote", "pullquote", "callout"):
            words += len(str(block.get("text", "")).split())
            if kind == "callout":
                words += len(str(block.get("title", "")).split())
    return words


def heading_outline(blocks: list[dict[str, Any]]) -> list[tuple[int, str]]:
    return [(b.get("level", 2), b.get("text", "")) for b in blocks if b.get("type") == "heading"]


def internal_links(blocks: list[dict[str, Any]]) -> list[str]:
    hrefs = []
    for block in blocks or []:
        for field in ("href", "button_href"):
            value = block.get(field)
            if isinstance(value, str) and value.startswith("/"):
                hrefs.append(value)
    return hrefs
