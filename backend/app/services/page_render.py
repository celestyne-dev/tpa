"""Page documents and their public, resolved form.

A *document* is the complete, validated configuration of a page:
``{"version": 1, "page": {...meta}, "sections": [...]}``. The draft document
is built from the editable rows; Publish stores a copy as
``Page.published_snapshot``. The public API only ever resolves published
snapshots (or the built-in homepage defaults on a fresh installation).

Resolving turns stored references into a small public payload: responsive
images, article cards, topic cards, global calls to action and shared
sections. Hidden sections and sections outside their visibility window are
left out, so the public payload never contains drafts or internal names.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from ..cms.defaults import HOME_SECTIONS
from ..cms.design import visible_at
from ..cms.sections import SECTION_TYPES, check_section
from ..extensions import db
from ..models import (
    Article,
    Author,
    GlobalCta,
    MediaAsset,
    Page,
    PageSection,
    ReusableSection,
    Topic,
)
from .serializers import _author_profile, expand_body, iso, public_article, public_topic

DOC_VERSION = 1
META_FIELDS = (
    "title",
    "slug",
    "path",
    "template",
    "parent_id",
    "seo_title",
    "meta_description",
    "noindex",
    "canonical_url",
    "social_title",
    "social_description",
    "social_image_id",
)
SECTION_FIELDS = (
    "key",
    "name",
    "section_type",
    "variant",
    "content",
    "design",
    "visibility",
    "is_visible",
    "reusable_section_id",
)
MAX_GROUP_DEPTH = 3


def _now() -> datetime:
    return datetime.now(UTC)


# ---- documents ---------------------------------------------------------------------------


def section_doc(section: PageSection) -> dict[str, Any]:
    return {
        "key": section.key,
        "name": section.name or "",
        "section_type": section.section_type,
        "variant": section.variant,
        "content": section.content or {},
        "design": section.design or {},
        "visibility": section.visibility or {},
        "is_visible": section.is_visible,
        "reusable_section_id": section.reusable_section_id,
    }


def meta_doc(page: Page) -> dict[str, Any]:
    return {f: getattr(page, f) for f in META_FIELDS}


def draft_document(page: Page) -> dict[str, Any]:
    return {
        "version": DOC_VERSION,
        "page": meta_doc(page),
        "sections": [section_doc(s) for s in page.sections],
    }


def doc_hash(doc: dict[str, Any] | None) -> str | None:
    if doc is None:
        return None
    data = json.dumps(doc, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(data.encode()).hexdigest()


def has_unpublished_changes(page: Page) -> bool:
    if page.status != "published" or not page.published_snapshot:
        return page.status != "archived"
    return doc_hash(draft_document(page)) != doc_hash(page.published_snapshot)


def default_home_document() -> dict[str, Any]:
    """The built-in homepage (used until a homepage has been published)."""
    sections = []
    for spec in HOME_SECTIONS:
        clean, _, _ = check_section(
            spec["section_type"], spec["variant"], spec["content"], spec.get("design")
        )
        sections.append(
            {
                "key": spec["key"],
                "name": spec.get("name", ""),
                "section_type": spec["section_type"],
                **clean,
                "is_visible": True,
                "reusable_section_id": None,
            }
        )
    return {
        "version": DOC_VERSION,
        "page": {
            "title": "Homepage",
            "slug": "home",
            "path": "/",
            "template": "home",
            "parent_id": None,
            "seo_title": None,
            "meta_description": None,
            "noindex": False,
            "canonical_url": None,
            "social_title": None,
            "social_description": None,
            "social_image_id": None,
        },
        "sections": sections,
    }


# ---- resolution ---------------------------------------------------------------------------


class _Loader:
    """Batch-loads every record a set of sections refers to."""

    def __init__(self) -> None:
        self.media: dict[int, MediaAsset] = {}
        self.articles: dict[int, Article] = {}
        self.topics: dict[int, Topic] = {}
        self.authors: dict[int, Author] = {}
        self.ctas: dict[int, GlobalCta] = {}
        self.reusables: dict[int, ReusableSection] = {}
        self._topic_counts: dict[int, int] | None = None
        self._settings: dict[str, Any] | None = None
        self.latest_dependency: datetime | None = None

    def touch_products(self, products: list[dict[str, Any]]) -> None:
        for product in products:
            if product.get("published_at"):
                self.touch(datetime.fromisoformat(product["published_at"].replace("Z", "+00:00")))

    def touch(self, value: datetime | None) -> None:
        if value and (self.latest_dependency is None or value > self.latest_dependency):
            self.latest_dependency = value

    def collect(self, sections: list[dict[str, Any]]) -> None:
        ids: dict[str, set[int]] = {
            k: set() for k in ("media", "article", "topic", "author", "cta")
        }
        reusable_ids: set[int] = set()

        def scan(section_type: str, content: dict[str, Any]) -> None:
            _, _, refs = check_section(section_type, None, content)
            for kind, value, _path in refs.items:
                if kind == "reusable":
                    reusable_ids.add(value)
                elif kind in ids:
                    ids[kind].add(value)

        pending = list(sections)
        depth = 0
        while pending and depth <= MAX_GROUP_DEPTH:
            for s in pending:
                if s.get("reusable_section_id"):
                    reusable_ids.add(s["reusable_section_id"])
                elif s.get("section_type") in SECTION_TYPES:
                    scan(s["section_type"], s.get("content") or {})
            new = reusable_ids - set(self.reusables)
            if not new:
                break
            loaded = db.session.scalars(
                select(ReusableSection).where(ReusableSection.id.in_(new))
            ).all()
            for r in loaded:
                self.reusables[r.id] = r
            pending = [{"section_type": r.section_type, "content": r.content or {}} for r in loaded]
            depth += 1

        def load(model, key):
            if ids[key]:
                return {
                    o.id: o for o in db.session.scalars(select(model).where(model.id.in_(ids[key])))
                }
            return {}

        self.media = load(MediaAsset, "media")
        self.articles = load(Article, "article")
        self.topics = load(Topic, "topic")
        self.authors = load(Author, "author")
        self.ctas = load(GlobalCta, "cta")

    @property
    def topic_counts(self) -> dict[int, int]:
        if self._topic_counts is None:
            from .article_service import published_topic_counts

            self._topic_counts = published_topic_counts()
        return self._topic_counts

    @property
    def settings(self) -> dict[str, Any]:
        if self._settings is None:
            from .settings_service import get_values

            self._settings = get_values()
        return self._settings


def _image(loader: _Loader, asset_id: int | None, preset: str = "responsive") -> dict | None:
    asset = loader.media.get(asset_id) if asset_id else None
    if asset is None or asset.visibility != "public" or asset.status == "archived":
        return None
    return asset.as_image(preset)


def _cta(loader: _Loader, value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return None
    style = value.get("style") or None
    if value.get("cta_id"):
        cta = loader.ctas.get(value["cta_id"])
        if cta is None:
            return None
        loader.touch(cta.updated_at)
        label, url, style = cta.label, cta.url, style or cta.style
    else:
        label, url = value.get("label"), value.get("url")
    if not label or not url:
        return None
    return {"label": label, "href": url, "external": url.startswith("https://"), "style": style}


def _published(article: Article | None, now: datetime) -> bool:
    return bool(
        article
        and article.status == "published"
        and article.published_at
        and article.published_at <= now
    )


def _resolve_field(loader: _Loader, spec: dict[str, Any], value: Any, now: datetime) -> Any:
    kind = spec["type"]
    if kind == "media":
        return _image(loader, value)
    if kind == "cta":
        return _cta(loader, value)
    if kind == "rich":
        return expand_body(value or [])
    if kind == "articles":
        return [
            public_article(loader.articles[i], include_body=False)
            for i in value or []
            if _published(loader.articles.get(i), now)
        ]
    if kind == "topics":
        return [
            public_topic(loader.topics[i], loader.topic_counts.get(i, 0))
            for i in value or []
            if i in loader.topics and loader.topics[i].status == "active"
        ]
    if kind in ("products", "product_collection"):
        return value or []  # resolved by the section's computed data
    if kind == "author":
        author = loader.authors.get(value) if value else None
        return _author_profile(author) if author and author.status == "active" else None
    if kind == "items":
        return [
            {
                sub: _resolve_field(loader, s, item.get(sub), now)
                for sub, s in spec["fields"].items()
            }
            for item in value or []
        ]
    return value


def _featured_articles(limit: int) -> list[dict[str, Any]]:
    from .article_service import list_articles

    return list_articles(featured=True, page=1, page_size=limit)[0]


def _latest_articles(limit: int, topic_slug: str | None) -> list[dict[str, Any]]:
    from .article_service import list_articles

    return list_articles(topic=topic_slug, page=1, page_size=limit)[0]


def _computed(
    loader: _Loader, section_type: str, content: dict[str, Any], data: dict[str, Any], page: dict
) -> None:
    """Type-specific data the frontend needs (collections, settings-driven values)."""
    settings = loader.settings
    if section_type == "featured_articles":
        if content.get("mode") == "manual":
            data["articles"] = data.get("articles") or []
        else:
            data["articles"] = _featured_articles(content.get("count") or 3)
    elif section_type == "latest_articles":
        topic = (data.get("topic") or [None])[0]
        data["topic"] = topic
        data["articles"] = _latest_articles(content.get("count") or 6, topic and topic["slug"])
    elif section_type == "topics_grid":
        from .topic_service import list_topics

        mode = content.get("mode")
        if mode == "featured":
            data["topics"] = list_topics(featured=True)
        elif mode == "all":
            data["topics"] = list_topics()
    elif section_type == "product_previews":
        from .commerce.catalogue import products_for_section

        data["products"] = products_for_section(content, content.get("count") or 3)
        loader.touch_products(data["products"])
        if not content.get("show_prices", True):
            for product in data["products"]:
                product["prices"] = []
    elif section_type == "brand_intro":
        data["stat_value"] = settings.get("community.linkedin_followers_label") or None
    elif section_type == "newsletter_cta":
        data["newsletter_name"] = "The Positive Reset"
        data["is_open"] = bool(settings.get("newsletter.is_open"))
    elif section_type == "contact_details":
        contact = settings.get("contact.email") or None
        data["email"] = contact if content.get("show_email") else None
        partnerships = settings.get("contact.partnerships_email") or contact
        data["partnerships_email"] = (
            partnerships if content.get("show_partnerships_email") else None
        )
    elif section_type == "page_header":
        data["heading"] = data.get("heading") or page.get("title")


def _resolve_section(
    loader: _Loader,
    section: dict[str, Any],
    page: dict[str, Any],
    now: datetime,
    *,
    preview: bool,
    depth: int = 0,
    seen: frozenset[int] = frozenset(),
) -> list[dict[str, Any]]:
    if not section.get("is_visible", True):
        return []
    in_window = visible_at(section.get("visibility"), now)
    if not in_window and not preview:
        return []
    section_type, variant = section["section_type"], section.get("variant")
    content, design = section.get("content") or {}, section.get("design") or {}
    shared_id = section.get("reusable_section_id")
    if shared_id:
        shared = loader.reusables.get(shared_id)
        if shared is None or shared_id in seen:
            return []
        loader.touch(shared.updated_at)
        section_type, variant = shared.section_type, shared.variant
        content, design = shared.content or {}, shared.design or {}
        seen = seen | {shared_id}
    definition = SECTION_TYPES.get(section_type)
    if definition is None:
        return []
    if section_type == "section_group":
        if depth >= MAX_GROUP_DEPTH:
            return []
        out = []
        for index, child_id in enumerate(content.get("items") or []):
            child = {
                "key": f"{section['key']}-{index}",
                "section_type": "",
                "reusable_section_id": child_id,
                "visibility": section.get("visibility"),
            }
            out += _resolve_section(
                loader, child, page, now, preview=preview, depth=depth + 1, seen=seen
            )
        return out
    data = {
        name: _resolve_field(loader, spec, content.get(name), now)
        for name, spec in definition["fields"].items()
    }
    _computed(loader, section_type, content, data, page)
    resolved = {
        "key": section["key"],
        "type": section_type,
        "variant": variant
        if variant in definition["variants"]
        else definition["defaults"]["variant"],
        "design": design,
        "devices": (section.get("visibility") or {}).get("devices") or "all",
        "data": data,
    }
    if shared_id:
        resolved["shared"] = True
    if preview and not in_window:
        resolved["preview_note"] = "Outside its visibility dates: not shown on the live site now."
    return [resolved]


def _breadcrumbs(page_meta: dict[str, Any]) -> list[dict[str, str]]:
    if page_meta.get("path") in (None, "/"):
        return []
    trail = []
    parent_id, guard = page_meta.get("parent_id"), 0
    while parent_id and guard < 5:
        parent = db.session.get(Page, parent_id)
        if parent is None:
            break
        snap = (
            (parent.published_snapshot or {}).get("page") if parent.status == "published" else None
        )
        if snap:
            trail.append({"name": snap["title"], "path": parent.published_path})
        parent_id, guard = parent.parent_id, guard + 1
    return [
        {"name": "Home", "path": "/"},
        *reversed(trail),
        {"name": page_meta["title"], "path": page_meta["path"]},
    ]


def resolve_document(
    doc: dict[str, Any],
    *,
    now: datetime | None = None,
    preview: bool = False,
    published_at: datetime | None = None,
) -> dict[str, Any]:
    now = now or _now()
    meta = doc["page"]
    loader = _Loader()
    loader.collect(doc.get("sections", []))
    sections: list[dict[str, Any]] = []
    for section in doc.get("sections", []):
        sections += _resolve_section(loader, section, meta, now, preview=preview)
    social = None
    if meta.get("social_image_id"):
        loader.media.update(
            {
                a.id: a
                for a in db.session.scalars(
                    select(MediaAsset).where(MediaAsset.id == meta["social_image_id"])
                )
            }
        )
        social = _image(loader, meta["social_image_id"], "social")
    modified = max(filter(None, [published_at, loader.latest_dependency]), default=None)
    return {
        "path": meta.get("path") or "/",
        "title": meta["title"],
        "template": meta.get("template"),
        "seo": {
            "title": meta.get("seo_title") or None,
            "description": meta.get("meta_description") or None,
            "canonical_url": meta.get("canonical_url") or None,
            "noindex": bool(meta.get("noindex")),
            "og_image": social,
            "og_title": meta.get("social_title") or None,
            "og_description": meta.get("social_description") or None,
        },
        "breadcrumbs": _breadcrumbs(meta),
        "published_at": iso(published_at),
        "updated_at": iso(modified),
        "sections": sections,
    }


# ---- public queries ---------------------------------------------------------------------------


def _live(path: str) -> Page | None:
    return db.session.scalar(
        select(Page).where(Page.published_path == path, Page.status == "published")
    )


def public_page(path: str) -> dict[str, Any] | None:
    page = _live(path)
    if page is not None and page.published_snapshot:
        return resolve_document(page.published_snapshot, published_at=page.published_at)
    if path == "/":
        home = db.session.scalar(select(Page).where(Page.slug == "home"))
        if home is None or not home.published_snapshot:
            return resolve_document(default_home_document())
    return None


def published_pages() -> list[dict[str, Any]]:
    """Every live CMS page (the prerenderer renders each one)."""
    pages = db.session.scalars(
        select(Page)
        .where(Page.status == "published", Page.published_path.is_not(None))
        .order_by(Page.published_path)
    )
    out = []
    for page in pages:
        snap = (page.published_snapshot or {}).get("page") or {}
        out.append(
            {
                "path": page.published_path,
                "title": snap.get("title", page.title),
                "noindex": bool(snap.get("noindex")),
                "canonical_url": snap.get("canonical_url"),
                "updated_at": iso(page.published_at),
            }
        )
    return out


def visibility_boundaries() -> list[datetime]:
    """Start/end times of section visibility windows on live pages (for rebuild timing)."""
    from ..cms.design import boundaries

    out: list[datetime] = []
    for snapshot in db.session.scalars(
        select(Page.published_snapshot).where(Page.status == "published")
    ):
        for section in (snapshot or {}).get("sections", []):
            out += boundaries(section.get("visibility"))
    return out
