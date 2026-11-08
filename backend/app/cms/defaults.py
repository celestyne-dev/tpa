"""Default navigation, homepage and article-sidebar sections.

HOME_SECTIONS is the editorial homepage (lead story with two featured stories, latest,
topics, newsletter, most read, resources, good news, a short reflection): editable CMS
sections that read live articles, topics and resources. Nothing is hardcoded content.
"""

DEFAULT_MENUS = {
    "primary": {
        "name": "Header navigation",
        "allows_groups": True,
        "items": [
            {"label": "Articles", "url": "/articles"},
            {
                "label": "Topics",
                "link_type": "heading",
                "children": [
                    {"label": "Positive Mindset", "url": "/topics/positive-mindset"},
                    {"label": "Personal Growth", "url": "/topics/personal-growth"},
                    {
                        "label": "Resilience & Starting Over",
                        "url": "/topics/resilience-starting-over",
                    },
                ],
            },
            {"label": "Resources", "url": "/resources"},
            {"label": "Newsletter", "url": "/newsletter"},
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
                    {"label": "Authors", "url": "/authors"},
                    {"label": "Search", "url": "/search"},
                    {"label": "Positive Mindset", "url": "/topics/positive-mindset"},
                    {"label": "Personal Growth", "url": "/topics/personal-growth"},
                    {
                        "label": "Resilience & Starting Over",
                        "url": "/topics/resilience-starting-over",
                    },
                ],
            },
            {
                "label": "Resources",
                "link_type": "heading",
                "children": [
                    {"label": "Free Resources", "url": "/free-resources"},
                    {"label": "Resource Library", "url": "/resources"},
                    # Left out of the website while "Show the shop/courses" are off.
                    {"label": "Shop", "url": "/shop"},
                    {"label": "Courses", "url": "/courses"},
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
    # Empty by default: staff sign in at /admin/login, which needn't be advertised on every
    # public page. Existing menus are unchanged; a link can still be added here.
    "items": [],
}


def _cta(label: str, url: str, style: str = "") -> dict:
    return {"label": label, "url": url, "style": style, "cta_id": None}


HOME_SECTIONS = [
    {
        "key": "featured",
        "name": "Featured stories",
        "section_type": "featured_articles",
        "variant": "lead_with_two",
        "design": {"background": "ivory", "spacing": "sm", "align": "left"},
        "content": {
            "eyebrow": "",
            "heading": "Featured stories",
            "description": "",
            "mode": "featured",
            "count": 3,
        },
    },
    {
        "key": "latest",
        "name": "Latest articles",
        "section_type": "latest_articles",
        "variant": "grid_3",
        "design": {"background": "ivory", "spacing": "sm", "align": "left"},
        "content": {
            "heading": "Latest articles",
            "count": 6,
            "exclude_shown": True,
            "cta": _cta("View all articles", "/articles", "outline"),
        },
    },
    {
        "key": "topics",
        "name": "Explore by topic",
        "section_type": "topics_grid",
        "variant": "compact_4",
        "design": {"background": "cream", "spacing": "sm", "align": "left"},
        "content": {
            "heading": "Explore by topic",
            "description": "Find encouragement for the part of life you are working on now.",
            "mode": "all",
        },
    },
    {
        "key": "newsletter",
        "name": "Newsletter",
        "section_type": "newsletter_cta",
        "variant": "panel",
        "design": {"background": "ivory", "spacing": "sm", "width": "wide"},
        "content": {
            "eyebrow": "Daily newsletter",
            "heading": "",
            "description": "One thoughtful email each day to help you reset your mindset, find "
            "perspective, and keep moving forward.",
            "show_learn_more": True,
        },
    },
    {
        "key": "most-read",
        "name": "Most read",
        "section_type": "popular_articles",
        "variant": "grid_4",
        "design": {"background": "ivory", "spacing": "sm", "align": "left"},
        "content": {
            "heading": "Most read",
            "period": "30",
            "count": 4,
            "exclude_shown": True,
            # Until the site has reading statistics: featured articles, named as such.
            "fallback": "featured",
            "fallback_heading": "Editor's picks",
        },
    },
    {
        "key": "resources",
        "name": "Resources for your growth",
        "section_type": "resource_showcase",
        "variant": "cards_3",
        "design": {"background": "cream", "spacing": "sm", "align": "left"},
        "content": {
            "heading": "Resources for your growth",
            "description": "Practical tools to help you reflect, plan and take the next step.",
            # Free and premium; premium only while the shop is switched on.
            "mode": "all",
            "count": 3,
            "cta": _cta("Browse all resources", "/resources", "outline"),
        },
    },
    {
        "key": "good-news",
        "name": "Good news & real stories",
        "section_type": "article_collection",
        "variant": "grid_3",
        "design": {"background": "ivory", "spacing": "sm", "align": "left"},
        # Chosen by the editors (hidden until stories are picked): never filled
        # automatically, so nothing is labelled "good news" or "real" without a person
        # deciding it is.
        "content": {
            "eyebrow": "Good news",
            "heading": "Real stories of hope and change",
            "articles": [],
        },
    },
    {
        "key": "reflection",
        "name": "Reflection",
        "section_type": "quote",
        "variant": "minimal",
        "design": {"background": "cream", "spacing": "sm", "align": "center"},
        # Unattributed: a reflection in Think Positive Always' own words, not a quotation.
        "content": {"quote": "Small steps, taken consistently, change everything."},
    },
]

# The article sidebar (Admin › Article sidebar): shown beside every article on wide
# screens and below it on phones. The same CMS sections, rendered compactly; empty ones
# are left out. No advertising by default: a "Sponsored banner" on the sidebar placement
# can be added, and shows only while a booking is live.
SIDEBAR_SECTIONS = [
    {
        "key": "popular",
        "name": "Popular articles",
        "section_type": "popular_articles",
        "variant": "numbered",
        "content": {"heading": "Popular articles", "period": "30", "count": 5},
    },
    {
        "key": "related",
        "name": "Related articles",
        "section_type": "related_articles",
        "variant": "list",
        "content": {"heading": "Related articles", "count": 4, "show_images": True},
    },
    {
        "key": "newsletter",
        "name": "Newsletter",
        "section_type": "newsletter_cta",
        "variant": "compact",
        "content": {
            "eyebrow": "Daily newsletter",
            "heading": "",
            "description": "One thoughtful email each day to help you reset your mindset, find "
            "perspective, and keep moving forward.",
            "show_first_name": False,
            "show_learn_more": True,
        },
    },
    {
        "key": "editors-picks",
        "name": "Editor's Picks",
        "section_type": "featured_articles",
        "variant": "grid_3",
        "content": {"heading": "Editor's Picks", "mode": "featured", "count": 3},
    },
    {
        "key": "topics",
        "name": "Explore topics",
        "section_type": "topics_grid",
        "variant": "cards_3",
        "content": {"heading": "Explore topics", "mode": "all"},
    },
]
