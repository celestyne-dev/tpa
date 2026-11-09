"""Page templates: sensible starter sections for new pages (always fully editable)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# The built-in legal pages' wording, kept identical to frontend/src/data/legal/
# legalDocuments.json (tests/test_company_legal_pages.py checks this). A CMS page created
# from a legal template starts as an exact copy of the page that is live today.
LEGAL_DOCUMENTS: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).with_name("legal_documents.json")).read_text(encoding="utf-8")
)


def _cta(label: str, url: str, style: str = "") -> dict[str, Any]:
    return {"label": label, "url": url, "style": style, "cta_id": None}


def _s(section_type: str, name: str, variant: str, content: dict, design: dict | None = None):
    return {
        "section_type": section_type,
        "name": name,
        "variant": variant,
        "content": content,
        "design": design or {},
    }


# The company pages' copy, kept identical to frontend/src/data/company/companyPages.json
# (the built-in pages render from that file; tests/test_company_pages_premium.py checks
# the two match and that these templates use them). A page created from one of these
# templates starts with exactly the wording the built-in page shows.
COMPANY: dict[str, Any] = json.loads(
    (Path(__file__).with_name("company_pages.json")).read_text(encoding="utf-8")
)


def _icon_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"icon": i["icon"], "title": i["title"], "text": i["text"]} for i in items]


def _about_template() -> dict[str, Any]:
    c = COMPANY["about"]
    story = c["story"]
    return {
        "label": "About page",
        "description": (
            "The About page as editable sections: introduction, our story (with an optional "
            "founder photo), mission, values, editorial approach, verified community figures "
            "and a closing invitation. Add an Author introduction section for a founder "
            "profile. Publish it at /about to replace the built-in page."
        ),
        "slug": "about",
        "meta_description": c["meta_description"],
        "sections": [
            _s(
                "page_header",
                "Introduction",
                "default",
                {"eyebrow": c["eyebrow"], "heading": c["title"], "intro": c["intro"]},
            ),
            _s(
                "image_text",
                "Our story",
                "image_right",
                {
                    "eyebrow": story["eyebrow"],
                    "heading": story["heading"],
                    "body": story["body"].replace("{community}", story["community_default"])
                    + "\n\n"
                    + story["quote"],
                },
            ),
            _s(
                "inspirational_message",
                "Our mission",
                "centered",
                {"eyebrow": c["mission"]["eyebrow"], "message": c["mission"]["default"]},
                {"background": "cream"},
            ),
            _s(
                "feature_list",
                "What we believe",
                "grid_4",
                {
                    "eyebrow": c["values"]["eyebrow"],
                    "heading": c["values"]["heading"],
                    "description": c["values"]["description"],
                    "items": _icon_items(c["values"]["items"]),
                },
            ),
            _s(
                "feature_list",
                "Our editorial approach",
                "grid_3",
                {
                    "eyebrow": c["editorial"]["eyebrow"],
                    "heading": c["editorial"]["heading"],
                    "items": _icon_items(c["editorial"]["items"]),
                },
                {"background": "cream"},
            ),
            _s(
                "audience_metrics",
                "Our community",
                "cards",
                {
                    "eyebrow": c["community"]["eyebrow"],
                    "heading": c["community"]["heading"],
                    "description": c["community"]["note"],
                    "metric_group": "all",
                    "count": 4,
                },
            ),
            _s(
                "call_to_action",
                "Closing invitation",
                "centered",
                {
                    "heading": c["closing"]["heading"],
                    "body": c["closing"]["body"],
                    "primary_cta": _cta(c["primary_action"]["label"], c["primary_action"]["href"]),
                    "secondary_cta": _cta(
                        c["secondary_action"]["label"], c["secondary_action"]["href"], "outline"
                    ),
                },
                {"background": "beige"},
            ),
        ],
    }


def _contact_template() -> dict[str, Any]:
    c = COMPANY["contact"]
    return {
        "label": "Contact page",
        "description": (
            "The Contact page as editable sections: introduction, contact cards (addresses "
            "from Settings) and the urgent-support notice. Publish it at /contact to replace "
            "the built-in page."
        ),
        "slug": "contact",
        "meta_description": c["meta_description"],
        "sections": [
            _s(
                "page_header",
                "Introduction",
                "default",
                {"eyebrow": c["eyebrow"], "heading": c["title"], "intro": c["intro"]},
            ),
            _s(
                "contact_cards",
                "Ways to reach us",
                "cards_3",
                {
                    "items": [
                        {
                            "icon": card["icon"],
                            "title": card["title"],
                            "text": card["text"],
                            "email": card["email"],
                            "cta_label": (card["action"] or {}).get("label", ""),
                            "cta_url": (card["action"] or {}).get("href", ""),
                        }
                        for card in c["cards"]
                    ],
                    "fallback": c["fallback"],
                },
            ),
            _s(
                "notice_panel",
                "Urgent support",
                "important",
                {"heading": c["urgent"]["heading"], "body": c["urgent"]["body"]},
            ),
        ],
    }


INQUIRY_ANCHOR = "/partner-with-us#partnership-inquiry"


def _partner_template() -> dict[str, Any]:
    c = COMPANY["partner"]
    return {
        "label": "Partner With Us page",
        "description": (
            "A partnership landing page: hero with an inquiry button that jumps to the form, "
            "audience, collaboration formats, reasons to partner, brand alignment, verified "
            "audience figures, the media kit, the inquiry form and a closing invitation. "
            "Publish it at /partner-with-us to replace the built-in page."
        ),
        "slug": "partner-with-us",
        "meta_description": c["meta_description"],
        "sections": [
            _s(
                "hero",
                "Hero",
                "centered",
                {
                    "eyebrow": c["eyebrow"],
                    "heading": c["title"],
                    "body": c["intro"],
                    "primary_cta": _cta(c["inquiry_action"], INQUIRY_ANCHOR),
                    "secondary_cta": _cta(c["media_kit_action"], "/advertise", "outline"),
                },
                {"background": "cream", "spacing": "md", "align": "center"},
            ),
            _s(
                "image_text",
                "Our audience",
                "image_right",
                {
                    "eyebrow": c["audience"]["eyebrow"],
                    "heading": c["audience"]["heading"],
                    "body": "\n\n".join(c["audience"]["paragraphs"]),
                },
            ),
            _s(
                "feature_list",
                "Collaboration opportunities",
                "grid_3",
                {
                    "eyebrow": c["formats"]["eyebrow"],
                    "heading": c["formats"]["heading"],
                    "description": c["formats"]["description"],
                    "items": _icon_items(c["formats"]["items"]),
                },
                {"background": "cream"},
            ),
            _s(
                "feature_list",
                "Why partner with us",
                "grid_3",
                {
                    "eyebrow": c["reasons"]["eyebrow"],
                    "heading": c["reasons"]["heading"],
                    "items": _icon_items(c["reasons"]["items"]),
                },
            ),
            _s(
                "image_text",
                "Brand alignment",
                "image_left",
                {
                    "eyebrow": c["alignment"]["eyebrow"],
                    "heading": c["alignment"]["heading"],
                    "body": c["alignment"]["description"],
                    "bullets": c["alignment"]["items"],
                },
                {"background": "cream"},
            ),
            _s(
                "audience_metrics",
                "Audience figures",
                "cards",
                {
                    "eyebrow": c["figures"]["eyebrow"],
                    "heading": c["figures"]["heading"],
                    "description": c["figures"]["note"],
                    "metric_group": "all",
                    "count": 4,
                },
            ),
            _s(
                "media_kit_summary",
                "Media kit",
                "panel",
                {
                    "heading": c["media_kit"]["heading"],
                    "description": c["media_kit"]["published"],
                    "show_metrics": False,
                    "cta": _cta(c["media_kit"]["view_label"], "/advertise"),
                },
                {"background": "beige"},
            ),
            _s(
                "partnership_inquiry",
                "Inquiry form",
                "panel",
                {
                    "heading": c["inquiry"]["form_heading"],
                    "description": " ".join(c["inquiry"]["steps"]),
                },
            ),
            _s(
                "call_to_action",
                "Closing invitation",
                "centered",
                {
                    "heading": c["closing"]["heading"],
                    "body": c["closing"]["body"],
                    "primary_cta": _cta(c["inquiry_action"], INQUIRY_ANCHOR),
                },
                {"background": "beige"},
            ),
        ],
    }


def _advertise_template() -> dict[str, Any]:
    c = COMPANY["advertise"]
    note = c["audience"]["note"]
    return {
        "label": "Advertise / media kit page",
        "description": (
            "A media kit landing page: hero, the media kit summary, verified social and "
            "website figures, collaboration formats and an inquiry invitation. Figures come "
            "from Partnerships › Audience metrics (verified, dated). Publish it at /advertise "
            "to replace the built-in page."
        ),
        "slug": "advertise",
        "meta_description": c["meta_description"],
        "sections": [
            _s(
                "hero",
                "Hero",
                "centered",
                {
                    "eyebrow": c["eyebrow"],
                    "heading": c["title"],
                    "body": c["intro"],
                    "primary_cta": _cta(c["inquiry_action"], INQUIRY_ANCHOR),
                },
                {"background": "cream", "spacing": "md", "align": "center"},
            ),
            _s(
                "media_kit_summary",
                "Media kit",
                "panel",
                {"heading": "About Think Positive Always", "show_metrics": False},
            ),
            _s(
                "audience_metrics",
                "Social audience",
                "cards",
                {
                    "eyebrow": "Audience",
                    "heading": c["audience"]["social_heading"],
                    "description": note,
                    "metric_group": "social",
                    "count": 4,
                },
                {"background": "cream"},
            ),
            _s(
                "audience_metrics",
                "Website audience",
                "cards",
                {
                    "eyebrow": "Audience",
                    "heading": c["audience"]["website_heading"],
                    "metric_group": "website",
                    "count": 4,
                },
                {"background": "cream"},
            ),
            _s(
                "feature_list",
                "Formats",
                "grid_3",
                {
                    "eyebrow": c["formats"]["eyebrow"],
                    "heading": c["formats"]["heading"],
                    "items": _icon_items(c["formats"]["items"]),
                },
            ),
            _s(
                "call_to_action",
                "Inquiry invitation",
                "centered",
                {
                    "heading": c["closing"]["heading"],
                    "body": c["closing"]["body"],
                    "primary_cta": _cta(c["closing"]["action"], INQUIRY_ANCHOR),
                },
                {"background": "beige"},
            ),
        ],
    }


def _legal_template(key: str, slug: str) -> dict[str, Any]:
    doc = LEGAL_DOCUMENTS[key]
    return {
        "label": f"{doc['title']} (legal document)",
        "description": (
            f"The current {doc['title']} wording in the legal page layout, ready to manage in "
            f"the CMS. Publish it at /{slug} to replace the built-in page."
        ),
        "slug": slug,
        "meta_description": doc["meta_description"],
        "sections": [
            _s(
                "legal_document",
                "Document",
                "default",
                {
                    "eyebrow": "Legal",
                    "heading": doc["title"],
                    "summary": doc["summary"],
                    "effective_date": doc["effective_date"],
                    "last_updated": doc["last_updated"],
                    "notice_title": doc["notice"]["title"],
                    "notice": doc["notice"]["text"],
                    "body": doc["body"],
                    "show_toc": True,
                    "show_related": True,
                },
            )
        ],
    }


PAGE_TEMPLATES: dict[str, dict[str, Any]] = {
    "standard": {
        "label": "Standard content page",
        "description": "A page header and free-form content. Good for About or policy pages.",
        "sections": [
            _s(
                "page_header",
                "Page header",
                "default",
                {"intro": "A short introduction to this page."},
            ),
            _s(
                "rich_text",
                "Main content",
                "narrow",
                {"body": [{"type": "paragraph", "text": "Write the page content here."}]},
            ),
        ],
    },
    "landing": {
        "label": "Landing page",
        "description": "A hero, an image-and-text feature, highlights and a call to action.",
        "sections": [
            _s(
                "hero",
                "Hero",
                "centered",
                {
                    "heading": "A clear promise for your visitors",
                    "body": "One or two sentences that explain why this page matters.",
                    "primary_cta": _cta("Get started", "/articles"),
                },
                {"background": "cream", "spacing": "lg", "align": "center"},
            ),
            _s(
                "feature_list",
                "Highlights",
                "grid_3",
                {
                    "heading": "What you will find",
                    "items": [
                        {
                            "title": "Practical",
                            "text": "Ideas you can use today.",
                            "icon": "compass",
                        },
                        {"title": "Encouraging", "text": "Honest, kind support.", "icon": "sun"},
                        {"title": "Actionable", "text": "Clear next steps.", "icon": "footprints"},
                    ],
                },
                {"background": "ivory"},
            ),
            _s(
                "call_to_action",
                "Call to action",
                "banner",
                {
                    "heading": "Ready to take the next step?",
                    "primary_cta": _cta("Read the articles", "/articles"),
                },
                {"background": "sage_dark"},
            ),
        ],
    },
    "newsletter": {
        "label": "Newsletter landing page",
        "description": "Introduces The Positive Reset with an honest sign-up panel and FAQ.",
        "sections": [
            _s(
                "page_header",
                "Page header",
                "centered",
                {"eyebrow": "The Positive Reset", "intro": "One thoughtful email each day."},
            ),
            _s("newsletter_cta", "Newsletter", "panel", {"show_learn_more": False}),
            _s(
                "faq",
                "Questions",
                "accordion",
                {
                    "items": [
                        {
                            "question": "How often will I hear from you?",
                            "answer": "Once a day: one short, thoughtful email.",
                        }
                    ]
                },
            ),
        ],
    },
    "lead_magnet": {
        "label": "Resource landing page",
        "description": "Presents a free resource with its benefits and recommended reading.",
        "sections": [
            _s(
                "hero",
                "Hero",
                "split",
                {
                    "eyebrow": "Free resource",
                    "heading": "Name of the resource",
                    "body": "Describe who it is for and what it helps with.",
                    "primary_cta": _cta("Explore free resources", "/free-resources"),
                },
            ),
            _s(
                "resource_list",
                "Inside the resource",
                "cards",
                {
                    "heading": "Related resources",
                    "items": [
                        {
                            "title": "Free resources",
                            "url": "/free-resources",
                            "link_label": "Browse",
                        }
                    ],
                },
            ),
            _s("newsletter_cta", "Newsletter", "compact", {}),
        ],
    },
    "campaign": {
        "label": "Promotional campaign page",
        "description": "A campaign banner, a short message and selected articles.",
        "sections": [
            _s(
                "promo_banner",
                "Campaign banner",
                "full_width",
                {
                    "eyebrow": "Special series",
                    "heading": "Campaign headline",
                    "body": "What the campaign is about.",
                },
                {"background": "sage_dark", "button_style": "light"},
            ),
            _s(
                "inspirational_message",
                "Message",
                "centered",
                {"message": "A short, encouraging message for this campaign."},
            ),
            _s("latest_articles", "Articles", "grid_3", {"heading": "Read the series", "count": 3}),
        ],
    },
    "partnership": {
        "label": "Partnership information page",
        "description": "Explains partnership opportunities and how to get in touch.",
        "sections": [
            _s(
                "page_header",
                "Page header",
                "default",
                {"eyebrow": "Partnerships", "intro": "Work with us."},
            ),
            _s(
                "partnership_cta",
                "Opportunities",
                "light",
                {
                    "heading": "Ways we can work together",
                    "list_heading": "Opportunities",
                    "items": ["Sponsored content", "Newsletter sponsorships"],
                },
            ),
            _s(
                "contact_details",
                "Contact",
                "default",
                {
                    "heading": "Start a conversation",
                    "show_email": False,
                    "show_partnerships_email": True,
                },
            ),
        ],
    },
    "coming_soon": {
        "label": "Coming-soon product page",
        "description": (
            "Announces an upcoming eBook or resource. There is no purchase button: the shop "
            "is not live yet."
        ),
        "sections": [
            _s(
                "hero",
                "Hero",
                "split",
                {
                    "eyebrow": "Coming soon",
                    "heading": "Title of the upcoming release",
                    "body": "What readers can look forward to.",
                    "primary_cta": _cta("Read related articles", "/articles"),
                },
            ),
            _s(
                "product_previews",
                "Upcoming titles",
                "grid",
                {"heading": "In development", "count": 3},
            ),
            _s("newsletter_cta", "Newsletter", "panel", {}),
        ],
    },
    "legal": {
        "label": "Legal document",
        "description": (
            "A blank policy or terms page with dates, a table of contents built from its "
            "headings, and links to the other legal pages."
        ),
        "sections": [
            _s(
                "legal_document",
                "Document",
                "default",
                {
                    "eyebrow": "Legal",
                    "summary": "A short summary of what this document covers.",
                    "body": [
                        {"type": "heading", "level": 2, "text": "1. First section"},
                        {"type": "paragraph", "text": "Write the document here."},
                    ],
                },
            )
        ],
    },
    "privacy_policy": _legal_template("privacy", "privacy-policy"),
    "terms_of_use": _legal_template("terms", "terms"),
    "affiliate_disclosure": _legal_template("affiliate", "affiliate-disclosure"),
    "about": _about_template(),
    "contact": _contact_template(),
    "partner_with_us": _partner_template(),
    "advertise": _advertise_template(),
}
