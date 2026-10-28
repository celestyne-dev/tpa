"""Commerce and revenue analytics (Batch 11.2): aggregates only, no order-level data.

Financial definitions are the existing finance report's (``order_admin.revenue_report``):

- gross = provider-verified ``charge`` payment transactions (written only after
  Paystack verification), refunds = processed ``refund`` transactions, net = gross −
  refunds (before provider fees), all by the transaction's recorded time;
- recognised orders = orders that reached ``paid`` (or were later refunded), by
  ``paid_at``; pending, awaiting payment, failed and cancelled orders are never sales;
- product revenue = the order lines' historical ``line_total_minor`` (the price paid),
  never today's catalogue price.

Scope: product purchases (``orders.kind = 'purchase'``). Membership subscription payments
are reported in Membership reports. Each currency is reported separately (no conversion
policy is configured) and test/live mode are never mixed.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from ...commerce.currency import money
from ...commerce.product_types import type_label
from ...extensions import db
from ...models import Order, OrderItem, PaymentTransaction, Product, ProductCategory
from ...models.commerce import product_categories
from ...utils.errors import ValidationError
from ..serializers import iso
from . import reports as traffic

RECOGNISED = ("paid", "partially_refunded", "refunded")
TOP = 25


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime(start.year, start.month, start.day, tzinfo=UTC),
        datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1),
    )


def _filters(args: dict[str, Any]) -> tuple[str, str | None]:
    mode = args.get("mode") or "live"
    if mode not in ("live", "test"):
        raise ValidationError(details={"mode": ["Use live or test."]})
    currency = (args.get("currency") or "").upper() or None
    if currency and (len(currency) != 3 or not currency.isalpha()):
        raise ValidationError(details={"currency": ["Use a three-letter currency code."]})
    return mode, currency


def product_group(product_type: str) -> str:
    if product_type == "course":
        return "course"
    if product_type == "bundle":
        return "bundle"
    return "resource"


def _day(value) -> date:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC).date()
    return value


def commerce_report(args: dict[str, Any]) -> dict[str, Any]:
    start, end, granularity = traffic.resolve_range(args)
    mode, currency = _filters(args)
    lo, hi = _bounds(start, end)
    T = PaymentTransaction

    def tx_rows(kind: str, status: str, any_mode: bool = False):
        stmt = (
            select(T.mode, T.currency, T.amount_minor, T.created_at, T.order_id)
            .join(Order, Order.id == T.order_id)
            .where(
                Order.kind == "purchase",
                T.kind == kind,
                T.status == status,
                T.created_at >= lo,
                T.created_at < hi,
            )
        )
        if not any_mode:
            stmt = stmt.where(T.mode == mode)
        if currency:
            stmt = stmt.where(T.currency == currency)
        return db.session.execute(stmt).all()

    charges = tx_rows("charge", "success")
    refunds = tx_rows("refund", "processed")

    paid_stmt = select(Order.id, Order.currency, Order.total_minor, Order.paid_at).where(
        Order.kind == "purchase",
        Order.mode == mode,
        Order.status.in_(RECOGNISED),
        Order.paid_at >= lo,
        Order.paid_at < hi,
    )
    if currency:
        paid_stmt = paid_stmt.where(Order.currency == currency)
    paid_orders = db.session.execute(paid_stmt).all()

    # ---- per-currency KPIs -------------------------------------------------------------
    cur: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "gross": 0,
            "charges": 0,
            "refunds": 0,
            "refund_count": 0,
            "orders": 0,
            "order_total": 0,
        }
    )
    for _m, code, amount, _at, _o in charges:
        cur[code]["gross"] += amount
        cur[code]["charges"] += 1
    for _m, code, amount, _at, _o in refunds:
        cur[code]["refunds"] += amount
        cur[code]["refund_count"] += 1
    for _id, code, total, _at in paid_orders:
        cur[code]["orders"] += 1
        cur[code]["order_total"] += total
    currencies = []
    for code in sorted(cur):
        c = cur[code]
        currencies.append(
            {
                "currency": code,
                "verified_sales": c["charges"],
                "gross": money(c["gross"], code),
                "refunds": money(c["refunds"], code),
                "refund_count": c["refund_count"],
                "net": money(c["gross"] - c["refunds"], code),
                "orders": c["orders"],
                "average_order_value": money(round(c["order_total"] / c["orders"]), code)
                if c["orders"]
                else None,
            }
        )

    # ---- order statuses (counts only; created in range) ---------------------------------
    status_stmt = (
        select(Order.status, func.count(Order.id))
        .where(
            Order.kind == "purchase",
            Order.mode == mode,
            Order.created_at >= lo,
            Order.created_at < hi,
        )
        .group_by(Order.status)
    )
    if currency:
        status_stmt = status_stmt.where(Order.currency == currency)
    statuses = {s: int(n) for s, n in db.session.execute(status_stmt)}

    # ---- test vs live (always both modes) ----------------------------------------------
    modes: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for m, code, amount, _at, _o in tx_rows("charge", "success", any_mode=True):
        modes[(m, code)][0] += 1
        modes[(m, code)][1] += amount
    mode_rows = [
        {"mode": m, "currency": c, "verified_sales": v[0], "gross": money(v[1], c)}
        for (m, c), v in sorted(modes.items())
    ]

    # ---- trends ------------------------------------------------------------------------
    buckets = []
    day = start
    while day <= end:
        key = traffic._bucket(day, granularity)
        if not buckets or buckets[-1] != key:
            buckets.append(key)
        day += timedelta(days=1)
    trend: dict[str, dict[str, dict[str, int]]] = {
        code: {b: {"gross": 0, "refunds": 0, "orders": 0} for b in buckets} for code in cur
    }
    for _m, code, amount, at, _o in charges:
        trend[code][traffic._bucket(_day(at), granularity)]["gross"] += amount
    for _m, code, amount, at, _o in refunds:
        trend[code][traffic._bucket(_day(at), granularity)]["refunds"] += amount
    for _id, code, _t, at in paid_orders:
        trend[code][traffic._bucket(_day(at), granularity)]["orders"] += 1
    series = [
        {
            "currency": code,
            "points": [
                {
                    "period": b,
                    "gross": money(v["gross"], code),
                    "refunds": money(v["refunds"], code),
                    "net": money(v["gross"] - v["refunds"], code),
                    "orders": v["orders"],
                }
                for b, v in points.items()
            ],
        }
        for code, points in sorted(trend.items())
    ]

    # ---- products ----------------------------------------------------------------------
    order_ids = [o[0] for o in paid_orders]
    lines = (
        db.session.execute(
            select(
                OrderItem.order_id,
                OrderItem.product_id,
                OrderItem.title,
                OrderItem.product_type,
                OrderItem.currency,
                OrderItem.quantity,
                OrderItem.line_total_minor,
            ).where(OrderItem.order_id.in_(order_ids))
        ).all()
        if order_ids
        else []
    )
    products: dict[tuple[int, str], dict[str, Any]] = {}
    groups: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    types: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    sold_ids = set()
    for _oid, pid, title, ptype, code, qty, total in lines:
        sold_ids.add(pid)
        row = products.setdefault(
            (pid, code),
            {
                "product_id": pid,
                "title": title,
                "product_type": ptype,
                "currency": code,
                "units": 0,
                "revenue_minor": 0,
                "orders": 0,
            },
        )
        row["units"] += qty
        row["revenue_minor"] += total
        row["orders"] += 1
        g = groups[(product_group(ptype), code)]
        g[0] += qty
        g[1] += total
        g[2] += 1
        t = types[(ptype, code)]
        t[0] += qty
        t[1] += total

    # Refunds by product only where attribution is certain: single-line orders.
    line_count = defaultdict(int)
    single_line: dict[int, int] = {}
    for oid, pid, *_rest in lines:
        line_count[oid] += 1
        single_line[oid] = pid
    refund_lines = {}
    if refunds:
        refund_order_ids = {o for *_x, o in refunds}
        counts = dict(
            db.session.execute(
                select(OrderItem.order_id, func.count(OrderItem.id))
                .where(OrderItem.order_id.in_(refund_order_ids))
                .group_by(OrderItem.order_id)
            ).all()
        )
        firsts = dict(
            db.session.execute(
                select(OrderItem.order_id, func.min(OrderItem.product_id))
                .where(OrderItem.order_id.in_(refund_order_ids))
                .group_by(OrderItem.order_id)
            ).all()
        )
        refund_lines = {o: (counts.get(o, 0), firsts.get(o)) for o in refund_order_ids}
    product_refunds: dict[tuple[int, str], list[int]] = defaultdict(lambda: [0, 0])
    unattributed: dict[str, int] = defaultdict(int)
    for _m, code, amount, _at, oid in refunds:
        n, pid = refund_lines.get(oid, (0, None))
        if n == 1 and pid is not None:
            product_refunds[(pid, code)][0] += 1
            product_refunds[(pid, code)][1] += amount
        else:
            unattributed[code] += amount

    titles = {
        p.id: p
        for p in db.session.scalars(
            select(Product).where(Product.id.in_({k[0] for k in product_refunds} | sold_ids or {0}))
        )
    }
    ranked = sorted(products.values(), key=lambda r: (-r["units"], -r["revenue_minor"], r["title"]))
    best = [
        {
            "product_id": r["product_id"],
            "title": r["title"],
            "product_type": r["product_type"],
            "type_label": type_label(r["product_type"]),
            "group": product_group(r["product_type"]),
            "currency": r["currency"],
            "units": r["units"],
            "orders": r["orders"],
            "revenue": money(r["revenue_minor"], r["currency"]),
            "refunds": money(
                product_refunds.get((r["product_id"], r["currency"]), [0, 0])[1], r["currency"]
            ),
            "refund_count": product_refunds.get((r["product_id"], r["currency"]), [0, 0])[0],
        }
        for r in ranked[:TOP]
    ]
    refund_by_product = [
        {
            "product_id": pid,
            "title": titles[pid].title if pid in titles else str(pid),
            "currency": code,
            "refund_count": v[0],
            "refunds": money(v[1], code),
        }
        for (pid, code), v in sorted(product_refunds.items(), key=lambda kv: -kv[1][1])
    ]

    # Categories (current category links of the products sold; revenue is historical).
    category_rows: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    if sold_ids:
        links = db.session.execute(
            select(product_categories.c.product_id, ProductCategory.name)
            .join(ProductCategory, ProductCategory.id == product_categories.c.category_id)
            .where(product_categories.c.product_id.in_(sold_ids))
        ).all()
        names = defaultdict(list)
        for pid, name in links:
            names[pid].append(name)
        for r in products.values():
            for name in names.get(r["product_id"]) or ["Uncategorised"]:
                category_rows[(name, r["currency"])][0] += r["units"]
                category_rows[(name, r["currency"])][1] += r["revenue_minor"]

    unsold = db.session.scalars(
        select(Product)
        .where(
            Product.status == "published",
            Product.pricing_model == "paid",
            Product.product_type != "membership",
            Product.id.not_in(sold_ids or {0}),
        )
        .order_by(Product.title)
        .limit(100)
    ).all()

    return {
        "range": {"from": start.isoformat(), "to": end.isoformat(), "granularity": granularity},
        "filters": {"mode": mode, "currency": currency},
        "generated_at": iso(datetime.now(UTC)),
        "has_data": bool(charges or paid_orders or refunds or statuses),
        "currencies": currencies,
        "order_statuses": statuses,
        "modes": mode_rows,
        "series": series,
        "products": best,
        "groups": [
            {"group": g, "currency": c, "units": v[0], "orders": v[2], "revenue": money(v[1], c)}
            for (g, c), v in sorted(groups.items())
        ],
        "product_types": [
            {
                "product_type": t,
                "type_label": type_label(t),
                "currency": c,
                "units": v[0],
                "revenue": money(v[1], c),
            }
            for (t, c), v in sorted(types.items(), key=lambda kv: -kv[1][1])
        ],
        "categories": [
            {"category": n, "currency": c, "units": v[0], "revenue": money(v[1], c)}
            for (n, c), v in sorted(category_rows.items(), key=lambda kv: (-kv[1][1], kv[0]))
        ],
        "refunds_by_product": refund_by_product,
        "unattributed_refunds": [money(v, c) for c, v in sorted(unattributed.items())],
        "unsold_products": [
            {"product_id": p.id, "title": p.title, "type_label": type_label(p.product_type)}
            for p in unsold
        ],
        "conversion": _conversion(start, end, mode, currency, products, paid_orders),
        "notes": [
            "Gross = Paystack-verified charges; refunds = processed refunds; net = gross − "
            "refunds, before provider fees.",
            "Orders count only once paid; pending, failed, abandoned and cancelled orders are "
            "never sales. Product revenue uses the price paid at the time.",
            "Currencies are reported separately (no conversion is configured) and test-mode "
            "payments are never mixed with live ones.",
            "Membership subscription payments are reported in Membership reports.",
        ],
    }


def _conversion(start, end, mode, currency, products, paid_orders) -> dict[str, Any]:
    """Ratios between first-party page views (Batch 11.1) and orders, only on days where
    page views were measured. Visitor-level purchase conversion is not available: orders
    are deliberately not linked to visitors."""
    unavailable = {
        "available": False,
        "reason": "Orders are not linked to visitors or sessions (no cookies or tracking "
        "identifiers), so visitor or session purchase conversion can't be measured.",
    }
    base = {"purchase_conversion": unavailable}
    if mode != "live":
        return base | {
            "available": False,
            "reason": "Test-mode orders aren't comparable with real visitor traffic.",
        }
    rolled, raw_days = traffic._split_days(start, end)
    daily = traffic._daily_totals(start, end, rolled, raw_days)
    measured = {d for d, (views, _u) in daily.items() if views}
    if not measured:
        return base | {
            "available": False,
            "reason": "No page views were measured in this period (tracking started later or "
            "was off).",
        }
    views = sum(daily[d][0] for d in measured)
    orders = sum(1 for _id, _c, _t, at in paid_orders if _day(at) in measured)
    pages = traffic._page_rows(start, end, raw_days)
    product_views: dict[str, int] = defaultdict(int)
    for r in pages.values():
        if r["page_type"] == "product":
            product_views[r["path"].rsplit("/", 1)[-1]] += r["views"]
    slugs = {
        p.id: (p.published_slug or p.slug)
        for p in db.session.scalars(
            select(Product).where(
                Product.id.in_({r["product_id"] for r in products.values()} or {0})
            )
        )
    }
    per_product = []
    for r in products.values():
        pv = product_views.get(slugs.get(r["product_id"], ""), 0)
        per_product.append(
            {
                "product_id": r["product_id"],
                "title": r["title"],
                "currency": r["currency"],
                "product_page_views": pv,
                "units": r["units"],
                "units_per_100_views": round(r["units"] * 100 / pv, 2) if pv else None,
            }
        )
    per_product.sort(key=lambda r: (-(r["product_page_views"]), r["title"]))
    return base | {
        "available": True,
        "measured_days": len(measured),
        "page_views": views,
        "orders": orders,
        "orders_per_1000_page_views": round(orders * 1000 / views, 2),
        "product_pages": per_product[:TOP],
        "explanation": "Ratios of counts on days with measured page views: not a conversion "
        "rate. Buyers may buy without viewing a product page, and page views exclude visitors "
        "who opted out (Do Not Track / GPC) or browsed with blockers."
        + (" Currency filter applies to orders only." if currency else ""),
    }


def export_csv(args: dict[str, Any]) -> str:
    report = commerce_report(args)
    from .exports import SafeWriter

    safe = SafeWriter()

    class _W:
        @staticmethod
        def writerow(cells):
            safe.row(*cells)

    w = _W()
    w.writerow(
        [
            "report",
            "commerce",
            "mode",
            report["filters"]["mode"],
            "from",
            report["range"]["from"],
            "to",
            report["range"]["to"],
        ]
    )
    w.writerow([])
    w.writerow(
        ["currency", "verified_sales", "orders", "gross", "refunds", "net", "average_order_value"]
    )
    for c in report["currencies"]:
        w.writerow(
            [
                c["currency"],
                c["verified_sales"],
                c["orders"],
                c["gross"]["amount"],
                c["refunds"]["amount"],
                c["net"]["amount"],
                c["average_order_value"]["amount"] if c["average_order_value"] else "",
            ]
        )
    w.writerow([])
    w.writerow(["product", "type", "currency", "units", "orders", "revenue", "refunds"])
    for p in report["products"]:
        w.writerow(
            [
                p["title"],
                p["type_label"],
                p["currency"],
                p["units"],
                p["orders"],
                p["revenue"]["amount"],
                p["refunds"]["amount"],
            ]
        )
    return safe.value()
