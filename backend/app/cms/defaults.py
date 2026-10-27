"""Default navigation and homepage sections.

HOME_SECTIONS reproduces the hand-built Batch 01 homepage (copy, layout and
colours) as editable CMS sections, so the migrated homepage looks the same.
"""

DEFAULT_MENUS = {
    "primary": {
        "name": "Header navigation",
        "allows_groups": True,
        "items": [
            {"label": "Home", "url": "/"},
            {"label": "Articles", "url": "/articles"},
            {"label": "Shop", "url": "/shop"},
            {"label": "Free Resources", "url": "/free-resources"},
            {"label": "Newsletter", "url": "/newsletter"},
            {"label": "Partner With Us", "url": "/partner-with-us"},
            {"label": "About", "url": "/about"},
        ],
    },
    "mobile": {
        "name": "Mobile navigation",
        "allows_groups": True,
        "help": "Leave empty to use the header navigation on mobile.",
        "items": [],
    },
    "footer": {
        "name": "Footer columns",
        "allows_groups": True,
        "groups_only": True,
        "items": [
            {
                "label": "Explore",
                "link_type": "heading",
                "children": [
                    {"label": "Home", "url": "/"},
                    {"label": "Articles", "url": "/articles"},
                    {"label": "Positive Mindset", "url": "/topics/positive-mindset"},
                    {"label": "Personal Growth", "url": "/topics/personal-growth"},
                    {
                        "label": "Resilience & Starting Over",
                        "url": "/topics/resilience-starting-over",
                    },
                ],
            },
            {
                "label": "Shop & Resources",
                "link_type": "heading",
                "children": [
                    {"label": "Shop", "url": "/shop"},
                    {"label": "Courses", "url": "/courses"},
                    {"label": "Free Resources", "url": "/free-resources"},
                    {"label": "The Positive Reset Newsletter", "url": "/newsletter"},
                ],
            },
            {
                "label": "Company",
                "link_type": "heading",
                "children": [
                    {"label": "About", "url": "/about"},
                    {"label": "Partner With Us", "url": "/partner-with-us"},
                    {"label": "Contact", "url": "/contact"},
                ],
            },
            {
                "label": "Legal",
                "link_type": "heading",
                "children": [
                    {"label": "Privacy Policy", "url": "/privacy-policy"},
                    {"label": "Terms of Use", "url": "/terms"},
                    {"label": "Affiliate Disclosure", "url": "/affiliate-disclosure"},
                ],
            },
        ],
    },
}

DEFAULT_MENUS["legal"] = {
    "name": "Footer legal links",
    "allows_groups": False,
    "help": "Shown in the bottom bar of the footer.",
    # A discreet way in for staff; the public header's Log in button is for customers.
    "items": [{"label": "Staff login", "url": "/admin/login"}],
}


def _cta(label: str, url: str, style: str = "") -> dict:
    return {"label": label, "url": url, "style": style, "cta_id": None}


HOME_SECTIONS = [
    {
        "key": "hero",
        "name": "Hero",
        "section_type": "hero",
        "variant": "split",
        "design": {"background": "ivory", "spacing": "lg", "align": "left"},
        "content": {
            "eyebrow": "Think Positive Always",
            "heading": "A Better Mindset.",
            "highlight": "A Brighter Life.",
            "body": "Practical encouragement, thoughtful resources, and tools to help you grow "
            "through every season of life.",
            "primary_cta": _cta("Explore Our Resources", "/free-resources"),
            "secondary_cta": _cta("Read Our Articles", "/articles", "outline"),
        },
    },
    {
        "key": "welcome",
        "name": "Mission and community",
        "section_type": "brand_intro",
        "variant": "with_stat",
        "design": {"background": "cream", "spacing": "md"},
        "content": {
            "eyebrow": "Our mission",
            "heading": "Welcome to Think Positive Always",
            "body": "Think Positive Always exists to help people develop a healthier mindset, "
            "navigate life's challenges, build confidence, and move forward with intention.\n\n"
            "Here you will find honest encouragement, mindset insights, and personal growth "
            "content written for real life, along with practical resources designed to help you "
            "turn reflection into meaningful action.",
            "cta": _cta("More about Think Positive Always", "/about", "outline"),
            "stat_caption": "people follow Think Positive Always on LinkedIn, part of a growing "
            "international community that shows up for daily encouragement and perspective.",
        },
    },
    {
        "key": "topics",
        "name": "Topics",
        "section_type": "topics_grid",
        "variant": "cards_3",
        "design": {"background": "ivory", "spacing": "md", "align": "left"},
        "content": {
            "eyebrow": "Explore by topic",
            "heading": "Explore What Matters to You",
            "description": "Find encouragement and practical guidance for the part of life you "
            "are working on right now.",
            "mode": "featured",
        },
    },
    {
        "key": "featured-articles",
        "name": "Featured articles",
        "section_type": "featured_articles",
        "variant": "lead_and_grid",
        "design": {"background": "cream", "spacing": "md", "align": "left"},
        "content": {
            "eyebrow": "From the journal",
            "heading": "Fresh Perspectives for Everyday Life",
            "description": "Thoughtful articles on mindset, confidence, resilience, and "
            "intentional living.",
            "mode": "featured",
            "count": 3,
            "cta": _cta("View all articles", "/articles", "outline"),
        },
    },
    {
        "key": "products",
        "name": "Coming soon to the shop",
        "section_type": "product_previews",
        "variant": "grid",
        "design": {"background": "ivory", "spacing": "md", "align": "left"},
        "content": {
            "eyebrow": "Coming soon to the shop",
            "heading": "Resources for Your Personal Growth Journey",
            "description": "Thoughtfully created guides and practical tools to help you take "
            "the next step.",
            "count": 4,
            "footnote": "These titles are in development and not yet available to purchase.",
            "cta": _cta("Visit the shop", "/shop", "outline"),
        },
    },
    {
        "key": "newsletter",
        "name": "Newsletter",
        "section_type": "newsletter_cta",
        "variant": "panel",
        "design": {"background": "ivory", "spacing": "sm", "width": "wide"},
        "content": {
            "eyebrow": "Weekly newsletter",
            "heading": "",
            "description": "One thoughtful email each week to help you reset your mindset, find "
            "perspective, and keep moving forward.",
            "show_learn_more": True,
        },
    },
    {
        "key": "why-tpa",
        "name": "Why Think Positive Always",
        "section_type": "feature_list",
        "variant": "sticky_intro",
        "design": {"background": "beige", "spacing": "md", "card_style": "soft"},
        "content": {
            "eyebrow": "Why Think Positive Always?",
            "heading": "Inspiration That Goes Beyond Words",
            "description": "Inspiration matters most when it helps you live differently. "
            "Everything we create is designed to encourage you and to help you act on that "
            "encouragement.",
            "quote": "Positive thinking is not pretending everything is fine. It is believing "
            "you can still move forward.",
            "items": [
                {
                    "title": "Grounded in real life",
                    "text": "Encouragement that acknowledges real challenges: setbacks, change, "
                    "uncertainty, and the ordinary pressures of everyday life.",
                    "icon": "heart-handshake",
                },
                {
                    "title": "Practical, not just positive",
                    "text": "Clear mindset and personal growth advice you can apply today, without "
                    "empty slogans or unrealistic promises.",
                    "icon": "compass",
                },
                {
                    "title": "Made for reflection",
                    "text": "Content that invites you to pause, ask better questions, and "
                    "understand yourself with more honesty and kindness.",
                    "icon": "notebook-pen",
                },
                {
                    "title": "Designed for action",
                    "text": "Resources built to help you take meaningful next steps, so insight "
                    "becomes progress you can feel.",
                    "icon": "footprints",
                },
            ],
        },
    },
    {
        "key": "partnerships",
        "name": "Partnerships",
        "section_type": "partnership_cta",
        "variant": "dark",
        "design": {"spacing": "lg"},
        "content": {
            "eyebrow": "Partner with us",
            "heading": "Let's Create Something Meaningful Together",
            "body": "We welcome conversations with brands, organisations, and publishers whose "
            "values align with ours. Together we can share thoughtful, useful messages with a "
            "community that cares about personal growth, well-being, and positive change.",
            "cta": _cta("Explore partnerships", "/partner-with-us", "light"),
            "list_heading": "Collaboration opportunities",
            "items": [
                "Sponsored content",
                "Brand storytelling",
                "Digital campaigns",
                "Newsletter sponsorships",
                "Relevant resource partnerships",
            ],
        },
    },
    {
        "key": "final-cta",
        "name": "Closing invitation",
        "section_type": "call_to_action",
        "variant": "centered",
        "design": {"background": "ivory", "spacing": "lg", "width": "narrow"},
        "content": {
            "heading": "Your next chapter can start today",
            "body": "Wherever you are on your journey, there is something here to encourage you. "
            "Read an article, explore a topic that matters to you, and take one small step "
            "forward.",
            "primary_cta": _cta("Start reading", "/articles"),
            "secondary_cta": _cta("Explore free resources", "/free-resources", "outline"),
        },
    },
]
