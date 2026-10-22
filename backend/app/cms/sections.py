"""Approved page section types, their layout variants and content fields.

Section content is structured data validated against these definitions; it
never contains executable HTML or JavaScript.
"""

from __future__ import annotations

from typing import Any

from ..utils.errors import ValidationError
from ..utils.validation import is_internal_path, plain_text_problem

# Field types: text (single line), textarea, path (internal link), string_list.
_CTA = lambda prefix: {  # noqa: E731
    f"{prefix}_label": {"type": "text", "label": "Button label", "max": 60},
    f"{prefix}_url": {"type": "path", "label": "Button link", "max": 200},
}

SECTION_TYPES: dict[str, dict[str, Any]] = {
    "hero": {
        "label": "Hero",
        "variants": ["default", "centered"],
        "fields": {
            "eyebrow": {"type": "text", "label": "Eyebrow", "max": 80},
            "heading": {"type": "text", "label": "Heading", "max": 120, "required": True},
            "highlight": {"type": "text", "label": "Highlighted line", "max": 120},
            "body": {"type": "textarea", "label": "Supporting text", "max": 400},
            **_CTA("primary_cta"),
            **_CTA("secondary_cta"),
        },
    },
    "brand_intro": {
        "label": "Brand introduction",
        "variants": ["default"],
        "fields": {
            "eyebrow": {"type": "text", "label": "Eyebrow", "max": 80},
            "heading": {"type": "text", "label": "Heading", "max": 120, "required": True},
            "body": {"type": "textarea", "label": "Body", "max": 1200},
            **_CTA("cta"),
        },
    },
    "topics_grid": {
        "label": "Topics grid",
        "variants": ["default"],
        "fields": {
            "eyebrow": {"type": "text", "label": "Eyebrow", "max": 80},
            "heading": {"type": "text", "label": "Heading", "max": 120, "required": True},
            "description": {"type": "textarea", "label": "Description", "max": 300},
        },
    },
    "featured_articles": {
        "label": "Featured articles",
        "variants": ["lead_and_grid", "grid"],
        "fields": {
            "eyebrow": {"type": "text", "label": "Eyebrow", "max": 80},
            "heading": {"type": "text", "label": "Heading", "max": 120, "required": True},
            "description": {"type": "textarea", "label": "Description", "max": 300},
            **_CTA("cta"),
        },
    },
    "product_previews": {
        "label": "Product previews",
        "variants": ["default"],
        "fields": {
            "eyebrow": {"type": "text", "label": "Eyebrow", "max": 80},
            "heading": {"type": "text", "label": "Heading", "max": 120, "required": True},
            "description": {"type": "textarea", "label": "Description", "max": 300},
            "footnote": {"type": "text", "label": "Footnote", "max": 200},
        },
    },
    "newsletter_cta": {
        "label": "Newsletter call to action",
        "variants": ["default"],
        "fields": {
            "heading": {"type": "text", "label": "Heading", "max": 120},
            "description": {"type": "textarea", "label": "Description", "max": 300},
        },
    },
    "feature_list": {
        "label": "Feature list",
        "variants": ["default"],
        "fields": {
            "eyebrow": {"type": "text", "label": "Eyebrow", "max": 80},
            "heading": {"type": "text", "label": "Heading", "max": 120, "required": True},
            "description": {"type": "textarea", "label": "Description", "max": 400},
            "quote": {"type": "textarea", "label": "Quote", "max": 300},
            "items": {"type": "string_list", "label": "Features", "max": 200, "max_items": 8},
        },
    },
    "partnership_cta": {
        "label": "Partnership call to action",
        "variants": ["dark", "light"],
        "fields": {
            "eyebrow": {"type": "text", "label": "Eyebrow", "max": 80},
            "heading": {"type": "text", "label": "Heading", "max": 120, "required": True},
            "body": {"type": "textarea", "label": "Body", "max": 600},
            **_CTA("cta"),
            "items": {"type": "string_list", "label": "Opportunities", "max": 80, "max_items": 10},
        },
    },
    "call_to_action": {
        "label": "Call to action",
        "variants": ["default"],
        "fields": {
            "heading": {"type": "text", "label": "Heading", "max": 120, "required": True},
            "body": {"type": "textarea", "label": "Body", "max": 400},
            **_CTA("primary_cta"),
            **_CTA("secondary_cta"),
        },
    },
    "rich_text": {
        "label": "Text block",
        "variants": ["default", "narrow"],
        "fields": {
            "heading": {"type": "text", "label": "Heading", "max": 120},
            "body": {"type": "textarea", "label": "Body", "max": 5000, "required": True},
        },
    },
}


def validate_section(section_type: str, variant: str, content: Any) -> dict[str, Any]:
    definition = SECTION_TYPES.get(section_type)
    if definition is None:
        raise ValidationError(details={"section_type": ["Unknown section type."]})
    errors: dict[str, list[str]] = {}
    if variant not in definition["variants"]:
        errors["variant"] = [f"Use one of: {', '.join(definition['variants'])}."]
    if not isinstance(content, dict):
        raise ValidationError(details={"content": ["Content must be an object."]})
    unknown = set(content) - set(definition["fields"])
    if unknown:
        errors["content"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]

    cleaned: dict[str, Any] = {}
    for name, spec in definition["fields"].items():
        value = content.get(name)
        field_errors: list[str] = []
        if spec["type"] == "string_list":
            value = value or []
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                field_errors.append("Must be a list of text items.")
                value = []
            if len(value) > spec.get("max_items", 10):
                field_errors.append(f"At most {spec.get('max_items', 10)} items.")
            items = [v.strip() for v in value if v.strip()]
            for item in items:
                if len(item) > spec["max"]:
                    field_errors.append(f"Items must be at most {spec['max']} characters.")
                if problem := plain_text_problem(item):
                    field_errors.append(problem)
            cleaned[name] = items
        else:
            if value is None:
                value = ""
            if not isinstance(value, str):
                field_errors.append("Must be text.")
                value = ""
            value = value.strip()
            if spec.get("required") and not value:
                field_errors.append("This field is required.")
            if len(value) > spec["max"]:
                field_errors.append(f"Must be at most {spec['max']} characters.")
            if value and (problem := plain_text_problem(value)):
                field_errors.append(problem)
            if spec["type"] == "path" and value and not is_internal_path(value):
                field_errors.append("Use an internal link starting with /.")
            cleaned[name] = value
        if field_errors:
            errors[name] = field_errors
    if errors:
        raise ValidationError("The section content is invalid.", details=errors)
    return cleaned
