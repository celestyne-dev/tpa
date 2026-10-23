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
    counts.update(seed_commerce_catalogue())
    return counts


def seed_commerce_catalogue() -> dict[str, int]:
    """Starter categories, coming-soon titles, collection and a draft bundle (only if missing)."""
    import secrets
    from datetime import UTC, datetime

    from ..commerce import starter_catalogue as starter
    from ..models import (
        BundleItem,
        Product,
        ProductCategory,
        ProductCollection,
        ProductCollectionItem,
        ProductRevision,
    )
    from .commerce.catalogue import snapshot_document

    counts = {"product_categories": 0, "products": 0, "product_collections": 0}
    categories = {c.slug: c for c in db.session.scalars(select(ProductCategory))}
    for data in starter.CATEGORIES:
        if data["slug"] not in categories:
            category = ProductCategory(**data)
            db.session.add(category)
            categories[data["slug"]] = category
            counts["product_categories"] += 1
    db.session.flush()
    existing = {p.slug: p for p in db.session.scalars(select(Product))} | {
        p.published_slug: p for p in db.session.scalars(select(Product)) if p.published_slug
    }
    now = datetime.now(UTC)
    for data in starter.PRODUCTS:
        if data["slug"] in existing:
            continue
        product = Product(
            public_id=secrets.token_hex(8),
            slug=data["slug"],
            product_type=data["product_type"],
            title=data["title"],
            subtitle=data["subtitle"],
            short_description=data["short_description"],
            description=validate_blocks(
                [
                    {"type": "paragraph", "text": data["short_description"]},
                    {"type": "paragraph", "text": starter.PLACEHOLDER_NOTE},
                ]
            ),
            benefits=data["benefits"],
            format_label=data["format_label"],
            cover_theme=data["cover_theme"],
            featured_order=data["featured_order"],
            is_featured=True,
            status="published",
            sales_status="coming_soon",
            pricing_model="paid",
        )
        product.categories = [categories[c] for c in data["categories"]]
        db.session.add(product)
        db.session.flush()
        product.published_snapshot = snapshot_document(product)
        product.published_slug = product.slug
        product.published_at = product.first_published_at = now
        db.session.add(
            ProductRevision(
                product_id=product.id,
                number=1,
                kind="system",
                summary="Starter catalogue (coming soon)",
                snapshot=product.published_snapshot,
            )
        )
        existing[product.slug] = product
        counts["products"] += 1
    spec = starter.COLLECTION
    if not db.session.scalar(
        select(ProductCollection.id).where(ProductCollection.slug == spec["slug"])
    ):
        collection = ProductCollection(
            slug=spec["slug"], name=spec["name"], description=spec["description"], is_featured=True
        )
        db.session.add(collection)
        db.session.flush()
        for position, slug in enumerate(spec["products"]):
            if slug in existing:
                db.session.add(
                    ProductCollectionItem(
                        collection_id=collection.id, product_id=existing[slug].id, position=position
                    )
                )
        counts["product_collections"] += 1
    bundle = starter.BUNDLE
    if bundle["slug"] not in existing:
        product = Product(
            public_id=secrets.token_hex(8),
            slug=bundle["slug"],
            product_type="bundle",
            title=bundle["title"],
            subtitle=bundle["subtitle"],
            short_description=bundle["short_description"],
            format_label=bundle["format_label"],
            cover_theme=bundle["cover_theme"],
            status="draft",
            sales_status="coming_soon",
            pricing_model="paid",
        )
        db.session.add(product)
        db.session.flush()
        for position, slug in enumerate(bundle["items"]):
            if slug in existing:
                db.session.add(
                    BundleItem(
                        bundle_id=product.id, product_id=existing[slug].id, position=position
                    )
                )
        counts["products"] += 1
    db.session.flush()
    return counts
