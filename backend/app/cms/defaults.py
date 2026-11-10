"""Default navigation, homepage and article-sidebar sections.

HOME_SECTIONS is the content-first homepage (Batch 14): a compact introduction, featured
stories, topics, trending (real reading statistics, or editor's picks), the newsletter,
latest articles, free resources, digital products, articles by topic and a community
section. All are editable CMS sections that read live articles, topics and products.
"""

# The recommended, content-first navigation (Batch 14). Nothing here is a topic: each
# group lists the site's own active topics whose names match its keywords
# (topic_links.grouped_topic_links), so it follows whatever topics the editors create and
# rename. Saved menus are never changed; Admin › Navigation offers this structure as
# "Use the recommended structure", which loads it into the editor for review.
TOPIC_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    (
        "Mindset",
        (
            "mindset",
            "positive",
            "positivity",
            "confidence",
            "self worth",
            "affirmation",
            "affirmations",
            "motivation",
            "inspiration",
            "personal growth",
            "gratitude",
            "optimism",
        ),
    ),
    (
        "Wellbeing",
        (
            "wellbeing",
            "well being",
            "mental",
            "resilience",
            "hard days",
            "self care",
            "emotional",
            "balance",
            "mindfulness",
            "calm",
            "starting over",
            "healing",
        ),
    ),
    (
        "Relationships",
        (
            "relationships",
            "relationship",
            "connection",
            "boundaries",
            "communication",
            "love",
            "friendship",
            "family",
        ),
    ),
    (
        "Career & Growth",
        (
            "career",
            "purpose",
            "work",
            "workplace",
            "productivity",
            "routines",
            "habits",
            "personal development",
            "leadership",
            "goals",
            "intentional living",
        ),
    ),
]
TOPICS_PER_GROUP = 6

# A group with "topic_group": label lists the matching topics, then "All articles" (and is
# left out when no topic matches); "group_links": True lists a link to each topic group on
# /topics. These are only starting points: Admin › Navigation saves editable copies.
DEFAULT_MENUS = {
    "primary": {
        "name": "Header navigation",
        "allows_groups": True,
        "items": [
            # Each topic group ends with an "All articles" link, so the archive is one
            # click away from every menu.
            *[
                {"label": label, "link_type": "heading", "topic_group": label, "children": []}
                for label, _keywords in TOPIC_GROUPS
            ],
            {
                "label": "Resources",
                "link_type": "heading",
                "children": [
                    {"label": "All Resources", "url": "/resources"},
                    {"label": "Free Downloads", "url": "/free-resources"},
                    # Left out while "Show the shop" is off (Settings › Website sections).
                    {"label": "Premium Resources", "url": "/shop"},
                    # Shown once the Recommended Books & Tools page is published.
                    {"label": "Recommended Books & Tools", "url": "/recommended"},
                    {"label": "My Library", "url": "/account/library"},
                ],
            },
            # On wide screens the header's Newsletter button stands in for this link.
            {"label": "Newsletter", "url": "/newsletter"},
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
                "children": [{"label": "Articles", "url": "/articles"}],
                "group_links": True,
            },
            {
                "label": "Resources",
                "link_type": "heading",
                "children": [
                    {"label": "Resource Library", "url": "/resources"},
                    {"label": "Free Resources", "url": "/free-resources"},
                    {"label": "Premium Resources", "url": "/shop"},
                    {"label": "Recommended Books & Tools", "url": "/recommended"},
                ],
            },
            {
                "label": "About",
                "link_type": "heading",
                "children": [
                    {"label": "Our Story", "url": "/about"},
                    {"label": "Partner With Us", "url": "/partner-with-us"},
                    {"label": "Contact", "url": "/contact"},
                    {"label": "Newsletter", "url": "/newsletter"},
                ],
            },
            {
                "label": "Legal",
                "link_type": "heading",
                "children": [
                    {"label": "Privacy Policy", "url": "/privacy-policy"},
                    {"label": "Terms of Use", "url": "/terms"},
                    {"label": "Cookie Policy", "url": "/cookie-policy"},
                    {"label": "Affiliate Disclosure", "url": "/affiliate-disclosure"},
                    # Policy pages: each link shows only once its page is published in the
                    # CMS (navigation_service.public_navigation).
                    {"label": "Editorial Policy", "url": "/editorial-policy"},
                    {"label": "Disclaimer", "url": "/disclaimer"},
                    {"label": "Advertising Policy", "url": "/advertising-policy"},
                    {"label": "Refund Policy", "url": "/refund-policy"},
                    {"label": "Accessibility", "url": "/accessibility"},
                    {"label": "Community Guidelines", "url": "/community-guidelines"},
                    {"label": "Copyright Policy", "url": "/copyright-policy"},
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
        # A compact brand introduction: the headline and two ways in, so readers reach the
        # stories quickly (small spacing and a smaller heading keep it short).
        "key": "intro",
        "name": "Introduction",
        "section_type": "hero",
        "variant": "centered",
        "design": {
            "background": "ivory",
            "spacing": "sm",
            "align": "center",
            "heading_size": "small",
        },
        "content": {
            "eyebrow": "Think Positive Always",
            "heading": "A Better Mindset. A Brighter Life.",
            "body": "Practical, encouraging reading on mindset, wellbeing, relationships and "
            "growth, for real life.",
            "primary_cta": _cta("Start reading", "/articles"),
            "secondary_cta": _cta("Explore topics", "/topics", "outline"),
        },
    },
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
        "key": "topics",
        "name": "Explore by topic",
        "section_type": "topics_grid",
        "variant": "compact_4",
        "design": {"background": "cream", "spacing": "sm", "align": "left"},
        "content": {
            "heading": "Explore by topic",
            "description": "Find encouragement for the part of life you are working on now.",
            # Featured topics with published articles (empty topics are left out).
            "mode": "featured",
            "cta": _cta("All topics", "/topics", "outline"),
        },
    },
    {
        "key": "most-read",
        "name": "Trending articles",
        "section_type": "popular_articles",
        "variant": "grid_4",
        "design": {"background": "ivory", "spacing": "sm", "align": "left"},
        "content": {
            # From the site's own reading statistics only; never invented.
            "heading": "Trending this month",
            "period": "30",
            "count": 4,
            # Real popularity may include a story shown above; the fallback never does.
            "exclude_shown": False,
            # Until the site has reading statistics: featured articles, named as such
            # (never presented as trending).
            "fallback": "featured",
            "fallback_heading": "Editor's picks",
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
        "key": "resources",
        "name": "Free resources",
        "section_type": "resource_showcase",
        "variant": "cards_3",
        "design": {"background": "cream", "spacing": "sm", "align": "left"},
        "content": {
            "heading": "Free resources",
            "description": "Worksheets, guides and planners you can download and use today.",
            "mode": "free",
            "count": 3,
            "cta": _cta("All free resources", "/free-resources", "outline"),
        },
    },
    {
        # Shown only while the shop is switched on and products are published.
        "key": "products",
        "name": "Featured digital products",
        "section_type": "product_previews",
        "variant": "grid",
        "design": {"background": "ivory", "spacing": "sm", "align": "left"},
        "content": {
            "heading": "Digital products",
            "description": "Workbooks, journals and planners to go deeper.",
            "mode": "featured",
            "count": 3,
            "show_prices": True,
            "cta": _cta("Browse premium resources", "/shop", "outline"),
        },
    },
    {
        # The latest articles from the featured topics, one row per topic with a link to
        # the topic page; topics without articles are left out.
        "key": "by-topic",
        "name": "Articles by topic",
        "section_type": "topic_articles",
        "variant": "rows",
        "design": {"background": "ivory", "spacing": "sm"},
        "content": {
            "heading": "More to read by topic",
            "mode": "featured",
            "topic_count": 4,
            "per_topic": 3,
            "exclude_shown": True,
        },
    },
    {
        # The community figure comes only from Settings (verified); without it the
        # section shows the text alone.
        "key": "community",
        "name": "Community and about",
        "section_type": "brand_intro",
        "variant": "with_stat",
        "design": {"background": "cream", "spacing": "sm"},
        "content": {
            "eyebrow": "Our community",
            "heading": "Encouragement for real life",
            "body": "Think Positive Always is an independent publication sharing practical, "
            "hopeful ideas for thinking clearly, caring for yourself and growing at your own "
            "pace.",
            "cta": _cta("Our story", "/about", "outline"),
            "stat_caption": "people follow Think Positive Always on LinkedIn.",
        },
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
