"""Technical SEO: per-article checks, the audit dashboard and sitemap entries.

Checks are practical and non-blocking. Length hints are guidance (search
engines truncate by pixel width, not a fixed character count); nothing here
promises rankings.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from flask import current_app
from sqlalchemy import func, select

from ..cms.blocks import blocks_word_count, heading_outline, internal_links, media_ids
from ..extensions import db
from ..models import Article, MediaAsset, Page, Redirect, Topic
from . import publication_service
from .serializers import iso

# Mirrors frontend/src/config/navigation.js (a test keeps them in sync).
STATIC_PATHS: list[tuple[str, float, str]] = [
    ("/", 1.0, "weekly"),
    ("/articles", 0.9, "daily"),
    ("/shop", 0.8, "weekly"),
    ("/free-resources", 0.8, "monthly"),
    ("/newsletter", 0.7, "monthly"),
    ("/partner-with-us", 0.6, "monthly"),
    ("/about", 0.6, "monthly"),
    ("/contact", 0.5, "yearly"),
    ("/privacy-policy", 0.2, "yearly"),
    ("/terms", 0.2, "yearly"),
    ("/affiliate-disclosure", 0.2, "yearly"),
]


def _site() -> str:
    return current_app.config.get("SITE_URL", "").rstrip("/")


def article_path(slug: str) -> str:
    return f"/articles/{slug}"


def article_url(slug: str) -> str:
    return f"{_site()}{article_path(slug)}"


def _check(code: str, severity: str, message: str, field: str | None = None) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "field": field}


# ---- internal link verification ---------------------------------------------------------


def _known_paths() -> tuple[set[str], set[str], set[str], set[str]]:
    articles = set(db.session.scalars(select(Article.slug).where(Article.status == "published")))
    topics = set(db.session.scalars(select(Topic.slug).where(Topic.status == "active")))
    redirects = set(
        db.session.scalars(select(Redirect.source_path).where(Redirect.is_active.is_(True)))
    )
    pages = set(
        db.session.scalars(
            select(Page.published_path).where(
                Page.status == "published", Page.published_path.is_not(None)
            )
        )
    )
    from ..models import Product, ProductCollection

    shop = {
        f"/shop/{slug}"
        for slug in db.session.scalars(
            select(Product.published_slug).where(
                Product.status == "published", Product.published_slug.is_not(None)
            )
        )
    } | {
        f"/shop/collections/{slug}"
        for slug in db.session.scalars(
            select(ProductCollection.slug).where(ProductCollection.is_active.is_(True))
        )
    }
    commerce_pages = {"/cart", "/account", "/account/library", "/account/orders"}
    return (
        {p for p, _, _ in STATIC_PATHS} | pages | shop | commerce_pages,
        articles,
        topics,
        redirects,
    )


def broken_links(hrefs: list[str], known=None) -> list[str]:
    static, articles, topics, redirects = known or _known_paths()
    broken = []
    for href in hrefs:
        path = href.split("#", 1)[0].split("?", 1)[0]
        path = path.rstrip("/") if len(path) > 1 else path
        if path in static or path in redirects:
            continue
        if path.startswith("/articles/") and path.removeprefix("/articles/") in articles:
            continue
        if path.startswith("/topics/") and path.removeprefix("/topics/") in topics:
            continue
        broken.append(href)
    return broken


# ---- per-article checks -----------------------------------------------------------------


def check_values(article: Article, values: dict[str, Any], known=None) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    title = (values.get("title") or "").strip()
    seo_title = (values.get("seo_title") or "").strip()
    description = (values.get("meta_description") or "").strip()
    excerpt = (values.get("excerpt") or "").strip()
    body = values.get("body") or []
    words = blocks_word_count(body)

    if not title:
        checks.append(_check("missing_title", "error", "The article has no title.", "title"))
    effective_title = seo_title or title
    if not seo_title:
        checks.append(
            _check(
                "missing_seo_title",
                "info",
                "No SEO title set; the article title is used in search results.",
                "seo_title",
            )
        )
    if len(effective_title) > 65:
        checks.append(
            _check(
                "long_title",
                "info",
                f"The search title is {len(effective_title)} characters and may be shortened "
                "in results. Put the important words first.",
                "seo_title",
            )
        )
    if not description:
        checks.append(
            _check(
                "missing_meta_description",
                "warning",
                "No meta description. Search engines may pick a random snippet"
                + (" (the excerpt is used as a fallback)." if excerpt else "."),
                "meta_description",
            )
        )
    elif len(description) > 160:
        checks.append(
            _check(
                "long_meta_description",
                "info",
                f"The meta description is {len(description)} characters; long descriptions "
                "are often truncated.",
                "meta_description",
            )
        )
    elif len(description) < 50:
        checks.append(
            _check(
                "short_meta_description",
                "info",
                "The meta description is very short; describe what readers will learn.",
                "meta_description",
            )
        )
    if not body or words == 0:
        checks.append(_check("empty_content", "error", "The article has no content.", "body"))
    elif words < 250:
        checks.append(
            _check(
                "thin_content",
                "info",
                f"The article has {words} words. Short articles can be fine, but make sure "
                "it fully answers the reader's question.",
                "body",
            )
        )

    # Headings: one H1 (the title), then H2 sections with optional H3 inside them.
    outline = heading_outline(body)
    seen_h2 = False
    for level, text in outline:
        if level == 2:
            seen_h2 = True
        elif level == 3 and not seen_h2:
            checks.append(
                _check(
                    "heading_hierarchy",
                    "warning",
                    f'The subheading "{text[:60]}" (H3) appears before any H2 section heading.',
                    "body",
                )
            )
            break
    if words > 600 and not outline:
        checks.append(
            _check(
                "no_headings",
                "info",
                "Long articles are easier to scan with section headings.",
                "body",
            )
        )

    featured_id = values.get("featured_image_id")
    asset_ids = media_ids(body) | {featured_id, values.get("social_image_id")} - {None}
    assets = (
        {
            a.id: a
            for a in db.session.scalars(select(MediaAsset).where(MediaAsset.id.in_(asset_ids)))
        }
        if asset_ids
        else {}
    )
    featured = assets.get(featured_id)
    if not featured:
        checks.append(
            _check(
                "missing_featured_image",
                "warning",
                "No featured image. It is also used for social sharing previews.",
                "featured_image_id",
            )
        )
    else:
        if not featured.alt_text.strip():
            checks.append(
                _check(
                    "featured_alt_missing",
                    "warning",
                    "The featured image has no alt text. Add it in the media library.",
                    "featured_image_id",
                )
            )
        if not featured.width or not featured.height:
            checks.append(
                _check(
                    "image_dimensions_missing",
                    "warning",
                    "The featured image has no recorded dimensions (layout shift risk).",
                    "featured_image_id",
                )
            )
    for index, block in enumerate(body):
        refs = []
        if block.get("type") == "image":
            refs = [(block.get("media_id"), block.get("alt"))]
        elif block.get("type") == "gallery":
            refs = [(i.get("media_id"), i.get("alt")) for i in block.get("items", [])]
        for media_id, alt in refs:
            asset = assets.get(media_id)
            if asset is None:
                checks.append(
                    _check(
                        "image_missing", "error", f"Block {index + 1} uses a missing image.", "body"
                    )
                )
            elif not (alt or asset.alt_text).strip():
                checks.append(
                    _check(
                        "image_alt_missing",
                        "warning",
                        f"An image in block {index + 1} has no alt text.",
                        "body",
                    )
                )

    for href in broken_links(internal_links(body), known):
        checks.append(
            _check(
                "broken_internal_link",
                "warning",
                f"The link {href} does not point to a published page.",
                "body",
            )
        )

    canonical = (values.get("canonical_url") or "").strip()
    own_url = article_url(values.get("slug") or article.slug)
    if canonical and canonical.rstrip("/") != own_url:
        checks.append(
            _check(
                "external_canonical",
                "info",
                "The canonical URL points elsewhere, so search engines are asked to index that "
                "URL instead. The article is left out of the sitemap.",
                "canonical_url",
            )
        )
        dupes = db.session.scalar(
            select(func.count(Article.id)).where(
                Article.canonical_url == canonical, Article.id != article.id
            )
        )
        if dupes:
            checks.append(
                _check(
                    "duplicate_canonical",
                    "warning",
                    f"{dupes} other article(s) use the same canonical URL.",
                    "canonical_url",
                )
            )
    if values.get("noindex"):
        checks.append(
            _check(
                "noindex",
                "warning",
                "Indexing is disabled: the article will not appear in search results or the "
                "sitemap.",
                "noindex",
            )
        )
    if not values.get("author_id"):
        checks.append(_check("missing_author", "warning", "No author is set.", "author_id"))
    if not values.get("primary_topic_id"):
        checks.append(
            _check("missing_topic", "warning", "No primary topic is set.", "primary_topic_id")
        )
    redirect = db.session.scalar(
        select(Redirect).where(
            Redirect.source_path == article_path(values.get("slug") or article.slug),
            Redirect.is_active.is_(True),
        )
    )
    if redirect:
        checks.append(
            _check(
                "slug_redirected",
                "error",
                f"An active redirect sends this article's URL to {redirect.destination}.",
                "slug",
            )
        )
    return checks


def check_article(article: Article) -> dict[str, Any]:
    from .admin.revisions import working_values

    values = working_values(article)
    checks = check_values(article, values)
    title = (values.get("seo_title") or values.get("title") or "").strip()
    description = (values.get("meta_description") or values.get("excerpt") or "").strip()
    return {
        "checks": checks,
        "counts": {
            s: sum(c["severity"] == s for c in checks) for s in ("error", "warning", "info")
        },
        "preview": {
            "title": title,
            "url": article_url(values.get("slug") or article.slug),
            "description": description,
            "social_title": (values.get("social_title") or title),
            "social_description": (values.get("social_description") or description),
            "indexable": not values.get("noindex")
            and (
                not values.get("canonical_url")
                or values["canonical_url"].rstrip("/")
                == article_url(values.get("slug") or article.slug)
            ),
        },
    }


def slug_status(slug: str, exclude_id: int | None) -> dict[str, Any]:
    from ..utils.validation import SLUG_RE

    if not SLUG_RE.match(slug):
        return {"slug": slug, "valid": False, "available": False}
    taken = db.session.scalar(
        select(Article.id).where(Article.slug == slug, Article.id != (exclude_id or 0))
    )
    redirected = db.session.scalar(
        select(Redirect.destination).where(
            Redirect.source_path == article_path(slug), Redirect.is_active.is_(True)
        )
    )
    return {
        "slug": slug,
        "valid": True,
        "available": taken is None,
        "redirect_destination": redirected,
    }


# ---- CMS pages ---------------------------------------------------------------------------


def check_page_document(doc: dict[str, Any], *, is_home: bool = False) -> list[dict[str, Any]]:
    """Practical, non-blocking SEO checks for a CMS page document."""
    meta = doc.get("page") or {}
    checks: list[dict[str, Any]] = []
    title = meta.get("seo_title") or meta.get("title") or ""
    if not meta.get("seo_title") and not is_home:
        checks.append(
            _check(
                "missing_seo_title", "info", "No SEO title: the page title is used.", "seo_title"
            )
        )
    if len(title) > 60:
        checks.append(
            _check(
                "long_title",
                "info",
                "The title may be shortened in search results (over about 60 characters).",
                "seo_title",
            )
        )
    description = meta.get("meta_description") or ""
    if not description:
        checks.append(
            _check(
                "missing_meta_description",
                "warning",
                "Add a meta description so search results show a helpful summary.",
                "meta_description",
            )
        )
    elif len(description) < 70 or len(description) > 160:
        checks.append(
            _check(
                "description_length",
                "info",
                "Meta descriptions of roughly 70–160 characters display best.",
                "meta_description",
            )
        )
    if meta.get("noindex"):
        checks.append(_check("noindex", "info", "Hidden from search engines (noindex).", "noindex"))
    visible = [s for s in doc.get("sections", []) if s.get("is_visible", True)]
    headings = [s for s in visible if s.get("section_type") in ("hero", "page_header")]
    if not headings and not is_home:
        checks.append(
            _check(
                "missing_h1",
                "warning",
                "Start the page with a page header or hero so it has a main heading.",
                "sections",
            )
        )
    hrefs = []
    for s in visible:
        content = s.get("content") or {}
        for value in content.values():
            if isinstance(value, dict) and value.get("url", "").startswith("/"):
                hrefs.append(value["url"])
    for href in broken_links(hrefs):
        checks.append(
            _check(
                "broken_internal_link",
                "warning",
                f"{href} does not point to a published page.",
                "sections",
            )
        )
    return checks


def page_issues(limit: int = 50) -> list[dict[str, Any]]:
    rows = []
    for page in db.session.scalars(
        select(Page).where(Page.status == "published").order_by(Page.title)
    ):
        checks = check_page_document(page.published_snapshot or {}, is_home=page.slug == "home")
        issues = [c for c in checks if c["severity"] in ("error", "warning")]
        if issues:
            rows.append(
                {"id": page.id, "title": page.title, "path": page.published_path, "issues": issues}
            )
    return rows[:limit]


# ---- dashboard ---------------------------------------------------------------------------


def overview(limit: int = 50) -> dict[str, Any]:
    published = db.session.scalars(
        select(Article).where(Article.status == "published").order_by(Article.title)
    ).all()
    known = _known_paths()
    rows = []
    totals = {
        "missing_seo_title": 0,
        "missing_meta_description": 0,
        "featured_alt_missing": 0,
        "missing_featured_image": 0,
        "noindex": 0,
        "broken_internal_link": 0,
        "external_canonical": 0,
    }
    for article in published:
        from .admin.revisions import content_values

        checks = check_values(article, content_values(article), known)
        codes = {c["code"] for c in checks}
        for code in totals:
            if code in codes:
                totals[code] += 1
        issues = [c for c in checks if c["severity"] in ("error", "warning")]
        if issues:
            rows.append(
                {
                    "id": article.id,
                    "title": article.title,
                    "slug": article.slug,
                    "issues": issues,
                }
            )
    page_rows = page_issues()
    redirect_count = db.session.scalar(select(func.count(Redirect.id))) or 0
    active_redirects = (
        db.session.scalar(select(func.count(Redirect.id)).where(Redirect.is_active.is_(True))) or 0
    )
    entries = sitemap_entries()
    status = publication_service.status()
    return {
        "published_articles": len(published),
        "totals": totals,
        "articles_with_issues": rows[:limit],
        "articles_with_issues_total": len(rows),
        "pages_with_issues": page_rows,
        "redirects": {"total": redirect_count, "active": active_redirects},
        "sitemap": {
            "urls": len(entries),
            "articles": sum(1 for e in entries if e["type"] == "article"),
            "pages": sum(1 for e in entries if e["type"] == "page"),
            "images": sum(len(e.get("images", [])) for e in entries),
            "indexing_enabled_in_build": status.get("indexing_enabled"),
        },
        "build": status,
        "generated_at": iso(datetime.now(UTC)),
    }


# ---- sitemap ---------------------------------------------------------------------------


def _absolute(url: str) -> str:
    return url if urlparse(url).scheme else f"{_site()}{url}"


def _image_entries(article: Article) -> list[dict[str, str]]:
    images = []
    seen = set()
    assets = [article.featured_image] if article.featured_image else []
    ids = media_ids(article.body or [])
    if ids:
        assets += list(db.session.scalars(select(MediaAsset).where(MediaAsset.id.in_(ids))))
    for asset in assets:
        if asset is None or asset.id in seen or not asset.public_url:
            continue
        seen.add(asset.id)
        image = asset.as_image() or {}
        entry = {"loc": _absolute(image.get("src") or asset.public_url)}
        if asset.title or asset.alt_text:
            entry["title"] = asset.title or asset.alt_text
        if asset.caption:
            entry["caption"] = asset.caption
        images.append(entry)
    return images


def _page_images(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    from .admin.media_admin import _deep_media_ids

    ids = set()
    for section in snapshot.get("sections", []):
        if section.get("is_visible", True):
            ids |= _deep_media_ids(section.get("content"))
    images, assets = [], []
    if ids:
        assets = db.session.scalars(
            select(MediaAsset).where(MediaAsset.id.in_(ids), MediaAsset.status == "active")
        ).all()
    for asset in assets:
        if asset.visibility != "public" or not asset.public_url:
            continue
        image = asset.as_image() or {}
        entry = {"loc": _absolute(image.get("src") or asset.public_url)}
        if asset.title or asset.alt_text:
            entry["title"] = asset.title or asset.alt_text
        images.append(entry)
    return images


def sitemap_entries() -> list[dict[str, Any]]:
    """Indexable public URLs only: no drafts, archived, noindex or canonicalised pages."""
    from .settings_service import get_values

    settings = get_values()
    excluded = set((settings.get("seo.sitemap_exclude") or "").splitlines())
    live = {
        p.published_path: p
        for p in db.session.scalars(
            select(Page).where(Page.status == "published", Page.published_path.is_not(None))
        )
    }
    entries: list[dict[str, Any]] = []

    def page_entry(page: Page, path: str, priority: float, changefreq: str) -> dict | None:
        snap = (page.published_snapshot or {}).get("page") or {}
        canonical = (snap.get("canonical_url") or "").rstrip("/")
        if snap.get("noindex") or (canonical and canonical != f"{_site()}{path}".rstrip("/")):
            return None
        return {
            "type": "page",
            "path": path,
            "priority": priority,
            "changefreq": changefreq,
            "lastmod": iso(page.published_at),
            "images": _page_images(page.published_snapshot or {}),
        }

    for path, priority, changefreq in STATIC_PATHS:
        if path in excluded:
            continue
        page = live.pop(path, None)
        if page is not None:
            entry = page_entry(page, path, priority, changefreq)
            if entry:
                entries.append(entry)
            continue
        entries.append(
            {"type": "page", "path": path, "priority": priority, "changefreq": changefreq}
        )
    for path, page in sorted(live.items()):
        if path in excluded:
            continue
        entry = page_entry(page, path, 0.6, "monthly")
        if entry:
            entries.append(entry)
    from .article_service import published_filter

    topics = (
        db.session.scalars(
            select(Topic).where(Topic.status == "active").order_by(Topic.display_order, Topic.name)
        )
        if settings.get("seo.sitemap_include_topics") is not False
        else []
    )
    for topic in topics:
        if f"/topics/{topic.slug}" in excluded:
            continue
        entries.append(
            {
                "type": "topic",
                "path": f"/topics/{topic.slug}",
                "priority": 0.7,
                "changefreq": "weekly",
                "lastmod": iso(topic.updated_at),
            }
        )
    for article in db.session.scalars(
        select(Article).where(published_filter()).order_by(Article.published_at.desc())
    ):
        own = article_url(article.slug)
        if article_path(article.slug) in excluded:
            continue
        if article.noindex or (article.canonical_url and article.canonical_url.rstrip("/") != own):
            continue
        entries.append(
            {
                "type": "article",
                "path": article_path(article.slug),
                "priority": 0.8,
                "changefreq": "monthly",
                "lastmod": iso(max(article.updated_at, article.published_at)),
                "images": _image_entries(article),
            }
        )
    entries.extend(_shop_entries(excluded))
    return entries


def _shop_entries(excluded: set[str]) -> list[dict[str, Any]]:
    """Published, indexable products and active collections that contain them."""
    from ..models import ProductCollection
    from .commerce.catalogue import published_products

    entries = []
    live_ids = set()
    for product in published_products():
        doc = product.published_snapshot or {}
        path = f"/shop/{product.published_slug}"
        live_ids.add(product.id)
        if doc.get("noindex") or path in excluded:
            continue
        images = []
        if doc.get("cover_media_id"):
            asset = db.session.get(MediaAsset, doc["cover_media_id"])
            if asset is not None and asset.visibility == "public" and asset.status != "archived":
                image = asset.as_image() or {}
                entry = {"loc": _absolute(image.get("src") or asset.public_url)}
                if asset.alt_text or asset.title:
                    entry["title"] = asset.title or asset.alt_text
                images.append(entry)
        entries.append(
            {
                "type": "product",
                "path": path,
                "priority": 0.7,
                "changefreq": "weekly",
                "lastmod": iso(product.published_at),
                "images": images,
            }
        )
    for collection in db.session.scalars(
        select(ProductCollection).where(ProductCollection.is_active.is_(True))
    ):
        path = f"/shop/collections/{collection.slug}"
        if path in excluded or not any(i.product_id in live_ids for i in collection.items):
            continue
        entries.append(
            {
                "type": "collection",
                "path": path,
                "priority": 0.6,
                "changefreq": "weekly",
                "lastmod": iso(collection.updated_at),
            }
        )
    return entries
