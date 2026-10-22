"""Page templates: sensible starter sections for new pages (always fully editable)."""

from __future__ import annotations

from typing import Any


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
                {"eyebrow": "The Positive Reset", "intro": "One thoughtful email each week."},
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
                            "answer": "Once a week, when the newsletter launches.",
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
}
