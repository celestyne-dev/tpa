from __future__ import annotations

from typing import Any

from flask import current_app

SOCIAL_LABELS = {
    "linkedin": "LinkedIn",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "x": "X",
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "pinterest": "Pinterest",
}


def _https(url: str) -> bool:
    return url.startswith("https://")


def get_site_settings() -> dict[str, Any]:
    """Public business settings. Only verified, configured values are returned."""
    cfg = current_app.config
    contact = cfg.get("CONTACT_EMAIL") or None
    social = [
        {"platform": p, "label": SOCIAL_LABELS[p], "url": url}
        for p, url in (cfg.get("SOCIAL_LINKS") or {}).items()
        if url and _https(url) and p in SOCIAL_LABELS
    ]
    media_kit = cfg.get("MEDIA_KIT_URL") or None
    return {
        "name": "Think Positive Always",
        "short_name": "TPA",
        "tagline": (
            "Practical inspiration for a stronger mindset, more confidence, "
            "and intentional personal growth."
        ),
        "description": (
            "Think Positive Always offers practical encouragement, mindset insights, personal "
            "growth articles and thoughtful resources to help you build confidence and grow "
            "through every season of life."
        ),
        "mission": (
            "Helping people develop a healthier mindset, navigate life's challenges, build "
            "confidence, and move forward through encouragement, thoughtful content, and "
            "useful personal development tools."
        ),
        "community": {
            # Verified figure: LinkedIn followers only.
            "linkedin_followers_label": "280,000+",
            "linkedin_followers_text": (
                "more than 280,000 people who follow Think Positive Always on LinkedIn"
            ),
        },
        "newsletter": {
            "name": "The Positive Reset",
            "cadence": "weekly",
            "is_open": bool(cfg.get("NEWSLETTER_OPEN")),
        },
        "contact": {
            "email": contact,
            "partnerships_email": cfg.get("PARTNERSHIPS_EMAIL") or contact,
        },
        "social_links": social,
        "media_kit_url": media_kit if media_kit and _https(media_kit) else None,
    }
