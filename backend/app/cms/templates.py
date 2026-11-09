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
    "about": {
        "label": "About page",
        "description": (
            "The current About page as editable sections: introduction, mission, who we serve "
            "and our values, topics and a closing note. Publish it at /about to replace the "
            "built-in page."
        ),
        "slug": "about",
        "meta_description": (
            "Think Positive Always offers practical inspiration for a stronger mindset, more "
            "confidence, and intentional personal growth. Learn what we stand for and who we "
            "serve."
        ),
        "sections": [
            _s(
                "page_header",
                "Page header",
                "default",
                {
                    "eyebrow": "About us",
                    "heading": "Practical Inspiration for Real Life",
                    "intro": (
                        "Practical inspiration for a stronger mindset, more confidence, and "
                        "intentional personal growth."
                    ),
                },
            ),
            _s(
                "brand_intro",
                "Mission",
                "text_only",
                {
                    "eyebrow": "What we stand for",
                    "heading": "Our mission",
                    "body": (
                        "Helping people develop a healthier mindset, navigate life's challenges, "
                        "build confidence, and move forward through encouragement, thoughtful "
                        "content, and useful personal development tools.\n\n"
                        "Think Positive Always began as a place for daily encouragement and has "
                        "grown into a community of more than 280,000 people who follow Think "
                        "Positive Always on LinkedIn, with audiences on other social platforms as "
                        "well. This website is our new home: a place to go deeper than a single "
                        "post and offer thoughtful articles and practical resources.\n\n"
                        "We believe that thinking positively is not about pretending life is "
                        "easy. It is about choosing a perspective that helps you keep going, and "
                        "pairing that perspective with practical steps that make a real "
                        "difference."
                    ),
                },
            ),
            _s(
                "feature_list",
                "Who we serve and our values",
                "sticky_intro",
                {
                    "eyebrow": "Who we serve",
                    "heading": "For anyone ready to grow",
                    "description": (
                        "Our readers are adults around the world who want to build a healthier "
                        "mindset, strengthen their confidence, recover from setbacks, nurture "
                        "better relationships, and live more intentionally. Some are navigating "
                        "a difficult season. Others simply want to keep growing. All are welcome "
                        "here."
                    ),
                    "items": [
                        {
                            "icon": "heart-handshake",
                            "title": "Honest encouragement",
                            "text": (
                                "We believe in hope that tells the truth. Our content "
                                "acknowledges real challenges and meets people where they are."
                            ),
                        },
                        {
                            "icon": "lightbulb",
                            "title": "Practical wisdom",
                            "text": (
                                "Inspiration should be useful. We focus on ideas, tools, and "
                                "small steps that people can apply in everyday life."
                            ),
                        },
                        {
                            "icon": "sprout",
                            "title": "Growth at your own pace",
                            "text": (
                                "Personal growth is not a race. We encourage progress over "
                                "perfection and self-compassion over pressure."
                            ),
                        },
                        {
                            "icon": "compass",
                            "title": "Inclusive by design",
                            "text": (
                                "Think Positive Always is for adults of every gender, background, "
                                "and stage of life who want to grow with intention."
                            ),
                        },
                    ],
                },
                {"background": "cream"},
            ),
            _s(
                "topics_grid",
                "Topics",
                "cards_4",
                {
                    "eyebrow": "What we write about",
                    "heading": "The topics at the heart of our work",
                    "mode": "featured",
                },
            ),
            _s(
                "call_to_action",
                "A note on our content",
                "centered",
                {
                    "heading": "A note on our content",
                    "body": (
                        "Our articles and resources are designed to encourage and educate. They "
                        "are not a substitute for professional medical, psychological, or "
                        "financial advice. If you are struggling, please reach out to a "
                        "qualified professional."
                    ),
                    "primary_cta": _cta("Read our articles", "/articles"),
                    "secondary_cta": _cta("Get in touch", "/contact", "outline"),
                },
                {"background": "beige"},
            ),
        ],
    },
    "contact": {
        "label": "Contact page",
        "description": (
            "The current Contact page as editable sections: introduction, contact details "
            "from Settings, partnerships and urgent-support information. Publish it at "
            "/contact to replace the built-in page."
        ),
        "slug": "contact",
        "meta_description": (
            "Find the best way to get in touch with Think Positive Always for general "
            "questions, partnerships, and collaborations."
        ),
        "sections": [
            _s(
                "page_header",
                "Page header",
                "default",
                {
                    "eyebrow": "Contact",
                    "heading": "Get in Touch",
                    "intro": (
                        "We would love to hear from you. Here are the best ways to reach Think "
                        "Positive Always."
                    ),
                },
            ),
            _s(
                "contact_details",
                "General inquiries",
                "default",
                {
                    "heading": "General inquiries",
                    "body": "For questions, feedback, or support, email us at:",
                    "show_email": True,
                    "show_partnerships_email": False,
                },
                {"background": "ivory"},
            ),
            _s(
                "call_to_action",
                "Brands & partnerships",
                "centered",
                {
                    "heading": "Brands & partnerships",
                    "body": (
                        "Interested in collaborating with Think Positive Always? Learn about "
                        "partnership formats and how to make an inquiry."
                    ),
                    "primary_cta": _cta("Partner with us", "/partner-with-us"),
                },
                {"background": "cream"},
            ),
            _s(
                "rich_text",
                "Urgent support",
                "narrow",
                {
                    "heading": "Need urgent support?",
                    "body": [
                        {
                            "type": "paragraph",
                            "text": (
                                "Think Positive Always is not a crisis or counselling service. If "
                                "you are in immediate danger or need urgent emotional support, "
                                "please contact your local emergency services or a licensed "
                                "mental health professional. In the United States, you can call "
                                "or text 988 to reach the 988 Suicide & Crisis Lifeline."
                            ),
                        }
                    ],
                },
            ),
        ],
    },
}
