"""Registered site settings: the only keys that can be stored, with types and defaults.

There are deliberately no free-form or executable fields (no HTML, scripts,
or arbitrary code). Defaults keep the site working on a fresh installation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from flask import current_app

from ..utils.validation import is_email, is_https_url, is_internal_path, plain_text_problem

SOCIAL_PLATFORMS = {
    "linkedin": "LinkedIn",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "x": "X",
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "pinterest": "Pinterest",
}


@dataclass(frozen=True)
class SettingDef:
    key: str
    label: str
    group: str
    type: str  # string | text | email | https_url | path_or_https | boolean
    default: Callable[[], Any]
    max_length: int = 200
    help: str = ""
    public: bool = True
    choices: tuple[str, ...] = field(default_factory=tuple)


def _cfg(name: str, fallback: Any = "") -> Callable[[], Any]:
    return lambda: current_app.config.get(name) or fallback


def _const(value: Any) -> Callable[[], Any]:
    return lambda: value


SETTINGS: list[SettingDef] = [
    SettingDef("site.name", "Site name", "Branding", "string", _const("Think Positive Always"), 80),
    SettingDef("site.short_name", "Short name", "Branding", "string", _const("TPA"), 20),
    SettingDef(
        "site.tagline",
        "Tagline",
        "Branding",
        "text",
        _const(
            "Practical inspiration for a stronger mindset, more confidence, "
            "and intentional personal growth."
        ),
        200,
    ),
    SettingDef(
        "site.description",
        "Short brand description",
        "Branding",
        "text",
        _const(
            "Think Positive Always offers practical encouragement, mindset insights, personal "
            "growth articles and thoughtful resources to help you build confidence and grow "
            "through every season of life."
        ),
        320,
    ),
    SettingDef(
        "site.mission",
        "Mission statement",
        "Branding",
        "text",
        _const(
            "Helping people develop a healthier mindset, navigate life's challenges, build "
            "confidence, and move forward through encouragement, thoughtful content, and "
            "useful personal development tools."
        ),
        400,
    ),
    SettingDef(
        "branding.logo_url",
        "Logo",
        "Branding",
        "path_or_https",
        _const("/icon.svg"),
        500,
        "Site path (e.g. /icon.svg) or https URL.",
    ),
    SettingDef(
        "community.linkedin_followers_label",
        "LinkedIn follower count label",
        "Branding",
        "string",
        _const("280,000+"),
        20,
        "Verified figure only.",
    ),
    SettingDef("contact.email", "Contact email", "Contact", "email", _cfg("CONTACT_EMAIL"), 254),
    SettingDef(
        "contact.partnerships_email",
        "Partnerships email",
        "Contact",
        "email",
        _cfg("PARTNERSHIPS_EMAIL"),
        254,
        "Falls back to the contact email when empty.",
    ),
    *[
        SettingDef(
            f"social.{platform}",
            label,
            "Social links",
            "https_url",
            (lambda p=platform: (current_app.config.get("SOCIAL_LINKS") or {}).get(p, "")),
            500,
        )
        for platform, label in SOCIAL_PLATFORMS.items()
    ],
    SettingDef(
        "seo.default_title",
        "Default page title",
        "SEO defaults",
        "string",
        _const("Think Positive Always — Practical Inspiration for Personal Growth"),
        120,
    ),
    SettingDef(
        "seo.default_description",
        "Default meta description",
        "SEO defaults",
        "text",
        _const(
            "Think Positive Always offers practical encouragement, mindset insights, personal "
            "growth articles and thoughtful resources to help you build confidence and grow "
            "through every season of life."
        ),
        320,
    ),
    SettingDef(
        "seo.default_og_image",
        "Default social sharing image",
        "SEO defaults",
        "path_or_https",
        _const("/og/default.png"),
        500,
        "1200×630 image path or https URL.",
    ),
    SettingDef(
        "footer.text",
        "Footer introduction",
        "Footer",
        "text",
        _const(
            "Practical encouragement, mindset insights, and thoughtful personal growth resources "
            "to help you build confidence and move forward through every season of life."
        ),
        400,
    ),
    SettingDef(
        "newsletter.is_open",
        "Newsletter sign-ups open",
        "Newsletter",
        "boolean",
        _cfg("NEWSLETTER_OPEN", False),
        help="Enable only after a real email provider is integrated.",
    ),
    SettingDef(
        "partnerships.media_kit_url",
        "Media kit URL",
        "Partnerships",
        "https_url",
        _cfg("MEDIA_KIT_URL"),
        500,
        "Leave empty until a media kit exists.",
    ),
]

SETTINGS_BY_KEY = {s.key: s for s in SETTINGS}


def validate_setting(definition: SettingDef, value: Any) -> tuple[Any, str | None]:
    """Return (clean_value, error)."""
    if definition.type == "boolean":
        if not isinstance(value, bool):
            return None, "Must be true or false."
        return value, None
    if value is None:
        value = ""
    if not isinstance(value, str):
        return None, "Must be text."
    value = value.strip()
    if len(value) > definition.max_length:
        return None, f"Must be at most {definition.max_length} characters."
    if not value:
        return "", None
    problem = plain_text_problem(value)
    if problem:
        return None, problem
    if definition.type == "email" and not is_email(value):
        return None, "Enter a valid email address."
    if definition.type == "https_url" and not is_https_url(value):
        return None, "Enter a full https:// URL."
    if definition.type == "path_or_https" and not (is_internal_path(value) or is_https_url(value)):
        return None, "Enter a site path starting with / or a full https:// URL."
    return value, None
