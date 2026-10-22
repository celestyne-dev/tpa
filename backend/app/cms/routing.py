"""Public URL rules for CMS pages.

Precedence (highest first):
1. Reserved system routes (admin, API, media, articles, topics, the shop, sign-in
   and build files) can never be CMS pages.
2. A *published* CMS page whose path matches one of the built-in pages below
   replaces that built-in page (e.g. publish an "about" page to manage /about in
   the CMS). Until then the built-in page is served.
3. Any other published CMS page path.
4. Everything else is a real 404 (redirects from the redirect manager are tried
   first by the web server).
"""

from __future__ import annotations

from ..utils.validation import SLUG_RE

# First path segments that belong to the application or its infrastructure.
RESERVED_SEGMENTS = frozenset(
    {
        "admin",
        "api",
        "articles",
        "topics",
        "shop",
        "media",
        "assets",
        "images",
        "og",
        "static",
        "_redirect",
        "login",
        "logout",
        "signin",
        "sign-in",
        "signup",
        "register",
        "account",
        "accounts",
        "auth",
        "oauth",
        "checkout",
        "cart",
        "orders",
        "preview",
        "search",
        "feed",
        "rss",
        "sitemap",
        "sitemap.xml",
        "robots.txt",
        "manifest.webmanifest",
        "favicon.ico",
        "icon.svg",
        "404",
        "404.html",
        "index.html",
        "redirects.json",
        "prerender-manifest.json",
        "well-known",
        ".well-known",
        "home",
    }
)

# Built-in, code-rendered pages that a published CMS page may take over.
OVERRIDABLE_PATHS = frozenset(
    {
        "/about",
        "/contact",
        "/newsletter",
        "/partner-with-us",
        "/free-resources",
        "/privacy-policy",
        "/terms",
        "/affiliate-disclosure",
    }
)

MAX_DEPTH = 3


def page_path(slugs: list[str]) -> str:
    return "/" + "/".join(slugs)


def slug_problem(slug: str, *, top_level: bool) -> str | None:
    if not slug or len(slug) > 120 or not SLUG_RE.match(slug):
        return "Use lowercase letters, numbers and hyphens (for example: spring-reset)."
    if top_level and slug in RESERVED_SEGMENTS:
        return f"“/{slug}” is reserved by the website and cannot be used for a page."
    return None
