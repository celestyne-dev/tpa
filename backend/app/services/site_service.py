from __future__ import annotations

from typing import Any

from ..cms.settings_registry import SOCIAL_PLATFORMS
from ..utils.validation import is_https_url
from .navigation_service import public_navigation
from .settings_service import get_values


def get_site_settings() -> dict[str, Any]:
    """Public site settings (Batch 01 shape plus CMS branding, SEO, footer and navigation)."""
    v = get_values()
    label = v["community.linkedin_followers_label"]
    contact = v["contact.email"] or None
    social = [
        {"platform": p, "label": name, "url": v[f"social.{p}"]}
        for p, name in SOCIAL_PLATFORMS.items()
        if v.get(f"social.{p}") and is_https_url(v[f"social.{p}"])
    ]
    return {
        "name": v["site.name"],
        "short_name": v["site.short_name"],
        "tagline": v["site.tagline"],
        "description": v["site.description"],
        "mission": v["site.mission"],
        "community": {
            "linkedin_followers_label": label,
            "linkedin_followers_text": (
                f"more than {label.rstrip('+')} people who follow {v['site.name']} on LinkedIn"
            ),
        },
        "newsletter": {
            "name": "The Positive Reset",
            "cadence": "weekly",
            "is_open": bool(v["newsletter.is_open"]),
        },
        "contact": {
            "email": contact,
            "partnerships_email": v["contact.partnerships_email"] or contact,
        },
        "social_links": social,
        "media_kit_url": v["partnerships.media_kit_url"]
        if is_https_url(v["partnerships.media_kit_url"] or "")
        else None,
        "branding": {"logo_url": v["branding.logo_url"]},
        "seo": {
            "default_title": v["seo.default_title"],
            "default_description": v["seo.default_description"],
            "default_og_image": v["seo.default_og_image"],
        },
        "footer": {"text": v["footer.text"]},
        "navigation": public_navigation(),
    }
