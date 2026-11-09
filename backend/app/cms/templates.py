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


# Company page copy shared by the About, Contact, Partner With Us and Advertise templates.
# It is the wording the built-in pages show (frontend/src/data/companyPages.js); nothing
# here states figures, achievements or biography details.
ABOUT_VALUES = [
    {
        "icon": "heart-handshake",
        "title": "Honest encouragement",
        "text": (
            "We believe in hope that tells the truth. Our content acknowledges real challenges "
            "and meets people where they are."
        ),
    },
    {
        "icon": "lightbulb",
        "title": "Practical wisdom",
        "text": (
            "Inspiration should be useful. We focus on ideas, tools, and small steps that "
            "people can apply in everyday life."
        ),
    },
    {
        "icon": "sprout",
        "title": "Growth at your own pace",
        "text": (
            "Personal growth is not a race. We encourage progress over perfection and "
            "self-compassion over pressure."
        ),
    },
    {
        "icon": "compass",
        "title": "Inclusive by design",
        "text": (
            "Think Positive Always is for adults of every gender, background, and stage of "
            "life who want to grow with intention."
        ),
    },
]
EDITORIAL_APPROACH = [
    {
        "icon": "book-open",
        "title": "Written to encourage and educate",
        "text": "Our articles and resources are designed to encourage and educate.",
    },
    {
        "icon": "shield-check",
        "title": "Not a substitute for professional advice",
        "text": (
            "Our content is not a substitute for professional medical, psychological, or "
            "financial advice. If you are struggling, please reach out to a qualified "
            "professional."
        ),
    },
    {
        "icon": "handshake",
        "title": "Partnerships clearly labelled",
        "text": (
            "When content is sponsored or created in partnership with a brand, it will be "
            "clearly labelled. Sponsorship does not guarantee a positive review, and our "
            "editorial opinions remain our own."
        ),
    },
]
CONTACT_FALLBACK = (
    "We are setting up dedicated contact channels for the new website. They will be published "
    "on this page shortly."
)
CONTACT_CARDS = [
    {
        "icon": "message-circle",
        "title": "General inquiries",
        "text": "For questions, feedback, or support, email us.",
        "email": "general",
        "cta_label": "",
        "cta_url": "",
    },
    {
        "icon": "pen-line",
        "title": "Editorial feedback and corrections",
        "text": (
            "Spotted something that needs correcting, or have feedback on an article? Let us "
            "know, including the article's title or link."
        ),
        "email": "general",
        "cta_label": "",
        "cta_url": "",
    },
    {
        "icon": "handshake",
        "title": "Advertising and partnerships",
        "text": (
            "Interested in collaborating with Think Positive Always? Learn about partnership "
            "formats and how to make an inquiry."
        ),
        "email": "partnerships",
        "cta_label": "Partner with us",
        "cta_url": "/partner-with-us",
    },
]
URGENT_SUPPORT = (
    "Think Positive Always is not a crisis or counselling service. If you are in immediate "
    "danger or need urgent emotional support, please contact your local emergency services or "
    "a licensed mental health professional. In the United States, you can call or text 988 to "
    "reach the 988 Suicide & Crisis Lifeline."
)
PARTNER_INTRO = (
    "We collaborate with brands, organisations, and publishers who share our belief that "
    "encouragement and practical tools can help people live better lives."
)
PARTNER_AUDIENCE = (
    "Think Positive Always speaks to an international, primarily English-speaking audience, "
    "including readers across the United States. Our community is made up of adults of all "
    "genders who are interested in mindset, confidence, resilience, relationships, and "
    "intentional living.\n\n"
    "They come to us for encouragement and practical perspective, which is why we only partner "
    "on messages we believe will be genuinely useful to them."
)
PARTNERSHIP_FORMATS = [
    {
        "icon": "pen-tool",
        "title": "Sponsored content",
        "text": (
            "Thoughtful articles and posts that share your message in a way that genuinely "
            "serves our readers."
        ),
    },
    {
        "icon": "sparkles",
        "title": "Brand storytelling",
        "text": (
            "Collaborative stories that connect your brand's purpose with themes of growth, "
            "resilience, and well-being."
        ),
    },
    {
        "icon": "megaphone",
        "title": "Digital campaigns",
        "text": (
            "Multi-channel campaigns designed around a shared goal, from awareness to community "
            "engagement."
        ),
    },
    {
        "icon": "newspaper",
        "title": "Newsletter sponsorships",
        "text": (
            "Placement in The Positive Reset, our daily email, once the newsletter has launched."
        ),
    },
    {
        "icon": "handshake",
        "title": "Resource partnerships",
        "text": (
            "Co-created guides, challenges, or tools that offer real value to people investing "
            "in their growth."
        ),
    },
]
PARTNER_REASONS = [
    {
        "icon": "users",
        "title": "An audience focused on growth",
        "text": (
            "Adults interested in mindset, confidence, resilience, relationships, and "
            "intentional living."
        ),
    },
    {
        "icon": "heart-handshake",
        "title": "Trust comes first",
        "text": (
            "Readers come to us for encouragement and practical perspective, so we only partner "
            "on messages we believe will be genuinely useful to them."
        ),
    },
    {
        "icon": "shield-check",
        "title": "Transparent by default",
        "text": (
            "Sponsored content is clearly labelled, and paid and affiliate links are marked as "
            "sponsored links for search engines."
        ),
    },
]
BRAND_ALIGNMENT = [
    "Products, services, or causes that support well-being, growth, learning, or positive change.",
    "A commitment to honest claims and respectful, inclusive messaging.",
    "Respect for our audience: no misleading offers, pressure tactics, or harmful products.",
    "Willingness to clearly disclose sponsored and affiliate relationships.",
]
METRICS_NOTE = (
    "Each figure is a measurement taken on the date shown, not a live count. Social media "
    "followers are not website visitors."
)


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
            "The About page as editable sections: introduction, our story (with an optional "
            "founder photo), mission, values, editorial approach, verified community figures "
            "and a closing invitation. Add an Author introduction section for a founder "
            "profile. Publish it at /about to replace the built-in page."
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
                "Introduction",
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
                "image_text",
                "Our story",
                "image_right",
                {
                    "eyebrow": "Our story",
                    "heading": "From daily encouragement to a home for growth",
                    "body": (
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
                "inspirational_message",
                "Our mission",
                "centered",
                {
                    "eyebrow": "Our mission",
                    "message": (
                        "Helping people develop a healthier mindset, navigate life's challenges, "
                        "build confidence, and move forward through encouragement, thoughtful "
                        "content, and useful personal development tools."
                    ),
                },
                {"background": "cream"},
            ),
            _s(
                "feature_list",
                "What we believe",
                "grid_4",
                {
                    "eyebrow": "What we believe",
                    "heading": "For anyone ready to grow",
                    "description": (
                        "Our readers are adults around the world who want to build a healthier "
                        "mindset, strengthen their confidence, recover from setbacks, nurture "
                        "better relationships, and live more intentionally. Some are navigating "
                        "a difficult season. Others simply want to keep growing. All are welcome "
                        "here."
                    ),
                    "items": ABOUT_VALUES,
                },
            ),
            _s(
                "feature_list",
                "Our editorial approach",
                "grid_3",
                {
                    "eyebrow": "Our editorial approach",
                    "heading": "Content you can trust",
                    "items": EDITORIAL_APPROACH,
                },
                {"background": "cream"},
            ),
            _s(
                "audience_metrics",
                "Our community",
                "cards",
                {
                    "eyebrow": "Our community",
                    "heading": "The people we write for",
                    "metric_group": "all",
                    "count": 4,
                },
            ),
            _s(
                "call_to_action",
                "Closing invitation",
                "centered",
                {
                    "heading": "Keep growing with us",
                    "body": (
                        "Explore our articles, or join The Positive Reset for a little "
                        "encouragement every day."
                    ),
                    "primary_cta": _cta("Read our articles", "/articles"),
                    "secondary_cta": _cta("Join The Positive Reset", "/newsletter", "outline"),
                },
                {"background": "beige"},
            ),
        ],
    },
    "contact": {
        "label": "Contact page",
        "description": (
            "The Contact page as editable sections: introduction, contact cards (addresses "
            "from Settings) and the urgent-support notice. Publish it at /contact to replace "
            "the built-in page."
        ),
        "slug": "contact",
        "meta_description": (
            "Find the best way to get in touch with Think Positive Always for general "
            "questions, partnerships, and collaborations."
        ),
        "sections": [
            _s(
                "page_header",
                "Introduction",
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
                "contact_cards",
                "Ways to reach us",
                "cards_3",
                {"items": CONTACT_CARDS, "fallback": CONTACT_FALLBACK},
            ),
            _s(
                "notice_panel",
                "Urgent support",
                "important",
                {"heading": "Need urgent support?", "body": URGENT_SUPPORT},
            ),
        ],
    },
    "partner_with_us": {
        "label": "Partner With Us page",
        "description": (
            "A partnership landing page: hero with an inquiry button that jumps to the form, "
            "audience, collaboration formats, reasons to partner, brand alignment, verified "
            "audience figures, the media kit, the inquiry form and a closing invitation. "
            "Publish it at /partner-with-us to replace the built-in page."
        ),
        "slug": "partner-with-us",
        "meta_description": (
            "Collaborate with Think Positive Always on sponsored content, brand storytelling, "
            "newsletter sponsorships, and purpose-driven campaigns for a personal growth "
            "audience."
        ),
        "sections": [
            _s(
                "hero",
                "Hero",
                "centered",
                {
                    "eyebrow": "Partnerships",
                    "heading": "Partner With Think Positive Always",
                    "body": PARTNER_INTRO,
                    "primary_cta": _cta("Make an inquiry", "/partner-with-us#partnership-inquiry"),
                    "secondary_cta": _cta("See the media kit", "/advertise", "outline"),
                },
                {"background": "cream", "spacing": "md", "align": "center"},
            ),
            _s(
                "image_text",
                "Our audience",
                "image_right",
                {
                    "eyebrow": "Our audience",
                    "heading": "A community that values growth",
                    "body": PARTNER_AUDIENCE,
                },
            ),
            _s(
                "feature_list",
                "Collaboration opportunities",
                "grid_3",
                {
                    "eyebrow": "Campaign formats",
                    "heading": "Ways we can work together",
                    "description": (
                        "Every collaboration is shaped around shared goals. These are some of "
                        "the formats we can explore."
                    ),
                    "items": PARTNERSHIP_FORMATS,
                },
                {"background": "cream"},
            ),
            _s(
                "feature_list",
                "Why partner with us",
                "grid_3",
                {
                    "eyebrow": "Why Think Positive Always",
                    "heading": "Reasons to partner with us",
                    "items": PARTNER_REASONS,
                },
            ),
            _s(
                "image_text",
                "Brand alignment",
                "image_left",
                {
                    "eyebrow": "Brand alignment",
                    "heading": "Partnerships built on shared values",
                    "body": (
                        "Our readers' trust comes first. We look for partners whose work fits "
                        "naturally with what Think Positive Always stands for."
                    ),
                    "bullets": BRAND_ALIGNMENT,
                },
                {"background": "cream"},
            ),
            _s(
                "audience_metrics",
                "Audience figures",
                "cards",
                {
                    "eyebrow": "Audience",
                    "heading": "Measured audience figures",
                    "description": METRICS_NOTE,
                    "metric_group": "all",
                    "count": 4,
                },
            ),
            _s(
                "media_kit_summary",
                "Media kit",
                "panel",
                {
                    "heading": "Media kit",
                    "description": (
                        "An overview of the brand, our content focus, audience information "
                        "and partnership formats."
                    ),
                    "show_metrics": False,
                    "cta": _cta("View the media kit", "/advertise"),
                },
                {"background": "beige"},
            ),
            _s(
                "partnership_inquiry",
                "Inquiry form",
                "panel",
                {
                    "heading": "Tell us about your organisation",
                    "description": (
                        "Introduce your brand or organisation, describe the campaign or "
                        "collaboration you have in mind, and share your goals, preferred "
                        "timeline and any key requirements."
                    ),
                },
            ),
        ],
    },
    "advertise": {
        "label": "Advertise / media kit page",
        "description": (
            "A media kit landing page: hero, the media kit summary, verified social and "
            "website figures, collaboration formats and an inquiry invitation. Figures come "
            "from Partnerships › Audience metrics (verified, dated). Publish it at /advertise "
            "to replace the built-in page."
        ),
        "slug": "advertise",
        "meta_description": (
            "Audience, editorial focus, placements and partnership formats at Think Positive "
            "Always."
        ),
        "sections": [
            _s(
                "hero",
                "Hero",
                "centered",
                {
                    "eyebrow": "Media kit",
                    "heading": "Advertise with Think Positive Always",
                    "body": (
                        "Sponsorships, newsletter partnerships and brand collaborations for a "
                        "personal growth audience."
                    ),
                    "primary_cta": _cta("Start a partnership inquiry", "/partner-with-us"),
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
                    "heading": "Social audience",
                    "description": METRICS_NOTE,
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
                    "heading": "Website audience",
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
                    "eyebrow": "Opportunities",
                    "heading": "Collaboration formats",
                    "items": PARTNERSHIP_FORMATS,
                },
            ),
            _s(
                "call_to_action",
                "Inquiry invitation",
                "centered",
                {
                    "heading": "Let's talk about a partnership",
                    "body": "Tell us about your organisation and what you have in mind.",
                    "primary_cta": _cta("Start a partnership conversation", "/partner-with-us"),
                },
                {"background": "beige"},
            ),
        ],
    },
}
