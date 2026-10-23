from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from ..cms.routing import OVERRIDABLE_PATHS
from ..cms.settings_registry import SOCIAL_PLATFORMS
from ..extensions import db
from ..models import MediaAsset, Page
from ..utils.validation import is_https_url
from .admin.announcement_admin import public_announcements
from .branding_service import public_branding
from .navigation_service import public_navigation
from .serializers import iso
from .settings_service import get_values


def _media_image(asset_id: Any, preset: str = "responsive") -> dict[str, Any] | None:
    if not isinstance(asset_id, int):
        return None
    asset = db.session.get(MediaAsset, asset_id)
    if asset is None or asset.visibility != "public" or asset.status == "archived":
        return None
    return asset.as_image(preset)


def _display_currencies(v: dict[str, Any]) -> list[str]:
    from ..commerce.currency import CURRENCIES

    codes = [c.strip().upper() for c in str(v.get("shop.display_currencies") or "").split(",")]
    return [c for c in dict.fromkeys(codes) if c in CURRENCIES] or ["USD"]


def overridden_builtin_paths() -> list[str]:
    """Built-in pages currently replaced by a published CMS page."""
    live = db.session.scalars(
        select(Page.published_path).where(
            Page.status == "published", Page.published_path.in_(OVERRIDABLE_PATHS)
        )
    )
    return sorted(live)


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
        "newsletter": _newsletter(),
        "contact": {
            "email": contact,
            "partnerships_email": v["contact.partnerships_email"] or contact,
        },
        "social_links": social,
        "media_kit_url": v["partnerships.media_kit_url"]
        if is_https_url(v["partnerships.media_kit_url"] or "")
        else None,
        "branding": public_branding(v),
        "seo": {
            "default_title": v["seo.default_title"],
            "default_description": v["seo.default_description"],
            "default_og_image": v["seo.default_og_image"],
            "organization_schema": v["seo.organization_schema"] is not False,
            "website_schema": v["seo.website_schema"] is not False,
            "organization_logo": _media_image(v["seo.organization_logo_media_id"]),
            "allow_indexing": v["seo.allow_indexing"] is not False,
            "canonical_site_url": v["seo.canonical_site_url"] or None,
        },
        "header": {
            "cta": {"label": v["header.cta_label"], "href": v["header.cta_url"]}
            if v["header.show_cta"] and v["header.cta_label"] and v["header.cta_url"]
            else None,
        },
        "footer": {
            "text": v["footer.text"],
            "show_newsletter_link": v["footer.show_newsletter_link"] is not False,
            "newsletter_label": v["footer.newsletter_label"],
            "show_contact": bool(v["footer.show_contact"]) and bool(contact),
            "show_social": v["footer.show_social"] is not False,
            "copyright": v["footer.copyright"],
            "promo": {
                "text": v["footer.promo_text"],
                "cta": {"label": v["footer.promo_cta_label"], "href": v["footer.promo_cta_url"]}
                if v["footer.promo_cta_label"] and v["footer.promo_cta_url"]
                else None,
            }
            if v["footer.promo_text"]
            else None,
        },
        "shop": {
            "title": v["shop.title"],
            "intro": v["shop.intro"],
            "notice": v["shop.notice"],
            "display_currencies": _display_currencies(v),
        },
        "navigation": public_navigation(),
        "announcements": public_announcements(),
        # Lets the browser hydrate time-limited content exactly as it was rendered.
        "generated_at": iso(datetime.now(UTC)),
        "cms_overrides": overridden_builtin_paths(),
    }


def _newsletter() -> dict:
    """Signup is open only when sending and consent wording are configured (not merely
    when the "sign-ups open" setting is on)."""
    from .newsletter.config import get_settings, public_status

    status = public_status()
    return {
        "name": status["name"],
        "tagline": status["tagline"],
        "cadence": "weekly",
        "is_open": status["signup_open"],
        "consent_text": status["consent_text"],
        "consent_version": get_settings()["email.consent_version"] if status["signup_open"] else "",
        "preferences": status["preferences"],
        "default_preferences": status["default_preferences"],
    }
