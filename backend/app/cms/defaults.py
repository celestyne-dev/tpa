"""Default navigation and homepage section content (mirrors the Batch 01 site)."""

DEFAULT_MENUS = {
    "primary": {
        "name": "Primary navigation",
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
    "footer": {
        "name": "Footer navigation",
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

HOME_SECTIONS = [
    {
        "key": "hero",
        "section_type": "hero",
        "variant": "default",
        "content": {
            "eyebrow": "Think Positive Always",
            "heading": "A Better Mindset.",
            "highlight": "A Brighter Life.",
            "body": "Practical encouragement, thoughtful resources, and tools to help you grow "
            "through every season of life.",
            "primary_cta_label": "Explore Our Resources",
            "primary_cta_url": "/free-resources",
            "secondary_cta_label": "Read Our Articles",
            "secondary_cta_url": "/articles",
        },
    },
    {
        "key": "welcome",
        "section_type": "brand_intro",
        "variant": "default",
        "content": {
            "eyebrow": "Our mission",
            "heading": "Welcome to Think Positive Always",
            "body": "Think Positive Always exists to help people develop a healthier mindset, "
            "navigate life's challenges, build confidence, and move forward with intention.",
            "cta_label": "More about Think Positive Always",
            "cta_url": "/about",
        },
    },
    {
        "key": "topics",
        "section_type": "topics_grid",
        "variant": "default",
        "content": {
            "eyebrow": "Explore by topic",
            "heading": "Explore What Matters to You",
            "description": "Find encouragement and practical guidance for the part of life you "
            "are working on right now.",
        },
    },
    {
        "key": "featured-articles",
        "section_type": "featured_articles",
        "variant": "lead_and_grid",
        "content": {
            "eyebrow": "From the journal",
            "heading": "Fresh Perspectives for Everyday Life",
            "description": "Thoughtful articles on mindset, confidence, resilience, and "
            "intentional living.",
            "cta_label": "View all articles",
            "cta_url": "/articles",
        },
    },
    {
        "key": "products",
        "section_type": "product_previews",
        "variant": "default",
        "content": {
            "eyebrow": "Coming soon to the shop",
            "heading": "Resources for Your Personal Growth Journey",
            "description": "Thoughtfully created guides and practical tools to help you take "
            "the next step.",
            "footnote": "These titles are in development and not yet available to purchase.",
        },
    },
    {
        "key": "newsletter",
        "section_type": "newsletter_cta",
        "variant": "default",
        "content": {
            "heading": "The Positive Reset",
            "description": "One thoughtful email each week to help you reset your mindset, find "
            "perspective, and keep moving forward.",
        },
    },
    {
        "key": "why-tpa",
        "section_type": "feature_list",
        "variant": "default",
        "content": {
            "eyebrow": "Why Think Positive Always?",
            "heading": "Inspiration That Goes Beyond Words",
            "description": "Inspiration matters most when it helps you live differently.",
            "quote": "Positive thinking is not pretending everything is fine. It is believing "
            "you can still move forward.",
            "items": [
                "Grounded in real life",
                "Practical, not just positive",
                "Made for reflection",
                "Designed for action",
            ],
        },
    },
    {
        "key": "partnerships",
        "section_type": "partnership_cta",
        "variant": "dark",
        "content": {
            "eyebrow": "Partner with us",
            "heading": "Let's Create Something Meaningful Together",
            "body": "We welcome conversations with brands, organisations, and publishers whose "
            "values align with ours.",
            "cta_label": "Explore partnerships",
            "cta_url": "/partner-with-us",
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
        "section_type": "call_to_action",
        "variant": "default",
        "content": {
            "heading": "Your next chapter can start today",
            "body": "Wherever you are on your journey, there is something here to encourage you.",
            "primary_cta_label": "Start reading",
            "primary_cta_url": "/articles",
            "secondary_cta_label": "Explore free resources",
            "secondary_cta_url": "/free-resources",
        },
    },
]
