"""Approved page section types: fields, layout variants, design presets and defaults.

Sections are structured data validated against these definitions. They never
contain HTML, CSS or executable code: the frontend renders each type with an
approved component from its section registry. New types are added here and in
``frontend/src/components/sections/registry.js``.

Field types
-----------
text, textarea   plain text (textarea keeps paragraphs separated by blank lines)
rich             article content blocks (validated by app.cms.blocks)
link             internal path (/about) or https URL
cta              button: {label, url, style} or {cta_id, style} (a global CTA)
media            media library asset id (optimised responsive image)
select, number, boolean
articles, topics lists of ids (selection order is kept)
products         product ids (selection order is kept)
product_collection  one product collection id (as a one-item list)
author           author id
items            list of objects with their own sub-fields
string_list      list of short texts
reusables        list of shared section ids (section groups only)
"""

from __future__ import annotations

from typing import Any

from ..utils.errors import ValidationError
from ..utils.validation import is_https_url, is_internal_path, plain_text_problem
from .design import DESIGN_OPTIONS, design_schema, validate_design, validate_visibility

BUTTON_STYLES = tuple(DESIGN_OPTIONS["button_style"]["choices"])
FEATURE_ICONS = (
    "heart-handshake",
    "compass",
    "notebook-pen",
    "footprints",
    "sun",
    "sprout",
    "gem",
    "sunrise",
    "leaf",
    "lightbulb",
    "book-open",
    "shield-check",
    "sparkles",
    "handshake",
    "mail-check",
    "calendar-check",
)


# ---- field spec helpers ----------------------------------------------------------------------


def _f(type_: str, label: str, **kw: Any) -> dict[str, Any]:
    return {"type": type_, "label": label, **kw}


def text(label, max=120, **kw):  # noqa: A002
    return _f("text", label, max=max, **kw)


def textarea(label, max=600, **kw):  # noqa: A002
    return _f("textarea", label, max=max, **kw)


def cta(label="Button", **kw):
    return _f("cta", label, **kw)


def media(label="Image", **kw):
    return _f("media", label, **kw)


EYEBROW = text("Small label above the heading", 80, help="Optional, e.g. “From the journal”.")
HEADING = text("Heading", 120, required=True)
OPTIONAL_HEADING = text("Heading", 120)
DESCRIPTION = textarea("Description", 400)
ARTICLE_COUNT = _f("number", "Number of articles", min=1, max=12, default=3)


SECTION_TYPES: dict[str, dict[str, Any]] = {
    "hero": {
        "label": "Hero banner",
        "category": "Introductions",
        "description": "The large opening section with the main headline and buttons.",
        "variants": {
            "split": "Text with illustration or image",
            "centered": "Centred text",
            "full_width": "Full-width background image",
        },
        "fields": {
            "eyebrow": EYEBROW,
            "heading": text("Headline", 120, required=True),
            "highlight": text("Highlighted second line", 120, help="Shown in italic sage."),
            "body": textarea("Supporting text", 400),
            "media": media(
                "Image",
                required_for=["full_width"],
                show_for=["split", "full_width"],
                help="Optional for the split layout: the brand illustration is used when empty.",
            ),
            "primary_cta": cta("Main button"),
            "secondary_cta": cta("Second button"),
        },
        "design": ["background", "spacing", "align", "heading_size"],
        "defaults": {
            "variant": "split",
            "design": {"background": "ivory", "spacing": "lg", "align": "left"},
            "content": {"heading": "A clear, encouraging headline"},
        },
    },
    "brand_intro": {
        "label": "Brand mission",
        "category": "Introductions",
        "description": "Who we are and why we exist, with an optional verified community figure.",
        "variants": {
            "with_stat": "With community figure",
            "with_image": "With image",
            "text_only": "Text only",
        },
        "fields": {
            "eyebrow": EYEBROW,
            "heading": HEADING,
            "body": textarea("Text", 1500, help="Separate paragraphs with a blank line."),
            "cta": cta(),
            "stat_caption": textarea(
                "Community figure caption",
                300,
                show_for=["with_stat"],
                help="The figure itself comes from Settings › LinkedIn follower count (verified).",
            ),
            "media": media(required_for=["with_image"], show_for=["with_image"]),
        },
        "design": ["background", "spacing", "aspect_ratio"],
        "defaults": {
            "variant": "text_only",
            "design": {"background": "cream", "spacing": "md"},
            "content": {"heading": "Our mission"},
        },
    },
    "featured_articles": {
        "label": "Featured articles",
        "category": "Articles",
        "description": "Articles marked as featured, or a hand-picked selection.",
        "variants": {
            "lead_and_grid": "Large lead article and grid",
            "grid_3": "Three-column cards",
            "carousel": "Horizontal scrolling row",
        },
        "fields": {
            "eyebrow": EYEBROW,
            "heading": HEADING,
            "description": DESCRIPTION,
            "mode": _f(
                "select",
                "Which articles",
                choices={"featured": "Articles marked as featured", "manual": "Choose articles"},
                default="featured",
            ),
            "articles": _f(
                "articles", "Articles", max_items=12, show_for_mode="manual", help="In this order."
            ),
            "count": ARTICLE_COUNT,
            "cta": cta("Link button"),
        },
        "design": ["background", "spacing", "card_style", "align"],
        "defaults": {
            "variant": "grid_3",
            "design": {"background": "cream", "spacing": "md"},
            "content": {"heading": "Featured articles", "mode": "featured", "count": 3},
        },
    },
    "latest_articles": {
        "label": "Latest articles",
        "category": "Articles",
        "description": "The most recently published articles, optionally from one topic.",
        "variants": {"grid_3": "Three-column cards", "grid_4": "Four-column cards", "list": "List"},
        "fields": {
            "eyebrow": EYEBROW,
            "heading": HEADING,
            "description": DESCRIPTION,
            "topic": _f("topics", "Only from this topic", max_items=1, help="Optional."),
            "count": {**ARTICLE_COUNT, "default": 6},
            "cta": cta("Link button"),
        },
        "design": ["background", "spacing", "card_style", "align"],
        "defaults": {
            "variant": "grid_3",
            "design": {"background": "ivory", "spacing": "md"},
            "content": {"heading": "Latest articles", "count": 6},
        },
    },
    "article_collection": {
        "label": "Selected article collection",
        "category": "Articles",
        "description": "A hand-picked reading list in your chosen order.",
        "variants": {"grid_3": "Three-column cards", "grid_2": "Two-column cards", "list": "List"},
        "fields": {
            "eyebrow": EYEBROW,
            "heading": HEADING,
            "description": DESCRIPTION,
            "articles": _f("articles", "Articles", max_items=12, required=True),
            "cta": cta("Link button"),
        },
        "design": ["background", "spacing", "card_style", "align"],
        "defaults": {
            "variant": "grid_3",
            "design": {"background": "ivory", "spacing": "md"},
            "content": {"heading": "Recommended reading"},
        },
    },
    "topics_grid": {
        "label": "Topic cards",
        "category": "Articles",
        "description": "Cards linking to topic pages: featured topics, all topics or a selection.",
        "variants": {"cards_3": "Three-column cards", "cards_4": "Four-column cards"},
        "fields": {
            "eyebrow": EYEBROW,
            "heading": HEADING,
            "description": DESCRIPTION,
            "mode": _f(
                "select",
                "Which topics",
                choices={
                    "featured": "Featured topics",
                    "all": "All active topics",
                    "manual": "Choose topics",
                },
                default="featured",
            ),
            "topics": _f("topics", "Topics", max_items=12, show_for_mode="manual"),
            "cta": cta("Link button"),
        },
        "design": ["background", "spacing", "align"],
        "defaults": {
            "variant": "cards_3",
            "design": {"background": "ivory", "spacing": "md"},
            "content": {"heading": "Explore by topic", "mode": "featured"},
        },
    },
    "quote": {
        "label": "Motivational quote",
        "category": "Inspiration",
        "description": "A short quote with an optional attribution.",
        "variants": {"minimal": "Minimal", "highlighted": "Highlighted card", "large": "Large"},
        "fields": {
            "quote": textarea("Quote", 400, required=True),
            "attribution": text("Attribution", 120, help="Only quote real people accurately."),
            "attribution_role": text("Attribution detail", 120),
        },
        "design": ["background", "spacing", "align"],
        "defaults": {
            "variant": "minimal",
            "design": {"background": "ivory", "spacing": "md", "align": "center"},
            "content": {"quote": "Small steps, taken consistently, change everything."},
        },
    },
    "inspirational_message": {
        "label": "Inspirational message",
        "category": "Inspiration",
        "description": "A short encouraging message with an optional button.",
        "variants": {"centered": "Centred", "banner": "Banner"},
        "fields": {
            "eyebrow": EYEBROW,
            "message": textarea("Message", 300, required=True),
            "body": textarea("Supporting text", 500),
            "cta": cta(),
        },
        "design": ["background", "spacing", "heading_size"],
        "defaults": {
            "variant": "centered",
            "design": {"background": "sage", "spacing": "md"},
            "content": {"message": "You are allowed to grow at your own pace."},
        },
    },
    "image_text": {
        "label": "Image and text feature",
        "category": "Content",
        "description": "An image beside a heading, text and buttons.",
        "variants": {
            "image_left": "Image left, text right",
            "image_right": "Text left, image right",
        },
        "fields": {
            "eyebrow": EYEBROW,
            "heading": HEADING,
            "body": textarea("Text", 1500, help="Separate paragraphs with a blank line."),
            "bullets": _f("string_list", "Bullet points", max=160, max_items=8),
            "media": media(required=True),
            "primary_cta": cta("Main button"),
            "secondary_cta": cta("Second button"),
        },
        "design": ["background", "spacing", "aspect_ratio"],
        "defaults": {
            "variant": "image_left",
            "design": {"background": "ivory", "spacing": "md", "aspect_ratio": "landscape"},
            "content": {"heading": "A feature worth highlighting"},
        },
    },
    "newsletter_cta": {
        "label": "Newsletter signup",
        "category": "Engagement",
        "description": (
            "The Positive Reset signup form (double opt-in). It collects addresses only when "
            "email sending and consent wording are configured; until then it shows an honest "
            "“opening soon” notice."
        ),
        "variants": {"panel": "Panel", "compact": "Compact"},
        "fields": {
            "eyebrow": text("Small label", 80, default="Weekly newsletter"),
            "heading": text("Heading", 120, help="Leave empty to use the newsletter name."),
            "description": textarea("Description", 300),
            "show_first_name": _f("boolean", "Ask for a first name (optional field)", default=True),
            "lead_magnet": _f(
                "lead_magnet",
                "Free resource (optional)",
                help="Offer an active lead magnet with this form. Subscribing stays optional "
                "unless the lead magnet itself says otherwise.",
            ),
            "show_learn_more": _f("boolean", "Show “What to expect” link", default=True),
        },
        "design": ["background", "spacing", "width"],
        "defaults": {
            "variant": "panel",
            "design": {"background": "ivory", "spacing": "sm", "width": "wide"},
            "content": {
                "description": "One thoughtful email each week to help you reset your mindset, "
                "find perspective, and keep moving forward."
            },
        },
    },
    "lead_magnet_signup": {
        "label": "Free resource signup",
        "category": "Engagement",
        "description": (
            "Offers a free resource (a lead magnet with real files) by secure email link. "
            "Newsletter opt-in is a separate, unticked choice."
        ),
        "variants": {"card": "Card", "split": "Split"},
        "fields": {
            "eyebrow": text("Small label", 80, default="Free resource"),
            "heading": text("Heading", 120, help="Leave empty to use the resource title."),
            "description": textarea("Description", 400),
            "lead_magnet": _f("lead_magnet", "Free resource", required=True),
            "show_first_name": _f(
                "boolean", "Ask for a first name (optional field)", default=False
            ),
        },
        "design": ["background", "spacing", "width"],
        "defaults": {
            "variant": "card",
            "design": {"background": "cream", "spacing": "md", "width": "wide"},
            "content": {},
        },
    },
    "product_previews": {
        "label": "Digital product showcase",
        "category": "Engagement",
        "description": (
            "Products from the shop catalogue: featured, newest, hand-picked, a collection or "
            "bundles. Prices appear only for products on sale; everything else is shown as an "
            "honest “coming soon” preview."
        ),
        "variants": {"grid": "Grid"},
        "fields": {
            "eyebrow": EYEBROW,
            "heading": HEADING,
            "description": DESCRIPTION,
            "mode": _f(
                "select",
                "Which products",
                choices={
                    "featured": "Featured first, then the catalogue order",
                    "latest": "Newest products",
                    "manual": "Choose products",
                    "collection": "A collection",
                    "bundles": "Bundles",
                },
                default="featured",
            ),
            "products": _f(
                "products",
                "Products",
                max_items=6,
                show_for_mode="manual",
                help="Only published products are shown, in this order.",
            ),
            "collection": _f(
                "product_collection",
                "Collection",
                max_items=1,
                show_for_mode="collection",
            ),
            "count": _f("number", "Number of products", min=1, max=6, default=3),
            "show_prices": _f(
                "boolean",
                "Show prices for products on sale",
                default=True,
                help="Prices are always shown with their currency (e.g. USD 12.00).",
            ),
            "footnote": text("Footnote", 200),
            "cta": cta("Link button"),
        },
        "design": ["background", "spacing", "align"],
        "defaults": {
            "variant": "grid",
            "design": {"background": "ivory", "spacing": "md"},
            "content": {
                "heading": "Coming soon",
                "count": 3,
                "footnote": "These titles are in development and not yet available to purchase.",
            },
        },
    },
    "promo_banner": {
        "label": "Promotional banner",
        "category": "Engagement",
        "description": "A bold banner for a campaign, series or upcoming release.",
        "variants": {"full_width": "Full width", "card": "Card"},
        "fields": {
            "eyebrow": EYEBROW,
            "heading": HEADING,
            "body": textarea("Text", 400),
            "media": media("Image (optional)"),
            "cta": cta(),
        },
        "design": ["background", "spacing", "button_style"],
        "defaults": {
            "variant": "card",
            "design": {"background": "sage_dark", "spacing": "md", "button_style": "light"},
            "content": {"heading": "Something new is on the way"},
        },
    },
    "call_to_action": {
        "label": "Call to action",
        "category": "Engagement",
        "description": "A focused invitation with one or two buttons.",
        "variants": {"centered": "Centred with ornament", "banner": "Full-width banner"},
        "fields": {
            "heading": HEADING,
            "body": textarea("Text", 400),
            "primary_cta": cta("Main button"),
            "secondary_cta": cta("Second button"),
        },
        "design": ["background", "spacing", "width", "heading_size"],
        "defaults": {
            "variant": "centered",
            "design": {"background": "ivory", "spacing": "lg", "width": "narrow"},
            "content": {"heading": "Ready for your next step?"},
        },
    },
    "testimonials": {
        "label": "Testimonials",
        "category": "Engagement",
        "description": "Genuine words from readers or partners, shared with permission.",
        "variants": {
            "cards_3": "Three columns",
            "cards_2": "Two columns",
            "single": "Large, one per row",
        },
        "fields": {
            "eyebrow": EYEBROW,
            "heading": OPTIONAL_HEADING,
            "items": _f(
                "items",
                "Testimonials",
                max_items=9,
                required=True,
                fields={
                    "quote": textarea("Quote", 500, required=True),
                    "name": text("Name", 80, required=True),
                    "role": text("Role or location", 120),
                    "media": media("Photo (optional)"),
                },
                help="Only publish genuine testimonials you have permission to share.",
            ),
        },
        "design": ["background", "spacing", "card_style", "align"],
        "defaults": {
            "variant": "cards_3",
            "design": {"background": "cream", "spacing": "md"},
            "content": {"heading": "Kind words"},
        },
    },
    "statistics": {
        "label": "Statistics",
        "category": "Engagement",
        "description": "A row of key figures.",
        "variants": {"row": "Row", "cards": "Cards"},
        "fields": {
            "eyebrow": EYEBROW,
            "heading": OPTIONAL_HEADING,
            "items": _f(
                "items",
                "Figures",
                max_items=6,
                required=True,
                fields={
                    "value": text("Figure", 24, required=True),
                    "label": text("Label", 120, required=True),
                },
                help="Use verified figures only.",
            ),
            "footnote": text("Footnote", 200, help="e.g. the source and date of the figures."),
        },
        "design": ["background", "spacing", "align"],
        "defaults": {
            "variant": "row",
            "design": {"background": "ivory", "spacing": "md", "align": "center"},
            "content": {},
        },
    },
    "faq": {
        "label": "FAQ",
        "category": "Content",
        "description": "Questions and answers in an accessible expandable list.",
        "variants": {"accordion": "Expandable list", "two_column": "Intro beside questions"},
        "fields": {
            "eyebrow": EYEBROW,
            "heading": text("Heading", 120, default="Frequently asked questions"),
            "intro": textarea("Introduction", 400),
            "items": _f(
                "items",
                "Questions",
                max_items=20,
                required=True,
                fields={
                    "question": text("Question", 200, required=True),
                    "answer": textarea("Answer", 1500, required=True),
                },
            ),
        },
        "design": ["background", "spacing", "width"],
        "defaults": {
            "variant": "accordion",
            "design": {"background": "ivory", "spacing": "md", "width": "narrow"},
            "content": {"heading": "Frequently asked questions"},
        },
    },
    "rich_text": {
        "label": "Custom content",
        "category": "Content",
        "description": "Free-form content built from text, headings, lists, images and quotes.",
        "variants": {"default": "Standard width", "narrow": "Narrow reading width"},
        "fields": {
            "heading": OPTIONAL_HEADING,
            "body": _f("rich", "Content", required=True),
        },
        "design": ["background", "spacing"],
        "defaults": {
            "variant": "narrow",
            "design": {"background": "ivory", "spacing": "md"},
            "content": {"body": [{"type": "paragraph", "text": "Write your content here."}]},
        },
    },
    "feature_list": {
        "label": "Feature list",
        "category": "Content",
        "description": "Short benefits or principles, each with an icon.",
        "variants": {
            "sticky_intro": "Introduction beside features",
            "grid_3": "Three-column grid",
            "grid_4": "Four-column grid",
        },
        "fields": {
            "eyebrow": EYEBROW,
            "heading": HEADING,
            "description": textarea("Description", 600),
            "quote": textarea("Highlighted quote", 300),
            "items": _f(
                "items",
                "Features",
                max_items=8,
                required=True,
                fields={
                    "title": text("Title", 80, required=True),
                    "text": textarea("Text", 300),
                    "icon": _f(
                        "select",
                        "Icon",
                        choices={i: i.replace("-", " ").capitalize() for i in FEATURE_ICONS},
                        default="sun",
                    ),
                },
            ),
        },
        "design": ["background", "spacing", "card_style"],
        "defaults": {
            "variant": "grid_3",
            "design": {"background": "beige", "spacing": "md"},
            "content": {"heading": "Why it helps"},
        },
    },
    "partnership_cta": {
        "label": "Partnership invitation",
        "category": "Engagement",
        "description": "An invitation for brands and organisations with a list of opportunities.",
        "variants": {"dark": "Dark", "light": "Light"},
        "fields": {
            "eyebrow": EYEBROW,
            "heading": HEADING,
            "body": textarea("Text", 800),
            "cta": cta(),
            "list_heading": text("List heading", 80),
            "items": _f("string_list", "Opportunities", max=80, max_items=10),
        },
        "design": ["spacing"],
        "defaults": {
            "variant": "dark",
            "design": {"spacing": "lg"},
            "content": {"heading": "Partner with us"},
        },
    },
    "author_intro": {
        "label": "Author introduction",
        "category": "Content",
        "description": "Introduce an author using their profile (portrait, name and bio).",
        "variants": {"card": "Card", "split": "Portrait beside text"},
        "fields": {
            "eyebrow": text("Small label", 80, default="About the author"),
            "author": _f("author", "Author", required=True),
            "body": textarea("Extra text", 800, help="Optional. The author's bio is shown first."),
            "cta": cta(),
        },
        "design": ["background", "spacing"],
        "defaults": {
            "variant": "card",
            "design": {"background": "cream", "spacing": "md"},
            "content": {"eyebrow": "About the author"},
        },
    },
    "resource_list": {
        "label": "Resource recommendations",
        "category": "Content",
        "description": "Recommended resources, guides or pages, each with a link.",
        "variants": {"cards": "Cards", "list": "List"},
        "fields": {
            "eyebrow": EYEBROW,
            "heading": HEADING,
            "description": DESCRIPTION,
            "items": _f(
                "items",
                "Resources",
                max_items=9,
                required=True,
                fields={
                    "title": text("Title", 120, required=True),
                    "description": textarea("Description", 300),
                    "url": _f("link", "Link", required=True),
                    "link_label": text("Link text", 60, default="Learn more"),
                    "media": media("Image (optional)"),
                },
            ),
        },
        "design": ["background", "spacing", "card_style", "aspect_ratio"],
        "defaults": {
            "variant": "cards",
            "design": {"background": "ivory", "spacing": "md", "aspect_ratio": "landscape"},
            "content": {"heading": "Helpful resources"},
        },
    },
    "contact_details": {
        "label": "Contact details",
        "category": "Engagement",
        "description": (
            "Contact email addresses from Settings. There is no contact form, so nothing is "
            "collected on the website."
        ),
        "variants": {"default": "Standard"},
        "fields": {
            "heading": HEADING,
            "body": textarea("Text", 800),
            "show_email": _f("boolean", "Show the contact email", default=True),
            "show_partnerships_email": _f("boolean", "Show the partnerships email", default=False),
            "note": text("Small print", 200),
        },
        "design": ["background", "spacing", "width"],
        "defaults": {
            "variant": "default",
            "design": {"background": "cream", "spacing": "md", "width": "narrow"},
            "content": {"heading": "Get in touch", "show_email": True},
        },
    },
    "page_header": {
        "label": "Page header",
        "category": "Introductions",
        "description": "The title area at the top of a page, with breadcrumbs for sub-pages.",
        "variants": {"default": "Standard", "centered": "Centred", "with_image": "With image"},
        "fields": {
            "eyebrow": EYEBROW,
            "heading": text("Heading", 120, help="Leave empty to use the page title."),
            "intro": textarea("Introduction", 500),
            "media": media(required_for=["with_image"], show_for=["with_image"]),
        },
        "design": ["background", "spacing", "heading_size"],
        "defaults": {
            "variant": "default",
            "design": {"background": "cream", "spacing": "md"},
            "content": {},
        },
    },
    "section_group": {
        "label": "Shared section group",
        "category": "Shared",
        "description": "Several shared sections shown together, in order.",
        "reusable_only": True,
        "variants": {"default": "In order"},
        "fields": {
            "items": _f("reusables", "Shared sections", max_items=6, required=True),
        },
        "design": [],
        "defaults": {"variant": "default", "design": {}, "content": {}},
    },
}

# Section types that only make sense once per page.
SINGLE_USE = {"hero", "page_header"}
CATEGORIES = ["Introductions", "Articles", "Inspiration", "Content", "Engagement", "Shared"]


# ---- validation -----------------------------------------------------------------------------


class Refs:
    """Database references found while validating, checked by the service layer."""

    def __init__(self) -> None:
        self.items: list[tuple[str, int, str]] = []

    def add(self, kind: str, value: int, path: str) -> None:
        self.items.append((kind, value, path))

    def ids(self, kind: str) -> set[int]:
        return {v for k, v, _ in self.items if k == kind}


def _visible_for(spec: dict[str, Any], variant: str, content: dict[str, Any]) -> bool:
    if "show_for" in spec and variant not in spec["show_for"]:
        return False
    return not ("show_for_mode" in spec and content.get("mode") != spec["show_for_mode"])


def _required(spec: dict[str, Any], variant: str) -> bool:
    return bool(spec.get("required")) or variant in spec.get("required_for", ())


def _clean_text(value, spec, required, errors, path):
    if value is None:
        value = spec.get("default", "")
    if not isinstance(value, str):
        errors[path] = ["Must be text."]
        return ""
    value = value.replace("\r\n", "\n").strip()
    if spec["type"] == "text":
        value = " ".join(value.split())
    problems = []
    if required and not value:
        problems.append("This field is required.")
    if len(value) > spec.get("max", 200):
        problems.append(f"Must be at most {spec.get('max', 200)} characters.")
    if value and (problem := plain_text_problem(value)):
        problems.append(problem)
    if problems:
        errors[path] = problems
    return value


def _clean_link(value, required, errors, path):
    value = (value or "").strip() if isinstance(value, str) or value is None else None
    if value is None:
        errors[path] = ["Must be a link."]
        return ""
    if required and not value:
        errors[path] = ["This field is required."]
    elif value and not (is_internal_path(value) or is_https_url(value)):
        errors[path] = ["Use a site path starting with / or a full https:// link."]
    elif len(value) > 500:
        errors[path] = ["Links must be at most 500 characters."]
    return value


def _clean_cta(value, required, errors, path, refs):
    empty = {"label": "", "url": "", "style": "", "cta_id": None}
    if value in (None, ""):
        if required:
            errors[path] = ["Add a button."]
        return empty
    if not isinstance(value, dict) or set(value) - {"label", "url", "style", "cta_id"}:
        errors[path] = ["Buttons need a label and a link."]
        return empty
    style = value.get("style") or ""
    if style and style not in BUTTON_STYLES:
        errors[f"{path}.style"] = [f"Use one of: {', '.join(BUTTON_STYLES)}."]
        style = ""
    cta_id = value.get("cta_id")
    if cta_id not in (None, ""):
        if not isinstance(cta_id, int) or isinstance(cta_id, bool):
            errors[f"{path}.cta_id"] = ["Choose a saved call to action."]
            return empty
        refs.add("cta", cta_id, path)
        return {"label": "", "url": "", "style": style, "cta_id": cta_id}
    label = _clean_text(
        value.get("label"), {"type": "text", "max": 60}, False, errors, f"{path}.label"
    )
    url = _clean_link(value.get("url"), False, errors, f"{path}.url")
    if bool(label) != bool(url):
        errors.setdefault(f"{path}.label" if not label else f"{path}.url", []).append(
            "A button needs both a label and a link."
        )
    if required and not label:
        errors.setdefault(path, []).append("Add a button.")
    return {"label": label, "url": url, "style": style, "cta_id": None}


def _clean_id(value, kind, required, errors, path, refs):
    if value in (None, ""):
        if required:
            errors[path] = ["This field is required."]
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        errors[path] = ["Choose an item from the list."]
        return None
    refs.add(kind, value, path)
    return value


def _clean_id_list(value, kind, spec, required, errors, path, refs):
    value = value or []
    if not isinstance(value, list) or not all(
        isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value
    ):
        errors[path] = ["Choose items from the list."]
        return []
    if len(set(value)) != len(value):
        errors[path] = ["Each item can only be chosen once."]
    if len(value) > spec.get("max_items", 12):
        errors[path] = [f"Choose at most {spec.get('max_items', 12)}."]
    if required and not value:
        errors[path] = ["Choose at least one."]
    for i, item in enumerate(value):
        refs.add(kind, item, f"{path}.{i}")
    return value


def _clean_field(name, spec, value, variant, content, errors, refs, path):
    required = _required(spec, variant) and _visible_for(spec, variant, content)
    kind = spec["type"]
    if kind in ("text", "textarea"):
        return _clean_text(value, spec, required, errors, path)
    if kind == "link":
        return _clean_link(value, required, errors, path)
    if kind == "cta":
        return _clean_cta(value, required, errors, path, refs)
    if kind == "media":
        return _clean_id(value, "media", required, errors, path, refs)
    if kind == "author":
        return _clean_id(value, "author", required, errors, path, refs)
    if kind in ("articles", "topics", "reusables", "products", "product_collection"):
        ref_kind = {
            "articles": "article",
            "topics": "topic",
            "reusables": "reusable",
            "products": "product",
            "product_collection": "product_collection",
        }[kind]
        return _clean_id_list(value, ref_kind, spec, required, errors, path, refs)
    if kind == "lead_magnet":
        if value in (None, ""):
            if required:
                errors[path] = ["Choose a free resource."]
            return None
        from sqlalchemy import select

        from ..extensions import db
        from ..models import LeadMagnet

        if not isinstance(value, str) or not db.session.scalar(
            select(LeadMagnet.id).where(LeadMagnet.slug == value, LeadMagnet.status != "archived")
        ):
            errors[path] = ["Choose a free resource from the list."]
            return None
        return value
    if kind == "select":
        value = spec.get("default") if value in (None, "") else value
        if value not in spec["choices"]:
            errors[path] = [f"Use one of: {', '.join(spec['choices'])}."]
            return spec.get("default")
        return value
    if kind == "number":
        value = spec.get("default") if value in (None, "") else value
        if not isinstance(value, int) or isinstance(value, bool):
            errors[path] = ["Must be a whole number."]
            return spec.get("default")
        if not spec["min"] <= value <= spec["max"]:
            errors[path] = [f"Must be between {spec['min']} and {spec['max']}."]
        return value
    if kind == "boolean":
        value = spec.get("default", False) if value is None else value
        if not isinstance(value, bool):
            errors[path] = ["Must be true or false."]
            return bool(spec.get("default", False))
        return value
    if kind == "string_list":
        value = value or []
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            errors[path] = ["Must be a list of text items."]
            return []
        items = [" ".join(v.split()) for v in value if v.strip()]
        problems = []
        if len(items) > spec.get("max_items", 10):
            problems.append(f"At most {spec.get('max_items', 10)} items.")
        for item in items:
            if len(item) > spec["max"]:
                problems.append(f"Items must be at most {spec['max']} characters.")
            if problem := plain_text_problem(item):
                problems.append(problem)
        if problems:
            errors[path] = sorted(set(problems))
        return items
    if kind == "rich":
        from .blocks import validate_blocks

        if value in (None, "") and not required:
            return []
        if isinstance(value, str):  # legacy plain-text body
            value = [{"type": "paragraph", "text": p} for p in value.split("\n\n") if p.strip()]
        try:
            blocks = validate_blocks(value)
        except ValidationError as exc:
            details = (exc.details or {}).get("body", exc.details)
            errors[path] = [details] if isinstance(details, str) else details
            return value if isinstance(value, list) else []
        if required and not blocks:
            errors[path] = ["Add some content."]
        for block in blocks:
            if isinstance(block.get("media_id"), int):
                refs.add("media", block["media_id"], path)
            for item in block.get("items", []) if block.get("type") == "gallery" else []:
                refs.add("media", item["media_id"], path)
        return blocks
    if kind == "items":
        value = value or []
        if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
            errors[path] = ["Must be a list of items."]
            return []
        if len(value) > spec.get("max_items", 10):
            errors[path] = [f"At most {spec.get('max_items', 10)} items."]
        if required and not value:
            errors[path] = ["Add at least one item."]
        cleaned = []
        for index, item in enumerate(value):
            unknown = set(item) - set(spec["fields"])
            if unknown:
                errors[f"{path}.{index}"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]
            cleaned.append(
                {
                    sub: _clean_field(
                        sub,
                        sub_spec,
                        item.get(sub),
                        variant,
                        {},
                        errors,
                        refs,
                        f"{path}.{index}.{sub}",
                    )
                    for sub, sub_spec in spec["fields"].items()
                }
            )
        return cleaned
    raise AssertionError(f"Unhandled field type {kind}")  # pragma: no cover


def check_section(
    section_type: str,
    variant: str | None,
    content: Any,
    design: Any = None,
    visibility: Any = None,
) -> tuple[dict[str, Any], dict[str, list], Refs]:
    """Validate one section. Returns (clean, errors, refs) without raising."""
    definition = SECTION_TYPES.get(section_type)
    refs = Refs()
    if definition is None:
        return {}, {"section_type": ["Unknown section type."]}, refs
    errors: dict[str, Any] = {}
    variant = variant or definition["defaults"]["variant"]
    if variant not in definition["variants"]:
        errors["variant"] = [f"Use one of: {', '.join(definition['variants'])}."]
        variant = definition["defaults"]["variant"]
    if content is None:
        content = {}
    if not isinstance(content, dict):
        return {}, {"content": ["Content must be an object."]}, refs
    unknown = set(content) - set(definition["fields"])
    if unknown:
        errors["content"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]
    clean_content = {
        name: _clean_field(name, spec, content.get(name), variant, content, errors, refs, name)
        for name, spec in definition["fields"].items()
    }
    clean_design, design_errors = validate_design(
        definition["design"], definition["defaults"].get("design", {}), design
    )
    clean_visibility, visibility_errors = validate_visibility(visibility)
    errors.update(design_errors)
    errors.update(visibility_errors)
    return (
        {
            "variant": variant,
            "content": clean_content,
            "design": clean_design,
            "visibility": clean_visibility,
        },
        errors,
        refs,
    )


def validate_section(section_type: str, variant: str, content: Any) -> dict[str, Any]:
    """Validate section content only (Batch 02 API); raises ValidationError."""
    clean, errors, _ = check_section(section_type, variant, content)
    if errors:
        raise ValidationError("The section content is invalid.", details=errors)
    return clean["content"]


def default_section(section_type: str) -> dict[str, Any]:
    definition = SECTION_TYPES[section_type]
    clean, _, _ = check_section(
        section_type,
        definition["defaults"]["variant"],
        definition["defaults"].get("content", {}),
        definition["defaults"].get("design", {}),
    )
    return clean


def section_types_schema() -> list[dict[str, Any]]:
    """Field and design definitions for the admin section editor."""

    def field_schema(name: str, spec: dict[str, Any]) -> dict[str, Any]:
        out = {"name": name, **{k: v for k, v in spec.items() if k != "fields"}}
        if "choices" in spec:
            out["choices"] = [{"value": v, "label": label} for v, label in spec["choices"].items()]
        if spec["type"] == "items":
            out["fields"] = [field_schema(n, s) for n, s in spec["fields"].items()]
        return out

    return [
        {
            "type": key,
            "label": spec["label"],
            "category": spec["category"],
            "description": spec["description"],
            "reusable_only": spec.get("reusable_only", False),
            "single_use": key in SINGLE_USE,
            "variants": [{"value": v, "label": label} for v, label in spec["variants"].items()],
            "fields": [field_schema(n, s) for n, s in spec["fields"].items()],
            "design": design_schema(spec["design"]),
            "defaults": default_section(key),
        }
        for key, spec in SECTION_TYPES.items()
    ]
