"""Product catalogue rules shared by the storefront, cart, checkout and admin.

- Prices come from ``product_prices`` (server-side, live); content comes from the
  product's published snapshot, so unpublished edits never reach the public.
- A product is *purchasable* only when every readiness check passes: published,
  marked on sale, inside its availability window, deliverable files present
  (scanned clean when a scanner is configured) or, for bundles, every included
  product deliverable, and an approved price (or free).
- Nothing here converts currencies: a product is simply not available in a
  currency it has no price for.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from ...commerce.currency import CURRENCIES, money
from ...commerce.product_types import PRODUCT_TYPES, type_label
from ...extensions import db
from ...models import (
    Author,
    MediaAsset,
    Product,
    ProductCategory,
    ProductCollection,
    ProductPrice,
)
from ..serializers import _author_profile, iso

MAX_BUNDLE_DEPTH = 3


def now_utc() -> datetime:
    return datetime.now(UTC)


# ---- prices -----------------------------------------------------------------------------


def _in_window(price: ProductPrice, now: datetime) -> bool:
    return (price.starts_at is None or price.starts_at <= now) and (
        price.ends_at is None or price.ends_at > now
    )


def effective_prices(product: Product, now: datetime | None = None) -> dict[str, dict[str, Any]]:
    """{currency: {amount_minor, compare_at_minor, price_id, promotional}} for active prices."""
    now = now or now_utc()
    regular: dict[str, ProductPrice] = {}
    promo: dict[str, ProductPrice] = {}
    for price in product.prices:
        if not price.is_active or price.currency not in CURRENCIES:
            continue
        if price.kind == "regular" and _in_window(price, now):
            regular[price.currency] = price
        elif price.kind == "promotional" and _in_window(price, now):
            promo[price.currency] = price
    out: dict[str, dict[str, Any]] = {}
    for currency, base in regular.items():
        sale = promo.get(currency)
        if sale is not None and sale.amount_minor < base.amount_minor:
            out[currency] = {
                "amount_minor": sale.amount_minor,
                "compare_at_minor": base.amount_minor,
                "price_id": sale.id,
                "promotional": True,
                "ends_at": iso(sale.ends_at),
            }
        else:
            out[currency] = {
                "amount_minor": base.amount_minor,
                "compare_at_minor": base.compare_at_minor,
                "price_id": base.id,
                "promotional": False,
                "ends_at": None,
            }
    return out


def price_boundaries(after: datetime) -> list[datetime]:
    """Future instants where a displayed price or availability changes (for rebuilds)."""
    times: set[datetime] = set()
    for price in db.session.scalars(select(ProductPrice).where(ProductPrice.is_active.is_(True))):
        for value in (price.starts_at, price.ends_at):
            if value and value > after:
                times.add(value)
    for product in db.session.scalars(select(Product).where(Product.status == "published")):
        for value in (product.available_from, product.available_until):
            if value and value > after:
                times.add(value)
    return sorted(times)


# ---- files and bundles ------------------------------------------------------------------


def deliverable_files(product: Product) -> list:
    out = []
    for file in product.files:
        version = file.current_version
        if file.status == "active" and version is not None and version.deliverable:
            out.append(file)
    return out


def bundle_products(
    product: Product, depth: int = 0, seen: set[int] | None = None
) -> list[Product]:
    """Distinct products a bundle grants (nested bundles expanded), in display order."""
    seen = seen if seen is not None else {product.id}
    out: list[Product] = []
    if depth >= MAX_BUNDLE_DEPTH:
        return out
    for item in product.bundle_items:
        child = item.product
        if child is None or child.id in seen:
            continue
        seen.add(child.id)
        out.append(child)
        if child.is_bundle:
            out.extend(bundle_products(child, depth + 1, seen))
    return out


def would_create_cycle(bundle_id: int, candidate_ids: list[int]) -> bool:
    """True if adding candidates to the bundle would make it (indirectly) contain itself."""
    stack = list(candidate_ids)
    visited: set[int] = set()
    while stack:
        current = stack.pop()
        if current == bundle_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        product = db.session.get(Product, current)
        if product is not None:
            stack.extend(i.product_id for i in product.bundle_items)
    return False


def bundle_depth(product: Product, depth: int = 0) -> int:
    if not product.is_bundle or depth > MAX_BUNDLE_DEPTH + 1:
        return depth
    return max(
        [depth + 1]
        + [bundle_depth(i.product, depth + 1) for i in product.bundle_items if i.product]
    )


# ---- readiness --------------------------------------------------------------------------


def readiness(product: Product, now: datetime | None = None) -> dict[str, Any]:
    """Problems that keep a product from being sold, plus the purchasable flag.

    ``issues`` are configuration problems shown in the admin (missing files, prices,
    invalid bundles). ``blockers`` are every reason it is not purchasable right now.
    """
    now = now or now_utc()
    issues: list[str] = []
    blockers: list[str] = []
    ptype = PRODUCT_TYPES.get(product.product_type)
    if ptype is None or not ptype.available:
        issues.append("This product type cannot be sold yet.")
    if product.is_bundle:
        items = bundle_products(product)
        if not product.bundle_items:
            issues.append("The bundle has no products.")
        for child in items:
            if child.is_bundle:
                continue
            if child.status == "archived":
                issues.append(f"Included product “{child.title}” is archived.")
            elif not deliverable_files(child):
                issues.append(f"Included product “{child.title}” has no deliverable files.")
    else:
        files = deliverable_files(product)
        pending = [
            f
            for f in product.files
            if f.status == "active"
            and f.current_version is not None
            and not f.current_version.deliverable
        ]
        if pending:
            issues.append(f"{len(pending)} file(s) are awaiting a malware scan or failed it.")
        if not files:
            issues.append("No deliverable files uploaded.")
    prices = effective_prices(product, now)
    if product.pricing_model == "paid":
        if not prices:
            issues.append("No price set.")
        elif any(p["amount_minor"] <= 0 for p in prices.values()):
            issues.append("Paid products need a price above zero (or switch to free).")
    blockers.extend(issues)
    if product.status != "published":
        blockers.append("Not published.")
    if product.sales_status != "on_sale":
        blockers.append("Marked as coming soon.")
    if product.available_from and product.available_from > now:
        blockers.append(f"Available from {iso(product.available_from)}.")
    if product.available_until and product.available_until <= now:
        blockers.append("The sales window has ended.")
    return {
        "issues": issues,
        "blockers": blockers,
        "purchasable": not blockers,
        "prices": prices,
    }


def purchasable_count() -> int:
    products = db.session.scalars(
        select(Product).where(Product.status == "published", Product.sales_status == "on_sale")
    ).all()
    return sum(1 for p in products if readiness(p)["purchasable"])


# ---- published snapshot -----------------------------------------------------------------


def snapshot_document(product: Product) -> dict[str, Any]:
    """The public content of a product, frozen at publish time."""
    return {
        "version": 1,
        "slug": product.slug,
        "product_type": product.product_type,
        "title": product.title,
        "subtitle": product.subtitle,
        "short_description": product.short_description,
        "description": product.description or [],
        "benefits": product.benefits or [],
        "included": product.included or [],
        "faq": product.faq or [],
        "audience": product.audience,
        "format_label": product.format_label,
        "language": product.language,
        "edition": product.edition,
        "page_count": product.page_count,
        "sample_text": product.sample_text,
        "author_id": product.author_id,
        "cover_media_id": product.cover_media_id,
        "cover_theme": product.cover_theme,
        "gallery": list(product.gallery or []),
        "social_image_id": product.social_image_id,
        "seo_title": product.seo_title,
        "meta_description": product.meta_description,
        "noindex": product.noindex,
        "category_ids": [c.id for c in product.categories],
        "tags": [t.name for t in product.tags],
        "related_ids": [r.id for r in product.related],
    }


def has_unpublished_changes(product: Product) -> bool:
    if product.status != "published" or not product.published_snapshot:
        return False
    return snapshot_document(product) != product.published_snapshot


# ---- public serialisation ---------------------------------------------------------------


class _Media:
    """Batch-loads media and authors for a list of products."""

    def __init__(self, docs: list[dict[str, Any]]):
        ids: set[int] = set()
        authors: set[int] = set()
        for doc in docs:
            for key in ("cover_media_id", "social_image_id"):
                if doc.get(key):
                    ids.add(doc[key])
            ids.update(i for i in doc.get("gallery") or [] if isinstance(i, int))
            if doc.get("author_id"):
                authors.add(doc["author_id"])
        self.media = (
            {m.id: m for m in db.session.scalars(select(MediaAsset).where(MediaAsset.id.in_(ids)))}
            if ids
            else {}
        )
        self.authors = (
            {a.id: a for a in db.session.scalars(select(Author).where(Author.id.in_(authors)))}
            if authors
            else {}
        )

    def image(self, media_id: int | None, preset: str = "responsive") -> dict | None:
        asset = self.media.get(media_id) if media_id else None
        if asset is None or asset.visibility != "public" or asset.status == "archived":
            return None
        return asset.as_image(preset)


def _categories() -> dict[int, ProductCategory]:
    return {c.id: c for c in db.session.scalars(select(ProductCategory))}


def _price_list(prices: dict[str, dict[str, Any]], currencies: list[str]) -> list[dict]:
    out = []
    for currency in currencies:
        price = prices.get(currency)
        if price is None:
            continue
        item = money(price["amount_minor"], currency)
        item["compare_at"] = (
            money(price["compare_at_minor"], currency) if price["compare_at_minor"] else None
        )
        item["promotional"] = price["promotional"]
        item["promotion_ends_at"] = price["ends_at"]
        out.append(item)
    return out


def display_currencies() -> list[str]:
    from ..settings_service import get_values

    raw = get_values().get("shop.display_currencies") or "USD,KES"
    codes = [c.strip().upper() for c in str(raw).split(",") if c.strip()]
    return [c for c in dict.fromkeys(codes) if c in CURRENCIES] or ["USD"]


def effective_download_limit(product: Product) -> int | None:
    """Downloads per buyer: the resource's own limit, else the store-wide setting."""
    if product.download_limit:
        return product.download_limit
    from ...payments.config import get_settings

    return get_settings().get("payments.download_limit")


def access_terms(product: Product) -> dict[str, Any]:
    """What a buyer gets, as shown on the resource page (live, like the price)."""
    return {
        "lifetime": product.access_days is None,
        "days": product.access_days,
        "download_limit": effective_download_limit(product),
    }


def availability_label(product: Product, state: dict[str, Any]) -> str:
    if state["purchasable"]:
        return "free" if product.pricing_model == "free" else "available"
    if product.sales_status == "coming_soon" or (
        product.available_from and product.available_from > now_utc()
    ):
        return "coming-soon"  # Batch 01 public API spelling
    return "unavailable"


def public_product(
    product: Product,
    *,
    detail: bool = False,
    loader: _Media | None = None,
    categories: dict[int, ProductCategory] | None = None,
    collections: dict[int, list[ProductCollection]] | None = None,
    preview: bool = False,
) -> dict[str, Any] | None:
    if preview:  # private admin preview of the current draft
        doc = snapshot_document(product)
    else:
        doc = product.published_snapshot
        if product.status != "published" or not doc:
            return None
    loader = loader or _Media([doc])
    categories = categories if categories is not None else _categories()
    state = readiness(product)
    currencies = display_currencies()
    availability = availability_label(product, state)
    cover = loader.image(doc.get("cover_media_id"))
    files = deliverable_files(product) if not product.is_bundle else []
    formats = sorted({f.current_version.file_format.upper() for f in files if f.current_version})
    data: dict[str, Any] = {
        "id": product.public_id,
        "slug": doc["slug"] if preview else (product.published_slug or doc["slug"]),
        "type": doc["product_type"],
        "type_label": type_label(doc["product_type"]),
        "title": doc["title"],
        "subtitle": doc.get("subtitle") or "",
        "description": doc.get("short_description") or "",
        "format": doc.get("format_label") or type_label(doc["product_type"]),
        "formats": formats,
        "availability": availability,
        "purchasable": state["purchasable"],
        "is_free": product.pricing_model == "free",
        "featured": product.is_featured,
        "cover": cover,
        "cover_theme": doc.get("cover_theme") or "sage",
        "prices": _price_list(state["prices"], currencies)
        if product.pricing_model == "paid" and availability != "coming-soon"
        else [],
        "categories": [
            {"slug": categories[c].slug, "name": categories[c].name}
            for c in doc.get("category_ids") or []
            if c in categories and categories[c].is_active
        ],
        "highlights": (doc.get("benefits") or [])[:3],
        "access": access_terms(product),
        "published_at": iso(product.first_published_at or product.published_at),
        "available_from": iso(product.available_from),
    }
    if product.is_bundle:
        data["bundle_items"] = [
            {"title": child.published_snapshot["title"], "slug": child.published_slug}
            if child.status == "published" and child.published_snapshot
            else {"title": child.title, "slug": None}
            for child in bundle_products(product)
        ]
    if detail:
        author = loader.authors.get(doc.get("author_id")) if doc.get("author_id") else None
        social = loader.image(doc.get("social_image_id"), "social") or loader.image(
            doc.get("cover_media_id"), "social"
        )
        from ..serializers import expand_body

        data.update(
            body=expand_body(doc.get("description") or []),
            benefits=doc.get("benefits") or [],
            included=doc.get("included") or [],
            faq=doc.get("faq") or [],
            audience=doc.get("audience") or "",
            language=doc.get("language") or "en",
            edition=doc.get("edition") or "",
            page_count=doc.get("page_count"),
            sample_text=doc.get("sample_text") or "",
            gallery=[img for i in doc.get("gallery") or [] if (img := loader.image(i))],
            author=_author_profile(author) if author and author.status == "active" else None,
            tags=doc.get("tags") or [],
            files=[
                {
                    "title": f.title,
                    "description": f.description,
                    "format": f.current_version.file_format.upper(),
                    "size_bytes": f.current_version.size_bytes,
                }
                for f in files
            ],
            collections=[
                {"slug": c.slug, "name": c.name}
                for c in (collections or {}).get(product.id, [])
                if c.is_active
            ],
            seo={
                k: v
                for k, v in {
                    "title": doc.get("seo_title"),
                    "description": doc.get("meta_description"),
                    "no_index": doc.get("noindex") or None,
                    "og_image": social,
                }.items()
                if v
            }
            or None,
            updated_at=iso(product.published_at),
        )
    return data


def _collections_by_product() -> dict[int, list[ProductCollection]]:
    out: dict[int, list[ProductCollection]] = {}
    for collection in db.session.scalars(select(ProductCollection)):
        for item in collection.items:
            out.setdefault(item.product_id, []).append(collection)
    return out


def published_products() -> list[Product]:
    return list(
        db.session.scalars(
            select(Product)
            .where(Product.status == "published", Product.published_snapshot.is_not(None))
            .order_by(Product.featured_order, Product.id)
        )
    )


def list_public(args: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    args = args or {}
    products = published_products()
    docs = [p.published_snapshot for p in products]
    loader = _Media(docs)
    cats = _categories()
    collections = _collections_by_product()
    items = []
    for product in products:
        data = public_product(product, loader=loader, categories=cats, collections=collections)
        if data is None:
            continue
        data["collections"] = [c.slug for c in collections.get(product.id, []) if c.is_active]
        data["_order"] = product.featured_order
        items.append(data)
    if args.get("category"):
        items = [i for i in items if args["category"] in {c["slug"] for c in i["categories"]}]
    if args.get("collection"):
        items = [i for i in items if args["collection"] in i["collections"]]
    if args.get("type"):
        items = [i for i in items if i["type"] == args["type"]]
    if args.get("group") == "resources":  # written resources: everything but bundles
        items = [i for i in items if i["type"] != "bundle"]
    if args.get("access") == "free":
        items = [i for i in items if i["is_free"]]
    elif args.get("access") == "premium":
        items = [i for i in items if not i["is_free"]]
    if args.get("featured"):
        items = [i for i in items if i["featured"]]
    if args.get("q"):
        q = args["q"].lower()
        items = [
            i
            for i in items
            if q in f"{i['title']} {i['subtitle']} {i['description']} {i['type_label']}".lower()
        ]
    sort = args.get("sort") or "featured"
    if sort == "newest":
        items.sort(key=lambda i: i["published_at"] or "", reverse=True)
    elif sort == "title":
        items.sort(key=lambda i: i["title"].lower())
    elif sort in ("price_asc", "price_desc"):
        currency = args.get("currency") or display_currencies()[0]

        def price_key(item):
            match = next((p for p in item["prices"] if p["currency"] == currency), None)
            if item["is_free"]:
                return 0
            return match["amount_minor"] if match else None

        priced = [i for i in items if price_key(i) is not None]
        unpriced = [i for i in items if price_key(i) is None]
        priced.sort(key=price_key, reverse=sort == "price_desc")
        items = priced + unpriced
    else:
        items.sort(key=lambda i: (not i["featured"], i["_order"]))
    for item in items:
        item.pop("_order", None)
    return items


def public_types(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resource types present in a listing, for filters (no empty options)."""
    counts: dict[str, int] = {}
    for item in items:
        counts[item["type"]] = counts.get(item["type"], 0) + 1
    return [
        {"key": key, "label": type_label(key), "count": count}
        for key, count in sorted(counts.items(), key=lambda kv: type_label(kv[0]))
    ]


def get_public(slug: str) -> dict[str, Any] | None:
    product = db.session.scalar(select(Product).where(Product.published_slug == slug))
    if product is None:
        return None
    data = public_product(product, detail=True, collections=_collections_by_product())
    if data is None:
        return None
    # Related resources chosen by editors (published order) come first; the rest are
    # filled from the same collections, then featured products.
    chosen = list((product.published_snapshot or {}).get("related_ids") or [])
    related_ids = set()
    collections = _collections_by_product().get(product.id, [])
    for collection in collections:
        related_ids.update(i.product_id for i in collection.items)
    related_ids.discard(product.id)
    candidates = [p for p in published_products() if p.id != product.id]
    rank = {pid: i for i, pid in enumerate(chosen)}
    candidates.sort(
        key=lambda p: (
            rank.get(p.id, len(rank)),
            p.id not in related_ids,
            p.featured_order,
            p.id,
        )
    )
    limit = max(3, min(len(chosen), 6))
    loader = _Media([p.published_snapshot for p in candidates[:limit]])
    data["related"] = [
        r for p in candidates[:limit] if (r := public_product(p, loader=loader)) is not None
    ]
    return data


def public_collections() -> list[dict[str, Any]]:
    collections = db.session.scalars(
        select(ProductCollection)
        .where(ProductCollection.is_active.is_(True))
        .order_by(ProductCollection.sort_order, ProductCollection.name)
    ).all()
    loader = _Media([{"cover_media_id": c.cover_media_id} for c in collections])
    out = []
    for c in collections:
        ids = [i.product_id for i in c.items]
        count = (
            len(
                [
                    p
                    for p in db.session.scalars(select(Product).where(Product.id.in_(ids)))
                    if p.status == "published" and p.published_snapshot
                ]
            )
            if ids
            else 0
        )
        out.append(
            {
                "slug": c.slug,
                "name": c.name,
                "description": c.description,
                "featured": c.is_featured,
                "product_count": count,
                "cover": loader.image(c.cover_media_id),
                "seo": {
                    k: v
                    for k, v in {"title": c.seo_title, "description": c.meta_description}.items()
                    if v
                }
                or None,
            }
        )
    return out


def get_collection(slug: str) -> dict[str, Any] | None:
    collection = db.session.scalar(
        select(ProductCollection).where(
            ProductCollection.slug == slug, ProductCollection.is_active.is_(True)
        )
    )
    if collection is None:
        return None
    meta = next(c for c in public_collections() if c["slug"] == slug)
    order = {i.product_id: i.position for i in collection.items}
    products = [p for p in published_products() if p.id in order]
    products.sort(key=lambda p: order[p.id])
    loader = _Media([p.published_snapshot for p in products])
    cats = _categories()
    meta["products"] = [
        d for p in products if (d := public_product(p, loader=loader, categories=cats))
    ]
    return meta


def public_categories() -> list[dict[str, Any]]:
    used: dict[int, int] = {}
    for product in published_products():
        for cid in (product.published_snapshot or {}).get("category_ids") or []:
            used[cid] = used.get(cid, 0) + 1
    return [
        {"slug": c.slug, "name": c.name, "description": c.description, "product_count": used[c.id]}
        for c in sorted(_categories().values(), key=lambda c: (c.sort_order, c.name))
        if c.is_active and used.get(c.id)
    ]


def products_for_section(content: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """Products for the homepage "Digital product showcase" section."""
    mode = content.get("mode") or "featured"
    products = published_products()
    by_id = {p.id: p for p in products}
    if mode == "manual":
        chosen = [by_id[i] for i in content.get("products") or [] if i in by_id]
    elif mode == "collection":
        slug_ids = content.get("collection") or []
        collection = db.session.get(ProductCollection, slug_ids[0]) if slug_ids else None
        if collection is None or not collection.is_active:
            chosen = []
        else:
            chosen = [by_id[i.product_id] for i in collection.items if i.product_id in by_id]
    elif mode == "bundles":
        chosen = [p for p in products if p.is_bundle]
    elif mode == "latest":
        chosen = sorted(
            products,
            key=lambda p: p.first_published_at or p.published_at or now_utc(),
            reverse=True,
        )
    else:  # featured: featured first, then the rest in catalogue order
        chosen = sorted(products, key=lambda p: (not p.is_featured, p.featured_order, p.id))
    chosen = chosen[:limit]
    loader = _Media([p.published_snapshot for p in chosen])
    cats = _categories()
    return [d for p in chosen if (d := public_product(p, loader=loader, categories=cats))]
