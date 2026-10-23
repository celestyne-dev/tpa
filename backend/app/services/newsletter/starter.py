"""Starter email templates and automations (inserted only when their key is missing).

Bracketed text is guidance for the author to replace before sending. Nothing here
claims results, quotes readers or states subscriber numbers.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ...extensions import db
from ...models import EmailAutomation, EmailAutomationStep, EmailTemplate


def _p(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "text": text}


def _h(text: str, level: int = 2) -> dict[str, Any]:
    return {"type": "heading", "text": text, "level": level}


def _button(label: str, href: str) -> dict[str, Any]:
    return {"type": "button", "label": label, "href": href, "style": "primary", "align": "left"}


TEMPLATES: list[dict[str, Any]] = [
    {
        "key": "weekly_edition",
        "name": "The Positive Reset — Weekly Edition",
        "description": "The main weekly letter: one idea, one practice, featured reading.",
        "subject": "The Positive Reset: [this week's theme]",
        "preheader": "[One sentence that tells readers what this week's letter offers]",
        "blocks": [
            _p("Hello {{first_name}},"),
            _p("[Open with a short, honest reflection on this week's theme.]"),
            _h("This week's idea"),
            _p("[Explain the main idea in two or three short paragraphs.]"),
            {
                "type": "callout",
                "tone": "tip",
                "title": "Try this",
                "text": "[One small, practical step readers can take this week.]",
            },
            _p("[Close warmly. Featured articles and products you select appear below.]"),
        ],
    },
    {
        "key": "daily_encouragement",
        "name": "Daily Encouragement",
        "description": "A short note of encouragement.",
        "subject": "[A short, encouraging subject]",
        "preheader": "[A gentle line for the inbox preview]",
        "blocks": [
            _p("Good morning, {{first_name}}."),
            {"type": "quote", "text": "[An encouraging thought, written or credited properly.]"},
            _p("[Two or three sentences on how to carry this thought through the day.]"),
        ],
    },
    {
        "key": "weekly_reflection",
        "name": "Weekly Reflection",
        "description": "Reflection prompts for the end of the week.",
        "subject": "Your weekly reflection: [theme]",
        "preheader": "A few quiet questions for the end of your week",
        "blocks": [
            _p("Hello {{first_name}},"),
            _p("[Invite readers to pause for a few minutes.]"),
            {
                "type": "list",
                "ordered": True,
                "items": ["[First reflection question]", "[Second question]", "[Third question]"],
            },
            _p("[A closing thought about being kind to yourself while reflecting.]"),
        ],
    },
    {
        "key": "new_article",
        "name": "New Article Announcement",
        "description": "Introduce a newly published article (select it under Featured articles).",
        "subject": "New on Think Positive Always: [article title]",
        "preheader": "[Why this article is worth reading]",
        "blocks": [
            _p("Hello {{first_name}},"),
            _p("[Two sentences on what the new article covers and who it may help.]"),
        ],
    },
    {
        "key": "free_resource",
        "name": "Free Resource Delivery",
        "description": "Share a free resource with subscribers.",
        "subject": "A free resource for you: [resource name]",
        "preheader": "[What the resource helps with]",
        "blocks": [
            _p("Hello {{first_name}},"),
            _p("[Describe the resource honestly: what it is, its format and how to use it.]"),
            _button("Get the free resource", "/free-resources"),
        ],
    },
    {
        "key": "product_announcement",
        "name": "New Digital Product Announcement",
        "description": "Announce a product (only to subscribers who chose product news).",
        "subject": "Now available: [product name]",
        "preheader": "[What the product is, in one line]",
        "blocks": [
            _p("Hello {{first_name}},"),
            _p("[Describe the product accurately: format, what is included and who it is for.]"),
            _p("[Select the product under Selected products so its real price and link appear.]"),
        ],
    },
    {
        "key": "welcome",
        "name": "Welcome to The Positive Reset",
        "description": "Sent after someone confirms their subscription.",
        "subject": "Welcome to The Positive Reset",
        "preheader": "Thank you for joining. Here's what to expect.",
        "blocks": [
            _p("Hello {{first_name}},"),
            _p(
                "Thank you for confirming your subscription to The Positive Reset. It's a "
                "newsletter about practical encouragement, healthier thinking and personal growth."
            ),
            _h("What to expect"),
            _p("[Describe how often you write and what a typical letter includes.]"),
            _p(
                "You can change what you receive or unsubscribe at any time using the links at "
                "the bottom of every email."
            ),
            _button("Read the latest articles", "/articles"),
        ],
    },
]

AUTOMATIONS: list[dict[str, Any]] = [
    {
        "key": "confirmed_welcome",
        "name": "Confirmed subscription welcome",
        "description": "One welcome email as soon as someone confirms their subscription.",
        "trigger": "subscription_confirmed",
        "steps": [{"template": "welcome", "delay_minutes": 0}],
    },
    {
        "key": "welcome_sequence",
        "name": "New subscriber welcome sequence",
        "description": "A short series over the first week after confirming.",
        "trigger": "subscription_confirmed",
        "steps": [
            {
                "delay_minutes": 2 * 24 * 60,
                "subject": "A small practice to start with",
                "preheader": "[A one-line preview]",
                "blocks": [
                    _p("Hello {{first_name}},"),
                    _p("[Share one simple practice readers can try this week.]"),
                ],
            },
            {
                "delay_minutes": 3 * 24 * 60,
                "subject": "Where to find more",
                "preheader": "Articles and free resources to explore",
                "blocks": [
                    _p("Hello {{first_name}},"),
                    _p("[Point readers to the articles and free resources that suit newcomers.]"),
                    _button("Explore free resources", "/free-resources"),
                ],
            },
        ],
    },
    {
        "key": "lead_magnet_follow_up",
        "name": "Lead magnet follow-up",
        "description": "Follows up two days after a subscriber claims a free resource.",
        "trigger": "lead_magnet_claimed",
        "steps": [
            {
                "delay_minutes": 2 * 24 * 60,
                "subject": "How is the resource working for you?",
                "preheader": "[A friendly check-in]",
                "blocks": [
                    _p("Hello {{first_name}},"),
                    _p("[A short tip for getting the most out of the free resource.]"),
                ],
            }
        ],
    },
    {
        "key": "new_article",
        "name": "New article announcement",
        "description": "Announces each newly published article (weekly-edition subscribers).",
        "trigger": "article_published",
        "required_preference": "weekly",
        "steps": [{"template": "new_article", "delay_minutes": 0}],
    },
    {
        "key": "product_announcement",
        "name": "Product announcement",
        "description": "Announces newly published products, only to subscribers who chose "
        "product news.",
        "trigger": "product_published",
        "required_preference": "products",
        "steps": [{"template": "product_announcement", "delay_minutes": 0}],
    },
    {
        "key": "reengagement",
        "name": "Re-engagement",
        "description": "Asks long-quiet subscribers whether they still want the newsletter. "
        "Exits as soon as they engage.",
        "trigger": "inactive",
        "settings": {"inactive_days": 180},
        "steps": [
            {
                "delay_minutes": 0,
                "subject": "Do you still want The Positive Reset?",
                "preheader": "Choose what you receive, or unsubscribe with one click",
                "blocks": [
                    _p("Hello {{first_name}},"),
                    _p(
                        "We haven't heard from you in a while, and we only want to write to "
                        "people who find these emails useful."
                    ),
                    _p(
                        "If you'd like to keep receiving The Positive Reset, you don't need to do "
                        "anything. You can also choose fewer emails or unsubscribe using the "
                        "links below."
                    ),
                ],
            }
        ],
    },
]


def ensure_templates() -> int:
    existing = set(db.session.scalars(select(EmailTemplate.key)))
    created = 0
    for spec in TEMPLATES:
        if spec["key"] in existing:
            continue
        db.session.add(
            EmailTemplate(
                key=spec["key"],
                name=spec["name"],
                kind="campaign",
                description=spec["description"],
                subject=spec["subject"],
                preheader=spec["preheader"],
                blocks=spec["blocks"],
                is_starter=True,
            )
        )
        created += 1
    db.session.flush()
    return created


def ensure_automations() -> int:
    ensure_templates()
    templates = {t.key: t for t in db.session.scalars(select(EmailTemplate))}
    existing = set(db.session.scalars(select(EmailAutomation.key)))
    created = 0
    for spec in AUTOMATIONS:
        if spec["key"] in existing:
            continue
        automation = EmailAutomation(
            key=spec["key"],
            name=spec["name"],
            description=spec["description"],
            trigger=spec["trigger"],
            status="draft",  # never active until someone reviews and enables it
            required_preference=spec.get("required_preference", ""),
            settings=spec.get("settings", {}),
        )
        for position, step in enumerate(spec["steps"], start=1):
            source = templates.get(step.get("template", "")) if step.get("template") else None
            automation.steps.append(
                EmailAutomationStep(
                    position=position,
                    delay_minutes=step["delay_minutes"],
                    subject=source.subject if source else step["subject"],
                    preheader=source.preheader if source else step.get("preheader", ""),
                    blocks=list(source.blocks) if source else step["blocks"],
                )
            )
        db.session.add(automation)
        created += 1
    db.session.flush()
    return created
