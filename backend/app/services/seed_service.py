"""Idempotent imports: sample editorial content (development) and CMS defaults.

Existing records (matched by slug / key / storage key) are never modified, so
re-running a seed cannot overwrite real editorial changes.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..cms.blocks import validate_blocks
from ..cms.defaults import DEFAULT_MENUS
from ..extensions import db
from ..models import Article, Author, MediaAsset, NavigationMenu, Page, Tag, Topic
from ..utils.validation import slugify
from .admin.media_admin import validate_metadata
from .navigation_service import _tree_from_defaults

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _media(image: dict[str, Any] | None, counts: dict[str, int]) -> MediaAsset | None:
    if not image:
        return None
    asset = db.session.scalar(select(MediaAsset).where(MediaAsset.storage_key == image["src"]))
    if asset:
        return asset
    filename = image["src"].rsplit("/", 1)[-1]
    mime = "image/svg+xml" if filename.endswith(".svg") else "image/png"
    meta = validate_metadata(
        {
            "filename": filename,
            "mime_type": mime,
            "size_bytes": 0,
            "alt_text": image.get("alt", ""),
            "width": image.get("width"),
            "height": image.get("height"),
            "visibility": "public",
        }
    )
    asset = MediaAsset(storage_key=image["src"], **meta)
    db.session.add(asset)
    counts["media"] += 1
    return asset


def seed_sample_content() -> dict[str, int]:
    counts = {"topics": 0, "authors": 0, "tags": 0, "media": 0, "articles": 0, "skipped": 0}
    topics: dict[str, Topic] = {t.slug: t for t in db.session.scalars(select(Topic))}
    for order, data in enumerate(_load("topics")):
        if data["slug"] in topics:
            counts["skipped"] += 1
            continue
        topic = Topic(
            name=data["name"],
            slug=data["slug"],
            description=data["description"],
            intro=data["intro"],
            icon=data["icon"],
            featured=data["featured"],
            display_order=order,
            status="active",
        )
        db.session.add(topic)
        topics[topic.slug] = topic
        counts["topics"] += 1
    db.session.flush()

    for data in _load("articles"):
        if db.session.scalar(select(Article.id).where(Article.slug == data["slug"])):
            counts["skipped"] += 1
            continue
        author_data = data["author"]
        author = db.session.scalar(select(Author).where(Author.slug == author_data["slug"]))
        if author is None:
            author = Author(
                display_name=author_data["name"], slug=author_data["slug"], status="active"
            )
            db.session.add(author)
            counts["authors"] += 1
        tags = []
        for name in data.get("tags", []):
            slug = slugify(name)
            tag = db.session.scalar(select(Tag).where(Tag.slug == slug))
            if tag is None:
                tag = Tag(name=name, slug=slug)
                db.session.add(tag)
                counts["tags"] += 1
            tags.append(tag)
        published = datetime.fromisoformat(data["published_at"].replace("Z", "+00:00"))
        article = Article(
            title=data["title"],
            slug=data["slug"],
            subtitle=data.get("subtitle"),
            excerpt=data["excerpt"],
            body=validate_blocks(data["body"]),
            author=author,
            primary_topic=topics[data["topic_slug"]],
            secondary_topics=[topics[s] for s in data.get("secondary_topic_slugs", [])],
            tags=tags,
            status=data.get("status", "published"),
            featured=data.get("featured", False),
            published_at=published,
            first_published_at=published,
            featured_image=_media(data.get("image"), counts),
            social_image=_media((data.get("seo") or {}).get("og_image"), counts),
            source=data.get("source", "sample"),
            original_slug=data["slug"],
        )
        db.session.add(article)
        db.session.flush()
        counts["articles"] += 1
    return counts


def seed_cms_defaults() -> dict[str, int]:
    """Create editable copies of the default menus and the homepage section config."""
    from ..models import NavigationItem

    counts = {"menus": 0, "pages": 0, "sections": 0}
    for key, spec in DEFAULT_MENUS.items():
        if not spec["items"]:
            continue  # optional menus (mobile, legal) start empty and use their fallbacks
        if db.session.scalar(select(NavigationMenu.id).where(NavigationMenu.key == key)):
            continue
        menu = NavigationMenu(key=key, name=spec["name"])
        db.session.add(menu)
        db.session.flush()
        for order, node in enumerate(_tree_from_defaults(key)):
            parent = NavigationItem(
                menu_id=menu.id,
                label=node["label"],
                link_type=node["link_type"],
                url=node["url"],
                display_order=order,
            )
            db.session.add(parent)
            db.session.flush()
            for child_order, child in enumerate(node["children"]):
                db.session.add(
                    NavigationItem(
                        menu_id=menu.id,
                        parent_id=parent.id,
                        label=child["label"],
                        link_type=child["link_type"],
                        url=child["url"],
                        display_order=child_order,
                    )
                )
        counts["menus"] += 1

    from .admin.page_admin import ensure_home
    from .page_render import draft_document

    existed = db.session.scalar(select(Page.id).where(Page.slug == "home")) is not None
    page = ensure_home()
    if not existed:
        counts["pages"] += 1
        counts["sections"] += len(page.sections)
    if page.published_snapshot is None:
        # First installation: the default homepage goes live as revision #1.
        from datetime import UTC, datetime

        from ..models import PageRevision

        doc = draft_document(page)
        page.status, page.path, page.published_path = "published", "/", "/"
        page.published_snapshot = doc
        page.published_at = page.first_published_at = datetime.now(UTC)
        db.session.add(
            PageRevision(
                page_id=page.id,
                number=1,
                kind="published",
                snapshot=doc,
                summary="Default homepage",
            )
        )
    db.session.flush()
    return counts
