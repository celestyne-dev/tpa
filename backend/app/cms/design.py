"""Approved design presets for page sections.

Sections never carry CSS. Each design key maps to a small set of approved
tokens that the frontend translates into Tailwind classes, so every
combination stays on-brand, responsive and readable (dark backgrounds always
switch the section to light text).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

DESIGN_OPTIONS: dict[str, dict[str, Any]] = {
    "background": {
        "label": "Background",
        "choices": {
            "ivory": "Ivory",
            "cream": "Cream",
            "beige": "Warm beige",
            "sage": "Soft sage",
            "sage_dark": "Deep sage",
            "charcoal": "Charcoal",
        },
    },
    "spacing": {
        "label": "Section spacing",
        "choices": {"sm": "Compact", "md": "Comfortable", "lg": "Spacious"},
    },
    "width": {
        "label": "Content width",
        "choices": {"narrow": "Narrow", "default": "Standard", "wide": "Wide"},
    },
    "align": {"label": "Text alignment", "choices": {"left": "Left", "center": "Centred"}},
    "card_style": {
        "label": "Card style",
        "choices": {"soft": "Soft shadow", "outline": "Outline", "flat": "Flat"},
    },
    "aspect_ratio": {
        "label": "Image shape",
        "choices": {
            "landscape": "Landscape (3:2)",
            "wide": "Wide (16:9)",
            "square": "Square",
            "portrait": "Portrait (4:5)",
        },
    },
    "button_style": {
        "label": "Button style",
        "choices": {
            "primary": "Sage (primary)",
            "secondary": "Charcoal",
            "outline": "Outline",
            "light": "Light",
        },
    },
    "heading_size": {
        "label": "Heading size",
        "choices": {"small": "Smaller", "default": "Standard", "large": "Larger"},
    },
}

DEVICE_CHOICES = {
    "all": "All devices",
    "desktop": "Desktop and tablet only",
    "mobile": "Mobile only",
}


def design_schema(keys: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "name": key,
            "label": DESIGN_OPTIONS[key]["label"],
            "choices": [
                {"value": v, "label": label} for v, label in DESIGN_OPTIONS[key]["choices"].items()
            ],
        }
        for key in keys
    ]


def validate_design(allowed: list[str], defaults: dict[str, str], value: Any) -> tuple[dict, dict]:
    """Return (clean_design, errors). Unknown keys are rejected; missing keys use defaults."""
    errors: dict[str, list[str]] = {}
    if value is None:
        value = {}
    if not isinstance(value, dict):
        return dict(defaults), {"design": ["Design must be an object."]}
    unknown = set(value) - set(allowed)
    if unknown:
        errors["design"] = [f"Not available for this section: {', '.join(sorted(unknown))}."]
    clean: dict[str, str] = {}
    for key in allowed:
        choice = value.get(key) or defaults.get(key)
        if choice is None:
            continue
        if choice not in DESIGN_OPTIONS[key]["choices"]:
            errors[f"design.{key}"] = [f"Use one of: {', '.join(DESIGN_OPTIONS[key]['choices'])}."]
            continue
        clean[key] = choice
    return clean, errors


def _parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError
    return parsed


def validate_visibility(value: Any) -> tuple[dict, dict]:
    """Visibility rules: optional date window and device targeting."""
    if value in (None, {}):
        return {"devices": "all", "starts_at": None, "ends_at": None}, {}
    if not isinstance(value, dict):
        return {"devices": "all", "starts_at": None, "ends_at": None}, {
            "visibility": ["Visibility must be an object."]
        }
    errors: dict[str, list[str]] = {}
    unknown = set(value) - {"devices", "starts_at", "ends_at"}
    if unknown:
        errors["visibility"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]
    devices = value.get("devices") or "all"
    if devices not in DEVICE_CHOICES:
        errors["visibility.devices"] = [f"Use one of: {', '.join(DEVICE_CHOICES)}."]
        devices = "all"
    window: dict[str, datetime | None] = {}
    for key in ("starts_at", "ends_at"):
        try:
            window[key] = _parse_dt(value.get(key))
        except ValueError:
            errors[f"visibility.{key}"] = ["Use a full date and time with a time zone."]
            window[key] = None
    if window["starts_at"] and window["ends_at"] and window["ends_at"] <= window["starts_at"]:
        errors["visibility.ends_at"] = ["The end must be after the start."]
    return {
        "devices": devices,
        "starts_at": window["starts_at"].isoformat() if window["starts_at"] else None,
        "ends_at": window["ends_at"].isoformat() if window["ends_at"] else None,
    }, errors


def visible_at(visibility: dict | None, now: datetime) -> bool:
    if not visibility:
        return True
    try:
        start = _parse_dt(visibility.get("starts_at"))
        end = _parse_dt(visibility.get("ends_at"))
    except ValueError:
        return True
    return (start is None or start <= now) and (end is None or now < end)


def boundaries(visibility: dict | None) -> list[datetime]:
    out = []
    for key in ("starts_at", "ends_at"):
        try:
            value = _parse_dt((visibility or {}).get(key))
        except ValueError:
            value = None
        if value:
            out.append(value)
    return out
