"""Registered site settings: the only keys that can be stored, with types and defaults.

There are deliberately no free-form or executable fields (no HTML, scripts,
or arbitrary code). Defaults keep the site working on a fresh installation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
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


# AI model-training crawlers: blocked in robots.txt unless approved one by one here.
# (token, who, what it's used for). AI *search* crawlers (OAI-SearchBot, ChatGPT-User,
# Claude-SearchBot, Claude-User, PerplexityBot, Perplexity-User) and search engines are
# never listed: they follow the normal rules and stay allowed.
AI_TRAINING_CRAWLERS = (
    ("GPTBot", "OpenAI", "training OpenAI models"),
    ("ClaudeBot", "Anthropic", "training Anthropic models"),
    ("Google-Extended", "Google", "training Gemini and grounding Gemini answers"),
    ("Applebot-Extended", "Apple", "training Apple's AI models"),
    ("CCBot", "Common Crawl", "public web datasets used to train AI models"),
    ("Meta-ExternalAgent", "Meta", "training Meta's AI models"),
    ("Bytespider", "ByteDance", "training ByteDance's AI models"),
)


def training_crawler_key(token: str) -> str:
    return f"seo.allow_ai_training.{token.lower()}"


@dataclass(frozen=True)
class SettingDef:
    key: str
    label: str
    group: str
    # string | text | email | https_url | path_or_https | boolean | media | choice | path_list
    # | exchange_rate
    type: str
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
        "visibility.shop_public",
        "Show the shop on the website",
        "Website sections",
        "boolean",
        _const(False),
        help="Off: Shop and Cart links are left out of the menus and the header, and digital "
        "product showcase sections are hidden. Resource and product pages stay reachable by "
        "their links (free resources link to them).",
    ),
    SettingDef(
        "visibility.courses_public",
        "Show courses on the website",
        "Website sections",
        "boolean",
        _const(False),
        help="Off: Courses links are left out of the menus. Course pages stay reachable by "
        "their links.",
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

PALETTES = {
    "classic": "Classic: ivory, sage and gold",
    "evergreen": "Evergreen: deeper greens",
    "golden_hour": "Golden hour: warmer gold accents",
}
TYPOGRAPHY = {
    "classic": "Classic: elegant serif headings, clean sans-serif text",
    "editorial": "Editorial: larger serif headings",
    "modern": "Modern: sans-serif headings",
}
BUTTON_SHAPES = {"pill": "Rounded pill", "rounded": "Softly rounded", "square": "Square corners"}
IMAGE_STYLES = {"rounded": "Rounded corners", "soft": "Slightly rounded", "square": "Square"}


def _choice(key, label, group, choices, default, help_=""):
    return SettingDef(
        key, label, group, "choice", _const(default), 40, help_, choices=tuple(choices)
    )


SETTINGS += [
    SettingDef(
        "branding.logo_media_id",
        "Logo image",
        "Branding",
        "media",
        _const(None),
        help="Optional. Replaces the built-in logo mark. Use a square or wide PNG/JPEG.",
    ),
    SettingDef(
        "branding.logo_alt_media_id",
        "Logo for dark backgrounds",
        "Branding",
        "media",
        _const(None),
        help="Used in the footer. Falls back to the main logo.",
    ),
    SettingDef(
        "branding.show_wordmark",
        "Show the site name beside the logo",
        "Branding",
        "boolean",
        _const(True),
    ),
    SettingDef(
        "branding.wordmark_subline",
        "Small line under the site name",
        "Branding",
        "string",
        _const("Mindset · Growth · Confidence"),
        60,
    ),
    SettingDef(
        "branding.favicon_media_id",
        "Favicon",
        "Branding",
        "media",
        _const(None),
        help="A square image (at least 512×512). Browser and app icons are generated from it.",
    ),
    SettingDef(
        "branding.social_image_media_id",
        "Default social sharing image",
        "Branding",
        "media",
        _const(None),
        help="Shown when pages are shared. Cropped to 1200×630. Overrides the SEO default path.",
    ),
    _choice(
        "branding.palette",
        "Colour palette",
        "Branding",
        PALETTES,
        "classic",
        "Approved palettes only; every option meets WCAG AA contrast.",
    ),
    _choice("branding.typography", "Typography", "Branding", TYPOGRAPHY, "classic"),
    _choice("branding.button_shape", "Button style", "Branding", BUTTON_SHAPES, "pill"),
    _choice("branding.image_style", "Image corners", "Branding", IMAGE_STYLES, "rounded"),
    SettingDef("header.show_cta", "Show a header button", "Header", "boolean", _const(True)),
    SettingDef(
        "header.cta_label", "Header button label", "Header", "string", _const("Newsletter"), 30
    ),
    SettingDef(
        "header.cta_url",
        "Header button link",
        "Header",
        "path_or_https",
        _const("/newsletter"),
        500,
        "A menu link to the same address is hidden on desktop to avoid repetition.",
    ),
    SettingDef(
        "footer.show_newsletter_link",
        "Show the newsletter invitation",
        "Footer",
        "boolean",
        _const(True),
        help="A short invitation to The Positive Reset with a button to /newsletter. The "
        "footer never shows a sign-up form.",
    ),
    SettingDef(
        "footer.newsletter_label",
        "Newsletter button text",
        "Footer",
        "string",
        _const("Explore the Newsletter"),
        80,
    ),
    SettingDef("footer.show_contact", "Show the contact email", "Footer", "boolean", _const(False)),
    SettingDef("footer.show_social", "Show social links", "Footer", "boolean", _const(True)),
    SettingDef(
        "footer.copyright",
        "Copyright line",
        "Footer",
        "string",
        _const("© {year} {site_name}. All rights reserved."),
        160,
        "{year} and {site_name} are filled in automatically.",
    ),
    SettingDef(
        "footer.promo_text",
        "Promotional message",
        "Footer",
        "text",
        _const(""),
        200,
        "Optional short message, e.g. an upcoming release.",
    ),
    SettingDef(
        "footer.promo_cta_label", "Promotional link text", "Footer", "string", _const(""), 60
    ),
    SettingDef(
        "footer.promo_cta_url", "Promotional link", "Footer", "path_or_https", _const(""), 500
    ),
    SettingDef(
        "seo.organization_logo_media_id",
        "Organisation logo for search engines",
        "SEO defaults",
        "media",
        _const(None),
        help="Used in Organization structured data. Falls back to the site logo.",
    ),
    SettingDef(
        "seo.organization_schema",
        "Publish Organization structured data",
        "SEO defaults",
        "boolean",
        _const(True),
    ),
    SettingDef(
        "seo.website_schema",
        "Publish WebSite structured data",
        "SEO defaults",
        "boolean",
        _const(True),
    ),
    SettingDef(
        "seo.sitemap_include_topics",
        "Include topic pages in the sitemap",
        "SEO defaults",
        "boolean",
        _const(True),
    ),
    SettingDef(
        "seo.sitemap_exclude",
        "Paths to leave out of the sitemap",
        "SEO defaults",
        "path_list",
        _const(""),
        2000,
        "One site path per line, e.g. /free-resources. "
        "Drafts and noindex pages are always excluded.",
    ),
    SettingDef(
        "shop.title", "Shop heading", "Shop", "string", _const("Tools for Your Growth Journey"), 120
    ),
    SettingDef(
        "shop.intro",
        "Shop introduction",
        "Shop",
        "text",
        _const(
            "Original eBooks, workbooks and journals designed to help you reflect, build "
            "confidence, and take meaningful steps forward."
        ),
        400,
    ),
    SettingDef(
        "shop.notice",
        "Shop notice",
        "Shop",
        "text",
        _const(""),
        300,
        "Optional short notice at the top of the shop (e.g. about a launch). Leave empty to hide.",
    ),
    # Batch 16. Prices, orders and Paystack charges are always in KES (CHARGE_CURRENCIES);
    # these only add an approximate US dollar figure next to KES prices.
    SettingDef(
        "shop.guest_checkout",
        "Allow guest checkout",
        "Shop",
        "boolean",
        _const(True),
        help="Let people buy without creating an account: they enter an email address, pay, "
        "and get their receipt and a private access link by email. Signed-in checkout is "
        "always available.",
    ),
    SettingDef(
        "shop.usd_estimate",
        "Show approximate US dollar prices",
        "Shop",
        "boolean",
        _const(False),
        help="Adds an approximate USD amount next to KES prices for international visitors. "
        "Customers are always charged the KES price; nothing is shown without a valid rate.",
    ),
    SettingDef(
        "shop.usd_rate",
        "Kenyan shillings per US dollar (display only)",
        "Shop",
        "exchange_rate",
        _const(""),
        12,
        "For example 129.50. Used only to show approximate USD amounts; never used to charge.",
    ),
    SettingDef(
        "seo.allow_indexing",
        "Allow search engines to index the site",
        "Technical",
        "boolean",
        _const(True),
        help="Can only restrict indexing: the deployment setting VITE_ALLOW_INDEXING "
        "must also allow it.",
    ),
    SettingDef(
        "seo.canonical_site_url",
        "Canonical website address",
        "Technical",
        "https_url",
        _const(""),
        200,
        "e.g. https://thinkpositivealways.com. Leave empty to use the deployment's SITE_URL.",
    ),
    SettingDef(
        "security.require_admin_mfa",
        "Require two-step sign-in for every administrator",
        "Technical",
        "boolean",
        _const(False),
        help="When on, administrators without two-step sign-in can only open their "
        "account's security page until they set it up. Enrol yourself first.",
        public=False,
    ),
    # Cookie settings (Batch 13): wording only. Which technologies exist, and whether usage
    # statistics wait for consent, are fixed in the application (PRIVACY_STATISTICS_MODE),
    # never in these fields.
    SettingDef(
        "privacy.settings_label",
        "Cookie settings link text",
        "Privacy choices",
        "string",
        _const("Cookie settings"),
        40,
        "Shown at the bottom of every page; it opens the cookie settings panel.",
    ),
    SettingDef(
        "privacy.panel_intro",
        "Cookie settings introduction",
        "Privacy choices",
        "text",
        _const(
            "We keep cookies to a minimum. The necessary ones keep the website working. Usage "
            "statistics are optional: they help us see which pages are useful, store nothing "
            "on your device and are never used for advertising."
        ),
        500,
    ),
    SettingDef(
        "privacy.notice_text",
        "Cookie notice text",
        "Privacy choices",
        "text",
        _const(
            "May we count your visit? Our own usage statistics store nothing on your device "
            "and are never used for advertising."
        ),
        300,
        "Shown only when the website asks before counting visits (consent mode).",
    ),
    SettingDef(
        "privacy.necessary_label",
        "Necessary: name",
        "Privacy choices",
        "string",
        _const("Necessary"),
        60,
    ),
    SettingDef(
        "privacy.necessary_description",
        "Necessary: description",
        "Privacy choices",
        "text",
        _const(
            "Keep you signed in, protect your account and remember things you ask for, such "
            "as your cart. Always on."
        ),
        400,
    ),
    SettingDef(
        "privacy.statistics_label",
        "Usage statistics: name",
        "Privacy choices",
        "string",
        _const("Usage statistics"),
        60,
    ),
    SettingDef(
        "privacy.statistics_description",
        "Usage statistics: description",
        "Privacy choices",
        "text",
        _const(
            "Count page visits so we can see what is useful. No cookies, nothing stored on "
            "your device, no advertising, and your IP address is never stored."
        ),
        400,
    ),
    SettingDef(
        "privacy.policy_path",
        "Cookie Policy link",
        "Privacy choices",
        "path_or_https",
        _const("/cookie-policy"),
        200,
    ),
    SettingDef(
        "privacy.consent_version",
        "Consent version",
        "Privacy choices",
        "string",
        _const("2026-11-09"),
        40,
        "Change this (for example to today's date) after a material change to the cookie "
        "categories or wording: visitors are asked for their choice again where consent is "
        "required.",
    ),
    SettingDef(
        "trust.editorial_policy_path",
        "Editorial policy page",
        "Trust",
        "path_or_https",
        _const("/editorial-policy"),
        200,
        "Site path of your published editorial policy page (create it under Pages). Linked "
        "in the footer and in Organization structured data only while that page is published.",
    ),
    SettingDef(
        "trust.corrections_policy_path",
        "Corrections policy page",
        "Trust",
        "path_or_https",
        _const("/corrections-policy"),
        200,
        "Site path of your published corrections policy page. Linked in the footer and in "
        "structured data only while that page is published.",
    ),
    *(
        SettingDef(
            training_crawler_key(token),
            f"Allow {token} ({who}) to use the site for AI training",
            "Technical",
            "boolean",
            _const(False),
            help=f"Off: robots.txt blocks {token} ({what}). Search engines and AI search "
            "crawlers are not affected. Takes effect at the next publish.",
        )
        for token, who, what in AI_TRAINING_CRAWLERS
    ),
]

SETTINGS_BY_KEY = {s.key: s for s in SETTINGS}
MEDIA_SETTINGS = tuple(s.key for s in SETTINGS if s.type == "media")


MAX_EXCHANGE_RATE = Decimal("100000")


def parse_exchange_rate(value: Any) -> Decimal | None:
    """A positive KES-per-USD rate with at most 4 decimal places, or None."""
    text = str(value if value is not None else "").strip().replace(",", "")
    if not text or len(text) > 12:
        return None
    try:
        rate = Decimal(text)
    except InvalidOperation:
        return None
    if not rate.is_finite() or rate <= 0 or rate > MAX_EXCHANGE_RATE:
        return None
    if rate.as_tuple().exponent < -4:
        return None
    return rate.normalize() if rate == rate.to_integral_value() else rate


def validate_setting(definition: SettingDef, value: Any) -> tuple[Any, str | None]:
    """Return (clean_value, error)."""
    if definition.type == "boolean":
        if not isinstance(value, bool):
            return None, "Must be true or false."
        return value, None
    if definition.type == "media":
        if value in (None, ""):
            return None, None
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            return None, "Choose an image from the media library."
        return value, None
    if definition.type == "choice":
        if value not in definition.choices:
            return None, f"Use one of: {', '.join(definition.choices)}."
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
    if definition.type == "path_list":
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        bad = [line for line in lines if not is_internal_path(line)]
        if bad:
            return None, f"Use site paths starting with / (not: {bad[0]})."
        if len(lines) > 50:
            return None, "At most 50 paths."
        return "\n".join(dict.fromkeys(lines)), None
    if definition.type == "exchange_rate":
        rate = parse_exchange_rate(value)
        if rate is None:
            return None, "Enter a number of shillings per US dollar, e.g. 129.50."
        return format(rate, "f"), None
    if definition.type == "https_url" and definition.key == "seo.canonical_site_url":
        from urllib.parse import urlparse

        parsed = urlparse(value)
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            return None, "Use the site address only, e.g. https://example.com."
        value = f"{parsed.scheme}://{parsed.netloc}"
    return value, None
