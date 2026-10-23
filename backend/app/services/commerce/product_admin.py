"""Product CMS: drafts, publishing, prices, bundles, categories, collections and history.

Permissions are enforced per action here (not only in the API layer):
- products.edit            content, media, categories, collections, SEO (draft)
- products.publish         publish/unpublish, on-sale status, availability window
- products.archive         archive/restore
- products.manage_prices   prices and the free/paid model
- products.manage_bundles  bundle contents
Every change that affects the public site queues a rebuild through the existing
publishing pipeline (``record_public_change``).
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...cms.blocks import validate_blocks
from ...commerce.currency import CURRENCIES, MAX_AMOUNT_MINOR, money
from ...commerce.product_types import COVER_THEMES, PRODUCT_TYPES, TAX_CATEGORIES, available_types
from ...extensions import db
from ...models import (
    Author,
    BundleItem,
    Entitlement,
    OrderItem,
    Product,
    ProductCategory,
    ProductCollection,
    ProductCollectionItem,
    ProductPrice,
    ProductRevision,
    Tag,
    User,
)
from ...utils.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from ...utils.validation import SLUG_RE, plain_text_problem, slugify
from .. import audit_service
from ..publication_service import record_public_change
from ..serializers import iso
from . import catalogue

# Slugs that would collide with storefront routes under /shop/.
RESERVED_PRODUCT_SLUGS = frozenset({"collections", "categories", "category", "cart", "search"})
_LANG = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
DRAFT_COALESCE = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.now(UTC)


def _require(actor: User, *perms: P) -> None:
    granted = effective_permissions(actor)
    if not all(p.value in granted for p in perms):
        raise ForbiddenError()


def can(actor: User) -> dict[str, bool]:
    granted = effective_permissions(actor)
    return {
        key: perm.value in granted
        for key, perm in {
            "create": P.PRODUCTS_CREATE,
            "edit": P.PRODUCTS_EDIT,
            "publish": P.PRODUCTS_PUBLISH,
            "archive": P.PRODUCTS_ARCHIVE,
            "prices": P.PRODUCTS_MANAGE_PRICES,
            "files": P.PRODUCTS_MANAGE_FILES,
            "bundles": P.PRODUCTS_MANAGE_BUNDLES,
        }.items()
    }


def get_product(product_id: int) -> Product:
    product = db.session.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product not found.")
    return product


# ---- serialisation ----------------------------------------------------------------------


def price_dict(price: ProductPrice) -> dict[str, Any]:
    return {
        "id": price.id,
        "currency": price.currency,
        "kind": price.kind,
        "amount_minor": price.amount_minor,
        "amount": money(price.amount_minor, price.currency)["amount"],
        "formatted": money(price.amount_minor, price.currency)["formatted"],
        "compare_at_minor": price.compare_at_minor,
        "starts_at": iso(price.starts_at),
        "ends_at": iso(price.ends_at),
        "is_active": price.is_active,
        "approved_at": iso(price.approved_at),
        "updated_at": iso(price.updated_at),
    }


def summary(product: Product) -> dict[str, Any]:
    state = catalogue.readiness(product)
    return {
        "id": product.id,
        "public_id": product.public_id,
        "title": product.title,
        "slug": product.slug,
        "published_slug": product.published_slug,
        "product_type": product.product_type,
        "status": product.status,
        "sales_status": product.sales_status,
        "pricing_model": product.pricing_model,
        "is_featured": product.is_featured,
        "featured_order": product.featured_order,
        "cover_media_id": product.cover_media_id,
        "cover_theme": product.cover_theme,
        "prices": [
            money(v["amount_minor"], c) | {"promotional": v["promotional"]}
            for c, v in sorted(state["prices"].items())
        ],
        "issues": state["issues"],
        "purchasable": state["purchasable"],
        "blockers": state["blockers"],
        "file_count": len([f for f in product.files if f.status == "active"]),
        "has_unpublished_changes": catalogue.has_unpublished_changes(product),
        "available_from": iso(product.available_from),
        "updated_at": iso(product.updated_at),
        "published_at": iso(product.published_at),
    }


def detail(product: Product, actor: User) -> dict[str, Any]:
    from .product_files import file_dict

    data = summary(product)
    data.update(
        lock_version=product.lock_version,
        subtitle=product.subtitle,
        short_description=product.short_description,
        description=product.description or [],
        benefits=product.benefits or [],
        included=product.included or [],
        faq=product.faq or [],
        audience=product.audience,
        format_label=product.format_label,
        language=product.language,
        edition=product.edition,
        page_count=product.page_count,
        sample_text=product.sample_text,
        author_id=product.author_id,
        gallery=list(product.gallery or []),
        social_image_id=product.social_image_id,
        seo_title=product.seo_title,
        meta_description=product.meta_description,
        noindex=product.noindex,
        tax_category=product.tax_category,
        category_ids=[c.id for c in product.categories],
        tag_ids=[t.id for t in product.tags],
        collection_ids=[
            i.collection_id
            for i in db.session.scalars(
                select(ProductCollectionItem).where(ProductCollectionItem.product_id == product.id)
            )
        ],
        available_until=iso(product.available_until),
        first_published_at=iso(product.first_published_at),
        archived_at=iso(product.archived_at),
        price_records=[
            price_dict(p) for p in sorted(product.prices, key=lambda p: (p.currency, p.kind))
        ],
        files=[file_dict(f) for f in product.files],
        bundle_items=[
            {
                "product_id": i.product_id,
                "title": i.product.title,
                "status": i.product.status,
                "product_type": i.product.product_type,
            }
            for i in product.bundle_items
        ],
        public_path=f"/shop/{product.published_slug}" if product.published_slug else None,
        sales=sales_summary(product),
        can=can(actor),
    )
    return data


def sales_summary(product: Product) -> dict[str, Any]:
    from ...models import Order

    rows = db.session.execute(
        select(Order.currency, Order.mode, func.count(OrderItem.id))
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            OrderItem.product_id == product.id,
            Order.status.in_(("paid", "partially_refunded", "refunded")),
        )
        .group_by(Order.currency, Order.mode)
    ).all()
    entitled = db.session.scalar(
        select(func.count(Entitlement.id)).where(
            Entitlement.product_id == product.id, Entitlement.status == "active"
        )
    )
    return {
        "orders": [{"currency": c, "mode": m, "count": n} for c, m, n in rows],
        "active_entitlements": entitled or 0,
    }


def list_products(args: dict[str, Any]) -> list[dict[str, Any]]:
    stmt = select(Product).order_by(Product.updated_at.desc())
    if args.get("status"):
        stmt = stmt.where(Product.status == args["status"])
    else:
        stmt = stmt.where(Product.status != "archived")
    if args.get("type"):
        stmt = stmt.where(Product.product_type == args["type"])
    if args.get("q"):
        like = f"%{args['q'].lower()}%"
        stmt = stmt.where(func.lower(Product.title).like(like) | Product.slug.like(like))
    items = [summary(p) for p in db.session.scalars(stmt)]
    if args.get("issues"):
        items = [i for i in items if i["issues"]]
    return items


def options() -> dict[str, Any]:
    from ..settings_service import get_values

    return {
        "types": [
            {
                "value": t.key,
                "label": t.label,
                "delivery": t.delivery,
                "available": t.available,
                "default_format": t.default_format,
                "description": t.description,
            }
            for t in PRODUCT_TYPES.values()
        ],
        "currencies": [
            {"code": c.code, "name": c.name, "exponent": c.exponent} for c in CURRENCIES.values()
        ],
        "display_currencies": catalogue.display_currencies(),
        "cover_themes": list(COVER_THEMES),
        "tax_categories": [{"value": k, "label": v} for k, v in TAX_CATEGORIES.items()],
        "tax_note": "Prices are charged exactly as shown. Tax is not calculated automatically "
        "in this release; consult your accountant before enabling taxable sales.",
        "categories": [category_dict(c) for c in _all_categories()],
        "collections": [
            {"id": c.id, "name": c.name, "slug": c.slug}
            for c in db.session.scalars(select(ProductCollection).order_by(ProductCollection.name))
        ],
        "authors": [
            {"id": a.id, "name": a.display_name}
            for a in db.session.scalars(
                select(Author).where(Author.status == "active").order_by(Author.display_name)
            )
        ],
        "tags": [
            {"id": t.id, "name": t.name} for t in db.session.scalars(select(Tag).order_by(Tag.name))
        ],
        "products": [
            {"id": p.id, "title": p.title, "product_type": p.product_type, "status": p.status}
            for p in db.session.scalars(
                select(Product).where(Product.status != "archived").order_by(Product.title)
            )
        ],
        "shop_settings": {k: v for k, v in get_values().items() if k.startswith("shop.")},
    }


# ---- validation -------------------------------------------------------------------------


def _text(value, name, max_len, errors, *, required=False, multiline=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        errors[name] = ["Must be text."]
        return ""
    value = value.replace("\r\n", "\n").strip()
    if not multiline:
        value = " ".join(value.split())
    if required and not value:
        errors[name] = ["This field is required."]
    elif len(value) > max_len:
        errors[name] = [f"Must be at most {max_len} characters."]
    elif value and (problem := plain_text_problem(value)):
        errors[name] = [problem]
    return value


def _string_list(value, name, max_items, max_len, errors):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        errors[name] = ["Must be a list of text items."]
        return []
    items = [" ".join(v.split()) for v in value if v.strip()]
    if len(items) > max_items:
        errors[name] = [f"At most {max_items} items."]
    for item in items:
        if len(item) > max_len:
            errors[name] = [f"Items must be at most {max_len} characters."]
        elif problem := plain_text_problem(item):
            errors[name] = [problem]
    return items


def _object_list(value, name, spec: dict[str, tuple[int, bool]], max_items, errors):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        errors[name] = ["Must be a list of items."]
        return []
    if len(value) > max_items:
        errors[name] = [f"At most {max_items} items."]
    out = []
    for index, item in enumerate(value):
        unknown = set(item) - set(spec)
        if unknown:
            errors[f"{name}.{index}"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]
            continue
        clean = {}
        for field, (max_len, required) in spec.items():
            clean[field] = _text(
                item.get(field),
                f"{name}.{index}.{field}",
                max_len,
                errors,
                required=required,
                multiline=max_len > 300,
            )
        out.append(clean)
    return out


def _id_or_none(value, name, errors):
    if value in (None, ""):
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        errors[name] = ["Choose an item from the list."]
        return None
    return value


def _validate_slug(slug: str, product: Product | None, errors: dict) -> str:
    slug = (slug or "").strip().lower()
    if not slug or not SLUG_RE.match(slug) or len(slug) > 200:
        errors["slug"] = ["Use lowercase letters, numbers and hyphens."]
    elif slug in RESERVED_PRODUCT_SLUGS:
        errors["slug"] = ["This address is reserved by the shop."]
    else:
        clash = db.session.scalar(
            select(Product.id).where(
                (Product.slug == slug) | (Product.published_slug == slug),
                Product.id != (product.id if product else 0),
            )
        )
        if clash:
            errors["slug"] = ["Another product already uses this address."]
    return slug


def unique_slug(base: str) -> str:
    base = slugify(base)[:180] or "product"
    if base in RESERVED_PRODUCT_SLUGS:
        base = f"{base}-product"
    slug, n = base, 2
    while db.session.scalar(
        select(Product.id).where((Product.slug == slug) | (Product.published_slug == slug))
    ):
        slug, n = f"{base}-{n}", n + 1
    return slug


CONTENT_FIELDS = {
    "title",
    "slug",
    "subtitle",
    "short_description",
    "description",
    "benefits",
    "included",
    "faq",
    "audience",
    "format_label",
    "language",
    "edition",
    "page_count",
    "sample_text",
    "author_id",
    "cover_media_id",
    "cover_theme",
    "gallery",
    "social_image_id",
    "seo_title",
    "meta_description",
    "noindex",
    "tax_category",
    "category_ids",
    "tag_ids",
    "collection_ids",
    "is_featured",
    "featured_order",
}
PUBLISH_FIELDS = {"sales_status", "available_from", "available_until"}
PRICE_FIELDS = {"pricing_model"}
ALL_FIELDS = CONTENT_FIELDS | PUBLISH_FIELDS | PRICE_FIELDS | {"lock_version"}


def _parse_dt(value, name, errors):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        errors[name] = ["Use an ISO 8601 date and time."]
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors[name] = ["Use an ISO 8601 date and time."]
        return None
    if parsed.tzinfo is None:
        errors[name] = ["Include a time zone (e.g. 2026-11-01T09:00:00Z)."]
        return None
    return parsed.astimezone(UTC)


def _clean(data: dict[str, Any], product: Product | None) -> tuple[dict[str, Any], dict]:
    errors: dict[str, Any] = {}
    unknown = set(data) - ALL_FIELDS
    if unknown:
        errors["_unknown"] = [f"Unknown field(s): {', '.join(sorted(unknown))}."]
    clean: dict[str, Any] = {}
    if "title" in data:
        clean["title"] = _text(data["title"], "title", 200, errors, required=True)
    if "slug" in data:
        clean["slug"] = _validate_slug(data["slug"], product, errors)
    for name, max_len in (
        ("subtitle", 240),
        ("short_description", 400),
        ("format_label", 80),
        ("edition", 60),
        ("seo_title", 200),
        ("meta_description", 320),
    ):
        if name in data:
            clean[name] = _text(data[name], name, max_len, errors)
    if "audience" in data:
        clean["audience"] = _text(data["audience"], "audience", 600, errors, multiline=True)
    if "sample_text" in data:
        clean["sample_text"] = _text(
            data["sample_text"], "sample_text", 5000, errors, multiline=True
        )
    if "description" in data:
        try:
            clean["description"] = validate_blocks(data["description"] or [])
        except ValidationError as exc:
            errors["description"] = (exc.details or {}).get("body", exc.details)
    if "benefits" in data:
        clean["benefits"] = _string_list(data["benefits"], "benefits", 12, 200, errors)
    if "included" in data:
        clean["included"] = _object_list(
            data["included"],
            "included",
            {"title": (120, True), "description": (400, False), "format": (40, False)},
            20,
            errors,
        )
    if "faq" in data:
        clean["faq"] = _object_list(
            data["faq"], "faq", {"question": (200, True), "answer": (1500, True)}, 20, errors
        )
    if "language" in data:
        lang = (data["language"] or "en").strip() if isinstance(data["language"], str) else ""
        if not _LANG.match(lang):
            errors["language"] = ["Use a language code such as en or en-GB."]
        clean["language"] = lang
    if "page_count" in data:
        value = data["page_count"]
        if value in (None, ""):
            clean["page_count"] = None
        elif not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5000:
            errors["page_count"] = ["Enter the real page count (1–5000), or leave it empty."]
        else:
            clean["page_count"] = value
    for name in ("author_id", "cover_media_id", "social_image_id"):
        if name in data:
            clean[name] = _id_or_none(data[name], name, errors)
    if "cover_theme" in data:
        if data["cover_theme"] not in COVER_THEMES:
            errors["cover_theme"] = [f"Use one of: {', '.join(COVER_THEMES)}."]
        else:
            clean["cover_theme"] = data["cover_theme"]
    if "tax_category" in data:
        if data["tax_category"] not in TAX_CATEGORIES:
            errors["tax_category"] = ["Choose a tax classification from the list."]
        else:
            clean["tax_category"] = data["tax_category"]
    for name, max_items in (
        ("gallery", 12),
        ("category_ids", 10),
        ("tag_ids", 20),
        ("collection_ids", 20),
    ):
        if name in data:
            value = data[name] or []
            if not isinstance(value, list) or not all(
                isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value
            ):
                errors[name] = ["Choose items from the list."]
            elif len(value) > max_items:
                errors[name] = [f"At most {max_items}."]
            else:
                clean[name] = list(dict.fromkeys(value))
    for name in ("noindex", "is_featured"):
        if name in data:
            if not isinstance(data[name], bool):
                errors[name] = ["Must be true or false."]
            else:
                clean[name] = data[name]
    if "featured_order" in data:
        value = data["featured_order"]
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 1000:
            errors["featured_order"] = ["Use a number between 0 and 1000."]
        else:
            clean["featured_order"] = value
    if "sales_status" in data:
        if data["sales_status"] not in ("coming_soon", "on_sale"):
            errors["sales_status"] = ["Use coming_soon or on_sale."]
        else:
            clean["sales_status"] = data["sales_status"]
    if "pricing_model" in data:
        if data["pricing_model"] not in ("paid", "free"):
            errors["pricing_model"] = ["Use paid or free."]
        else:
            clean["pricing_model"] = data["pricing_model"]
    for name in ("available_from", "available_until"):
        if name in data:
            clean[name] = _parse_dt(data[name], name, errors)
    start = clean.get("available_from", product.available_from if product else None)
    end = clean.get("available_until", product.available_until if product else None)
    if start and end and end <= start:
        errors["available_until"] = ["The end must be after the start."]
    return clean, errors


def _check_refs(clean: dict[str, Any], errors: dict) -> None:
    from ..admin.media_admin import media_ref_problems

    media = {k: clean[k] for k in ("cover_media_id", "social_image_id") if clean.get(k)}
    for index, media_id in enumerate(clean.get("gallery") or []):
        media[f"gallery.{index}"] = media_id
    for key, problem in media_ref_problems(media).items():
        errors[key] = [problem]
    if clean.get("author_id"):
        author = db.session.get(Author, clean["author_id"])
        if author is None or author.status != "active":
            errors["author_id"] = ["Choose an active author."]
    for name, model in (
        ("category_ids", ProductCategory),
        ("tag_ids", Tag),
        ("collection_ids", ProductCollection),
    ):
        ids = clean.get(name) or []
        if ids:
            found = set(db.session.scalars(select(model.id).where(model.id.in_(ids))))
            if set(ids) - found:
                errors[name] = ["One or more selected items no longer exist."]


# ---- revisions --------------------------------------------------------------------------


def _record_revision(product: Product, kind: str, actor: User | None, summary_text: str) -> None:
    snapshot = catalogue.snapshot_document(product) | {
        "status": product.status,
        "sales_status": product.sales_status,
        "pricing_model": product.pricing_model,
        "prices": [price_dict(p) for p in product.prices],
        "bundle_product_ids": [i.product_id for i in product.bundle_items],
    }
    latest = db.session.scalar(
        select(ProductRevision)
        .where(ProductRevision.product_id == product.id)
        .order_by(ProductRevision.number.desc())
        .limit(1)
    )
    if (
        kind == "draft"
        and latest is not None
        and latest.kind == "draft"
        and actor is not None
        and latest.created_by_id == actor.id
        and latest.created_at > _now() - DRAFT_COALESCE
    ):
        latest.snapshot, latest.summary, latest.created_at = snapshot, summary_text, _now()
        return
    db.session.add(
        ProductRevision(
            product_id=product.id,
            number=(latest.number + 1) if latest else 1,
            kind=kind,
            summary=summary_text[:300],
            snapshot=snapshot,
            created_by_id=actor.id if actor else None,
        )
    )


def revisions(product: Product) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "number": r.number,
            "kind": r.kind,
            "summary": r.summary,
            "created_at": iso(r.created_at),
            "created_by": r.created_by.display_name if r.created_by else None,
            "title": r.snapshot.get("title"),
        }
        for r in db.session.scalars(
            select(ProductRevision)
            .where(ProductRevision.product_id == product.id)
            .order_by(ProductRevision.number.desc())
        )
    ]


# ---- create / update --------------------------------------------------------------------


def create(data: dict[str, Any], actor: User) -> Product:
    _require(actor, P.PRODUCTS_CREATE)
    errors: dict[str, Any] = {}
    product_type = data.get("product_type")
    ptype = PRODUCT_TYPES.get(product_type)
    if ptype is None or not ptype.available:
        errors["product_type"] = [
            "Choose one of: " + ", ".join(t.label for t in available_types()) + "."
        ]
    title = _text(data.get("title"), "title", 200, errors, required=True)
    extra = {k: v for k, v in data.items() if k not in ("product_type", "title", "slug")}
    if set(extra) - CONTENT_FIELDS:
        errors["_unknown"] = ["Only content fields can be set when creating a product."]
    if errors:
        raise ValidationError(details=errors)
    slug = data.get("slug") or unique_slug(title)
    product = Product(
        public_id=secrets.token_hex(8),
        slug="pending-" + secrets.token_hex(6),
        product_type=product_type,
        title=title,
        format_label=ptype.default_format,
        pricing_model="paid",
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    db.session.add(product)
    db.session.flush()
    clean, errors = _clean({"slug": slug, **extra}, product)
    _check_refs(clean, errors)
    if errors:
        db.session.rollback()
        raise ValidationError(details=errors)
    _apply(product, clean)
    _record_revision(product, "draft", actor, "Created")
    audit_service.record(
        "product.created", "product", product.id, actor=actor, details={"title": title}
    )
    return product


def _apply(product: Product, clean: dict[str, Any]) -> None:
    for key, value in clean.items():
        if key == "category_ids":
            product.categories = (
                list(
                    db.session.scalars(select(ProductCategory).where(ProductCategory.id.in_(value)))
                )
                if value
                else []
            )
        elif key == "tag_ids":
            product.tags = (
                list(db.session.scalars(select(Tag).where(Tag.id.in_(value)))) if value else []
            )
        elif key == "collection_ids":
            _set_collections(product, value)
        else:
            setattr(product, key, value)


def _set_collections(product: Product, collection_ids: list[int]) -> None:
    existing = {
        i.collection_id: i
        for i in db.session.scalars(
            select(ProductCollectionItem).where(ProductCollectionItem.product_id == product.id)
        )
    }
    for cid, item in existing.items():
        if cid not in collection_ids:
            db.session.delete(item)
    for cid in collection_ids:
        if cid not in existing:
            last = db.session.scalar(
                select(func.max(ProductCollectionItem.position)).where(
                    ProductCollectionItem.collection_id == cid
                )
            )
            db.session.add(
                ProductCollectionItem(
                    collection_id=cid, product_id=product.id, position=(last or 0) + 1
                )
            )


LIVE_FIELDS = {"is_featured", "featured_order", "collection_ids"} | PUBLISH_FIELDS | PRICE_FIELDS


def update(product: Product, data: dict[str, Any], actor: User) -> Product:
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object.")
    if product.status == "archived":
        raise ConflictError("Restore this product before editing it.")
    lock = data.get("lock_version")
    if lock is not None and lock != product.lock_version:
        raise ConflictError(
            "Someone else saved this product while you were editing.",
            details={"code": "edit_conflict", "lock_version": product.lock_version},
        )
    fields = set(data) - {"lock_version"}
    if fields & CONTENT_FIELDS:
        _require(actor, P.PRODUCTS_EDIT)
    if fields & PUBLISH_FIELDS:
        _require(actor, P.PRODUCTS_PUBLISH)
    if fields & PRICE_FIELDS:
        _require(actor, P.PRODUCTS_MANAGE_PRICES)
    clean, errors = _clean(data, product)
    _check_refs(clean, errors)
    if clean.get("sales_status") == "on_sale":
        preview_state = _preview_readiness(product, clean)
        if preview_state:
            errors["sales_status"] = preview_state
    if errors:
        raise ValidationError("Some fields need attention.", details=errors)
    before = catalogue.snapshot_document(product) | {
        k: getattr(product, k) for k in PUBLISH_FIELDS | PRICE_FIELDS | {"is_featured"}
    }
    _apply(product, clean)
    product.updated_by_id = actor.id
    product.lock_version += 1
    db.session.flush()
    after = catalogue.snapshot_document(product) | {
        k: getattr(product, k) for k in PUBLISH_FIELDS | PRICE_FIELDS | {"is_featured"}
    }
    changes = audit_service.changed_fields(before, after)
    if changes:
        _record_revision(product, "draft", actor, "Saved draft")
        audit_service.record("product.updated", "product", product.id, actor=actor, details=changes)
        if product.status == "published" and fields & LIVE_FIELDS:
            record_public_change("product", product.id, "product_availability_changed", actor)
    return product


def _preview_readiness(product: Product, clean: dict[str, Any]) -> list[str]:
    """Refuse "on sale" unless files and prices make the product deliverable."""
    model = clean.get("pricing_model", product.pricing_model)
    state = catalogue.readiness(product)
    issues = [i for i in state["issues"] if model == "paid" or "price" not in i.lower()]
    return issues


# ---- publishing -------------------------------------------------------------------------


def _publish_problems(product: Product) -> list[str]:
    problems = []
    if not product.short_description:
        problems.append("Add a short description.")
    ptype = PRODUCT_TYPES.get(product.product_type)
    if ptype is None or not ptype.available:
        problems.append("This product type cannot be published yet.")
    if product.slug in RESERVED_PRODUCT_SLUGS:
        problems.append("Choose a different address.")
    if product.sales_status == "on_sale":
        problems.extend(catalogue.readiness(product)["issues"])
    return problems


def publish(product: Product, actor: User) -> Product:
    _require(actor, P.PRODUCTS_PUBLISH)
    if product.status == "archived":
        raise ConflictError("Restore this product before publishing it.")
    problems = _publish_problems(product)
    if problems:
        raise ValidationError(
            "This product is not ready to publish.", details={"publish": problems}
        )
    old_slug = product.published_slug if product.status == "published" else product.published_slug
    product.published_snapshot = catalogue.snapshot_document(product)
    if old_slug and old_slug != product.slug:
        from ..redirect_service import create_slug_redirect

        create_slug_redirect(f"/shop/{old_slug}", f"/shop/{product.slug}", actor)
    product.published_slug = product.slug
    now = _now()
    product.status = "published"
    product.published_at = now
    product.first_published_at = product.first_published_at or now
    product.lock_version += 1
    db.session.flush()
    _record_revision(product, "publish", actor, "Published")
    audit_service.record(
        "product.published", "product", product.id, actor=actor, details={"slug": product.slug}
    )
    record_public_change("product", product.id, "product_published", actor)
    if catalogue.readiness(product)["purchasable"]:
        from ..newsletter.automations import record_event

        # Announced once, and only when it can really be bought (never "coming soon").
        record_event("product_published", f"product:{product.id}", {"product_id": product.id})
    return product


def unpublish(product: Product, actor: User) -> Product:
    _require(actor, P.PRODUCTS_PUBLISH)
    if product.status != "published":
        raise ConflictError("This product is not published.")
    product.status = "draft"
    product.lock_version += 1
    audit_service.record("product.unpublished", "product", product.id, actor=actor)
    record_public_change("product", product.id, "product_unpublished", actor)
    return product


def discard_changes(product: Product, actor: User) -> Product:
    _require(actor, P.PRODUCTS_EDIT)
    if not product.published_snapshot:
        raise ConflictError("There is no published version to go back to.")
    _load_snapshot(product, product.published_snapshot)
    product.lock_version += 1
    _record_revision(product, "restore", actor, "Discarded unpublished changes")
    audit_service.record("product.changes_discarded", "product", product.id, actor=actor)
    return product


def _load_snapshot(product: Product, snap: dict[str, Any]) -> None:
    for key in (
        "title",
        "subtitle",
        "short_description",
        "description",
        "benefits",
        "included",
        "faq",
        "audience",
        "format_label",
        "language",
        "edition",
        "page_count",
        "sample_text",
        "cover_theme",
        "gallery",
        "seo_title",
        "meta_description",
        "noindex",
    ):
        if key in snap:
            setattr(product, key, snap[key])
    for key in ("author_id", "cover_media_id", "social_image_id"):
        value = snap.get(key)
        if key == "author_id":
            author = db.session.get(Author, value) if value else None
            product.author_id = value if author else None
        else:
            from ...models import MediaAsset

            asset = db.session.get(MediaAsset, value) if value else None
            setattr(product, key, value if asset is not None else None)
    if "slug" in snap and snap["slug"] != product.slug:
        clash = db.session.scalar(
            select(Product.id).where(Product.slug == snap["slug"], Product.id != product.id)
        )
        if not clash:
            product.slug = snap["slug"]
    product.categories = list(
        db.session.scalars(
            select(ProductCategory).where(ProductCategory.id.in_(snap.get("category_ids") or []))
        )
    )


def restore_revision(product: Product, revision_id: int, actor: User) -> Product:
    _require(actor, P.PRODUCTS_EDIT)
    revision = db.session.get(ProductRevision, revision_id)
    if revision is None or revision.product_id != product.id:
        raise NotFoundError("Revision not found.")
    if product.status == "archived":
        raise ConflictError("Restore this product before restoring a revision.")
    _load_snapshot(product, revision.snapshot)
    product.lock_version += 1
    _record_revision(product, "restore", actor, f"Restored revision #{revision.number}")
    audit_service.record(
        "product.revision_restored",
        "product",
        product.id,
        actor=actor,
        details={"revision": revision.number},
    )
    return product


def archive(product: Product, actor: User) -> Product:
    _require(actor, P.PRODUCTS_ARCHIVE)
    if product.status == "archived":
        raise ConflictError("Already archived.")
    was_public = product.status == "published"
    product.status = "archived"
    product.is_featured = False
    product.archived_at = _now()
    product.lock_version += 1
    audit_service.record("product.archived", "product", product.id, actor=actor)
    if was_public:
        record_public_change("product", product.id, "product_archived", actor)
    return product


def restore(product: Product, actor: User) -> Product:
    _require(actor, P.PRODUCTS_ARCHIVE)
    if product.status != "archived":
        raise ConflictError("This product is not archived.")
    product.status = "draft"
    product.archived_at = None
    product.lock_version += 1
    audit_service.record("product.restored", "product", product.id, actor=actor)
    return product


def duplicate(product: Product, actor: User) -> Product:
    _require(actor, P.PRODUCTS_CREATE)
    copy = Product(
        public_id=secrets.token_hex(8),
        slug=unique_slug(f"{product.slug}-copy"),
        product_type=product.product_type,
        title=f"{product.title} (copy)"[:200],
        created_by_id=actor.id,
        updated_by_id=actor.id,
        pricing_model=product.pricing_model,
    )
    for key in (
        "subtitle",
        "short_description",
        "description",
        "benefits",
        "included",
        "faq",
        "audience",
        "format_label",
        "language",
        "edition",
        "sample_text",
        "author_id",
        "cover_media_id",
        "cover_theme",
        "gallery",
        "social_image_id",
        "seo_title",
        "meta_description",
        "noindex",
        "tax_category",
    ):
        setattr(copy, key, getattr(product, key))
    copy.categories = list(product.categories)
    copy.tags = list(product.tags)
    db.session.add(copy)
    db.session.flush()
    if product.is_bundle:
        for item in product.bundle_items:
            db.session.add(
                BundleItem(bundle_id=copy.id, product_id=item.product_id, position=item.position)
            )
    _record_revision(copy, "draft", actor, f"Duplicated from “{product.title}”")
    audit_service.record(
        "product.duplicated", "product", copy.id, actor=actor, details={"source": product.id}
    )
    return copy


# ---- prices -----------------------------------------------------------------------------


def set_price(product: Product, data: dict[str, Any], actor: User) -> ProductPrice:
    _require(actor, P.PRODUCTS_MANAGE_PRICES)
    errors: dict[str, Any] = {}
    allowed = {
        "currency",
        "kind",
        "amount_minor",
        "compare_at_minor",
        "starts_at",
        "ends_at",
        "is_active",
    }
    if set(data) - allowed:
        errors["_unknown"] = [f"Unknown field(s): {', '.join(sorted(set(data) - allowed))}."]
    currency = str(data.get("currency") or "").upper()
    if currency not in CURRENCIES:
        errors["currency"] = ["Choose a supported currency."]
    kind = data.get("kind") or "regular"
    if kind not in ("regular", "promotional"):
        errors["kind"] = ["Use regular or promotional."]
    amount = data.get("amount_minor")
    if (
        not isinstance(amount, int)
        or isinstance(amount, bool)
        or not 0 <= amount <= MAX_AMOUNT_MINOR
    ):
        errors["amount_minor"] = ["Enter the amount in minor units (e.g. 1250 for 12.50)."]
    compare = data.get("compare_at_minor")
    if compare is not None:
        if kind == "promotional":
            errors["compare_at_minor"] = ["Promotional prices compare against the regular price."]
        elif (
            not isinstance(compare, int)
            or isinstance(compare, bool)
            or (isinstance(amount, int) and compare <= amount)
        ):
            errors["compare_at_minor"] = ["The compare-at price must be higher than the price."]
    starts = _parse_dt(data.get("starts_at"), "starts_at", errors)
    ends = _parse_dt(data.get("ends_at"), "ends_at", errors)
    if starts and ends and ends <= starts:
        errors["ends_at"] = ["The end must be after the start."]
    if kind == "regular" and (starts or ends):
        errors["starts_at"] = ["Regular prices have no schedule; use a promotional price."]
    active = data.get("is_active", True)
    if not isinstance(active, bool):
        errors["is_active"] = ["Must be true or false."]
    if product.pricing_model == "free":
        errors["currency"] = ["This product is free. Switch it to paid before setting prices."]
    if not errors and kind == "promotional":
        regular = next(
            (p for p in product.prices if p.currency == currency and p.kind == "regular"), None
        )
        if regular is None:
            errors["kind"] = [f"Set a regular {currency} price first."]
        elif amount >= regular.amount_minor:
            errors["amount_minor"] = ["A promotional price must be lower than the regular price."]
    if not errors and kind == "regular" and amount == 0:
        errors["amount_minor"] = ["Paid products need a price above zero (or make it free)."]
    if errors:
        raise ValidationError("The price is invalid.", details=errors)
    price = next((p for p in product.prices if p.currency == currency and p.kind == kind), None)
    before = price_dict(price) if price else None
    if price is None:
        price = ProductPrice(
            product_id=product.id, currency=currency, kind=kind, amount_minor=amount
        )
        product.prices.append(price)
    price.amount_minor = amount
    price.compare_at_minor = compare
    price.starts_at, price.ends_at = starts, ends
    price.is_active = active
    price.approved_by_id, price.approved_at = actor.id, _now()
    if kind == "regular":
        promo = next(
            (p for p in product.prices if p.currency == currency and p.kind == "promotional"), None
        )
        if promo is not None and promo.amount_minor >= amount:
            promo.is_active = False
    db.session.flush()
    _record_revision(product, "draft", actor, f"Price {currency} {kind} set")
    audit_service.record(
        "product.price_set",
        "product",
        product.id,
        actor=actor,
        details={"before": before, "after": price_dict(price)},
    )
    if product.status == "published":
        record_public_change("product", product.id, "product_price_changed", actor)
    return price


def delete_price(product: Product, price_id: int, actor: User) -> None:
    _require(actor, P.PRODUCTS_MANAGE_PRICES)
    price = next((p for p in product.prices if p.id == price_id), None)
    if price is None:
        raise NotFoundError("Price not found.")
    if price.kind == "regular" and any(
        p.currency == price.currency and p.kind == "promotional" for p in product.prices
    ):
        raise ConflictError("Remove the promotional price in this currency first.")
    details = price_dict(price)
    product.prices.remove(price)
    db.session.flush()
    _record_revision(
        product, "draft", actor, f"Price {details['currency']} {details['kind']} removed"
    )
    audit_service.record(
        "product.price_removed", "product", product.id, actor=actor, details=details
    )
    if product.status == "published":
        record_public_change("product", product.id, "product_price_changed", actor)
        if product.sales_status == "on_sale" and not catalogue.readiness(product)["purchasable"]:
            audit_service.record(
                "product.no_longer_purchasable", "product", product.id, actor=actor
            )


# ---- bundles ----------------------------------------------------------------------------


def set_bundle_items(product: Product, product_ids: Any, actor: User) -> Product:
    _require(actor, P.PRODUCTS_MANAGE_BUNDLES)
    if not product.is_bundle:
        raise ValidationError(details={"items": ["Only bundles can include other products."]})
    if (
        not isinstance(product_ids, list)
        or not all(isinstance(i, int) and not isinstance(i, bool) for i in product_ids)
        or len(product_ids) > 20
    ):
        raise ValidationError(details={"items": ["Choose up to 20 products."]})
    ids = list(dict.fromkeys(product_ids))
    if product.id in ids:
        raise ValidationError(details={"items": ["A bundle cannot include itself."]})
    found = {p.id: p for p in db.session.scalars(select(Product).where(Product.id.in_(ids)))}
    missing = [i for i in ids if i not in found]
    if missing:
        raise ValidationError(details={"items": ["One or more products no longer exist."]})
    archived = [found[i].title for i in ids if found[i].status == "archived"]
    if archived:
        raise ValidationError(details={"items": [f"Archived: {', '.join(archived)}."]})
    if catalogue.would_create_cycle(product.id, ids):
        raise ValidationError(
            details={"items": ["That would make the bundle include itself (circular bundle)."]}
        )
    nested_depth = max([catalogue.bundle_depth(found[i]) for i in ids if found[i].is_bundle] or [0])
    if nested_depth + 1 > catalogue.MAX_BUNDLE_DEPTH:
        raise ValidationError(details={"items": ["Bundles can be nested at most 3 levels deep."]})
    before = [i.product_id for i in product.bundle_items]
    product.bundle_items = [
        BundleItem(bundle_id=product.id, product_id=pid, position=pos)
        for pos, pid in enumerate(ids)
    ]
    product.lock_version += 1
    db.session.flush()
    _record_revision(product, "draft", actor, "Bundle contents changed")
    audit_service.record(
        "product.bundle_changed",
        "product",
        product.id,
        actor=actor,
        details={"before": before, "after": ids},
    )
    if product.status == "published":
        record_public_change("product", product.id, "bundle_changed", actor)
    return product


# ---- categories and collections ---------------------------------------------------------


def _all_categories() -> list[ProductCategory]:
    return list(
        db.session.scalars(
            select(ProductCategory).order_by(ProductCategory.sort_order, ProductCategory.name)
        )
    )


def category_dict(c: ProductCategory) -> dict[str, Any]:
    count = db.session.scalar(
        select(func.count())
        .select_from(Product)
        .join(Product.categories)
        .where(ProductCategory.id == c.id)
    )
    return {
        "id": c.id,
        "slug": c.slug,
        "name": c.name,
        "description": c.description,
        "sort_order": c.sort_order,
        "is_active": c.is_active,
        "product_count": count or 0,
    }


def _taxonomy_clean(data: dict[str, Any], model, item, allowed: set[str]) -> dict[str, Any]:
    errors: dict[str, Any] = {}
    if set(data) - allowed:
        errors["_unknown"] = [f"Unknown field(s): {', '.join(sorted(set(data) - allowed))}."]
    clean: dict[str, Any] = {}
    if "name" in data or item is None:
        clean["name"] = _text(data.get("name"), "name", 120, errors, required=True)
    if "slug" in data or item is None:
        slug = (data.get("slug") or slugify(clean.get("name") or "")).strip().lower()
        if not slug or not SLUG_RE.match(slug) or len(slug) > 120:
            errors["slug"] = ["Use lowercase letters, numbers and hyphens."]
        elif db.session.scalar(
            select(model.id).where(model.slug == slug, model.id != (item.id if item else 0))
        ):
            errors["slug"] = ["This address is already used."]
        clean["slug"] = slug
    if "description" in data:
        clean["description"] = _text(
            data["description"], "description", 600, errors, multiline=True
        )
    for name in ("is_active", "is_featured"):
        if name in data:
            if not isinstance(data[name], bool):
                errors[name] = ["Must be true or false."]
            else:
                clean[name] = data[name]
    if "sort_order" in data:
        if not isinstance(data["sort_order"], int) or isinstance(data["sort_order"], bool):
            errors["sort_order"] = ["Must be a whole number."]
        else:
            clean["sort_order"] = data["sort_order"]
    for name, max_len in (("seo_title", 200), ("meta_description", 320)):
        if name in data:
            clean[name] = _text(data[name], name, max_len, errors) or None
    if "cover_media_id" in data:
        clean["cover_media_id"] = _id_or_none(data["cover_media_id"], "cover_media_id", errors)
        if clean["cover_media_id"]:
            from ..admin.media_admin import media_ref_problems

            for key, problem in media_ref_problems(
                {"cover_media_id": clean["cover_media_id"]}
            ).items():
                errors[key] = [problem]
    if errors:
        raise ValidationError(details=errors)
    return clean


def save_category(data: dict[str, Any], actor: User, category: ProductCategory | None = None):
    _require(actor, P.PRODUCTS_EDIT)
    clean = _taxonomy_clean(
        data, ProductCategory, category, {"name", "slug", "description", "sort_order", "is_active"}
    )
    if category is None:
        category = ProductCategory(**clean)
        db.session.add(category)
    else:
        for k, v in clean.items():
            setattr(category, k, v)
    db.session.flush()
    audit_service.record(
        "product_category.saved", "product_category", category.id, actor=actor, details=clean
    )
    record_public_change("product_category", category.id, "product_category_changed", actor)
    return category


def delete_category(category: ProductCategory, actor: User) -> None:
    _require(actor, P.PRODUCTS_EDIT)
    if category_dict(category)["product_count"]:
        raise ConflictError("Products still use this category. Deactivate it instead.")
    audit_service.record("product_category.deleted", "product_category", category.id, actor=actor)
    db.session.delete(category)
    record_public_change("product_category", category.id, "product_category_changed", actor)


def collection_dict(c: ProductCollection) -> dict[str, Any]:
    return {
        "id": c.id,
        "slug": c.slug,
        "name": c.name,
        "description": c.description,
        "cover_media_id": c.cover_media_id,
        "seo_title": c.seo_title,
        "meta_description": c.meta_description,
        "is_active": c.is_active,
        "is_featured": c.is_featured,
        "sort_order": c.sort_order,
        "product_ids": [i.product_id for i in c.items],
        "products": [
            {"id": i.product_id, "title": p.title, "status": p.status}
            for i in c.items
            if (p := db.session.get(Product, i.product_id))
        ],
    }


def save_collection(data: dict[str, Any], actor: User, collection: ProductCollection | None = None):
    _require(actor, P.PRODUCTS_EDIT)
    product_ids = data.pop("product_ids", None) if isinstance(data, dict) else None
    clean = _taxonomy_clean(
        data,
        ProductCollection,
        collection,
        {
            "name",
            "slug",
            "description",
            "sort_order",
            "is_active",
            "is_featured",
            "seo_title",
            "meta_description",
            "cover_media_id",
        },
    )
    if collection is None:
        collection = ProductCollection(**clean)
        db.session.add(collection)
        db.session.flush()
    else:
        for k, v in clean.items():
            setattr(collection, k, v)
    if product_ids is not None:
        if not isinstance(product_ids, list) or not all(
            isinstance(i, int) and not isinstance(i, bool) for i in product_ids
        ):
            raise ValidationError(details={"product_ids": ["Choose products from the list."]})
        ids = list(dict.fromkeys(product_ids))[:60]
        found = set(db.session.scalars(select(Product.id).where(Product.id.in_(ids))))
        if set(ids) - found:
            raise ValidationError(
                details={"product_ids": ["One or more products no longer exist."]}
            )
        collection.items = [
            ProductCollectionItem(collection_id=collection.id, product_id=pid, position=pos)
            for pos, pid in enumerate(ids)
        ]
    db.session.flush()
    audit_service.record(
        "product_collection.saved", "product_collection", collection.id, actor=actor, details=clean
    )
    record_public_change("product_collection", collection.id, "product_collection_changed", actor)
    return collection


def delete_collection(collection: ProductCollection, actor: User) -> None:
    _require(actor, P.PRODUCTS_EDIT)
    audit_service.record(
        "product_collection.deleted", "product_collection", collection.id, actor=actor
    )
    db.session.delete(collection)
    record_public_change("product_collection", collection.id, "product_collection_changed", actor)
