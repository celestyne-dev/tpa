"""Starter catalogue: editorial placeholders for the first planned titles.

They are published as clearly labelled "coming soon" previews (no prices, no
page counts, no files, nothing purchasable) so the shop and the homepage
showcase keep showing honest previews until the real books are written,
uploaded and priced. Seeding only creates records whose slug does not exist,
so administrator changes are never overwritten.
"""

CATEGORIES = [
    {"slug": "ebooks", "name": "eBooks", "sort_order": 1},
    {"slug": "workbooks", "name": "Workbooks", "sort_order": 2},
    {"slug": "journals", "name": "Journals & planners", "sort_order": 3},
    {"slug": "guides", "name": "Guides & resources", "sort_order": 4},
]

PRODUCTS = [
    {
        "slug": "the-power-of-starting-again",
        "product_type": "ebook",
        "title": "The Power of Starting Again",
        "subtitle": "A guide to rebuilding with hope and intention",
        "short_description": (
            "A compassionate, practical guide for anyone facing a new chapter after loss, change "
            "or disappointment, with reflections and steps to help you rebuild at your own pace."
        ),
        "benefits": [
            "Reflections for processing endings honestly",
            "Practical steps for rebuilding routines and direction",
            "Prompts to reconnect with your values and hopes",
        ],
        "format_label": "eBook",
        "cover_theme": "sage",
        "categories": ["ebooks"],
        "featured_order": 1,
    },
    {
        "slug": "the-30-day-mindset-reset-workbook",
        "product_type": "workbook",
        "title": "The 30-Day Mindset Reset Workbook",
        "subtitle": "Daily prompts for a calmer, more hopeful outlook",
        "short_description": (
            "A guided 30-day workbook with short daily exercises to help you notice unhelpful "
            "thought patterns, practise gratitude and build a more balanced perspective."
        ),
        "benefits": [
            "One focused exercise for each day",
            "Space to journal and track what you notice",
            "Weekly reflections to consolidate progress",
        ],
        "format_label": "Printable workbook",
        "cover_theme": "gold",
        "categories": ["workbooks"],
        "featured_order": 2,
    },
    {
        "slug": "the-daily-reflection-journal",
        "product_type": "journal",
        "title": "The Daily Reflection Journal",
        "subtitle": "A few quiet minutes to check in with yourself",
        "short_description": (
            "A simple, printable journal with gentle morning and evening prompts to help you "
            "notice what matters, celebrate small wins and end each day with perspective."
        ),
        "benefits": [
            "Morning intentions and evening reflections",
            "Gratitude and small-wins pages",
            "Monthly look-back prompts",
        ],
        "format_label": "Printable journal",
        "cover_theme": "olive",
        "categories": ["journals"],
        "featured_order": 3,
    },
    {
        "slug": "the-confidence-and-self-worth-workbook",
        "product_type": "workbook",
        "title": "The Confidence & Self-Worth Workbook",
        "subtitle": "Building confidence from the inside out",
        "short_description": (
            "An encouraging workbook for recognising your value, setting healthy boundaries and "
            "building confidence that does not depend on other people's approval."
        ),
        "benefits": [
            "Exercises for quieting the inner critic",
            "Guidance on boundaries and self-respect",
            "Reflection prompts for everyday confidence",
        ],
        "format_label": "Printable workbook",
        "cover_theme": "charcoal",
        "categories": ["workbooks"],
        "featured_order": 4,
    },
    {
        "slug": "the-letting-go-and-moving-forward-guide",
        "product_type": "reflection_guide",
        "title": "The Letting Go & Moving Forward Guide",
        "subtitle": "Making peace with the past, one step at a time",
        "short_description": (
            "A reflective guide for releasing what you cannot change, processing regret with "
            "kindness and choosing small, steady steps towards what comes next."
        ),
        "benefits": [
            "Reflections for acceptance and forgiveness",
            "Exercises for loosening the grip of regret",
            "Gentle next-step planning",
        ],
        "format_label": "Reflection guide",
        "cover_theme": "blush",
        "categories": ["guides"],
        "featured_order": 5,
    },
]

COLLECTION = {
    "slug": "fresh-start",
    "name": "The Fresh Start Collection",
    "description": (
        "Three companions for a new chapter: a guide to starting again, a 30-day mindset reset "
        "and a daily reflection journal."
    ),
    "products": [
        "the-power-of-starting-again",
        "the-30-day-mindset-reset-workbook",
        "the-daily-reflection-journal",
    ],
}

# The bundle is created as a draft: it is a template for the editors, not a live offer.
BUNDLE = {
    "slug": "the-fresh-start-collection",
    "product_type": "bundle",
    "title": "The Fresh Start Collection",
    "subtitle": "Three resources for a new chapter",
    "short_description": (
        "The Power of Starting Again, The 30-Day Mindset Reset Workbook and The Daily Reflection "
        "Journal together."
    ),
    "format_label": "Bundle",
    "cover_theme": "cream",
    "items": COLLECTION["products"],
}

PLACEHOLDER_NOTE = (
    "This title is in development and is not yet available to purchase. Details may change "
    "as it is finalised."
)
