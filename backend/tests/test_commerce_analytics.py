"""Batch 11.2: commerce and revenue analytics (aggregates from verified payment records)."""

from __future__ import annotations

import csv
import io
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import (
    AnalyticsPageView,
    Customer,
    Order,
    OrderItem,
    PaymentTransaction,
    Product,
    ProductCategory,
)

URL = "/api/v1/admin/analytics/commerce"
NOW = datetime.now(UTC)
YESTERDAY = NOW - timedelta(days=1)


def _product(title, ptype, *, status="published"):
    p = Product(
        public_id=secrets.token_hex(8),
        slug=title.lower().replace(" ", "-"),
        product_type=ptype,
        title=title,
        status=status,
        pricing_model="paid",
    )
    db.session.add(p)
    db.session.flush()
    return p


def _order(
    customer, lines, *, status="paid", mode="live", currency="USD", paid_at=YESTERDAY, charge=True
):
    total = sum(q * unit for _p, q, unit in lines)
    o = Order(
        number=f"TPA-{secrets.token_hex(4)}",
        public_id=secrets.token_hex(16),
        customer_id=customer.id,
        email=customer.email,
        status=status,
        currency=currency,
        subtotal_minor=total,
        total_minor=total,
        provider="paystack",
        mode=mode,
        idempotency_key=secrets.token_hex(8),
        paid_at=paid_at if status in ("paid", "partially_refunded", "refunded") else None,
        created_at=paid_at,
    )
    for product, qty, unit in lines:
        o.items.append(
            OrderItem(
                product_id=product.id,
                product_public_id=product.public_id,
                title=product.title,
                product_type=product.product_type,
                slug=product.slug,
                currency=currency,
                unit_amount_minor=unit,  # the historical price paid
                quantity=qty,
                line_total_minor=qty * unit,
            )
        )
    db.session.add(o)
    db.session.flush()
    if charge and o.paid_at:
        _tx(o, "charge", total, "success", paid_at)
    return o


def _tx(order, kind, amount, status, at):
    db.session.add(
        PaymentTransaction(
            order_id=order.id,
            provider="paystack",
            kind=kind,
            provider_id=secrets.token_hex(6),
            reference=secrets.token_hex(6),
            mode=order.mode,
            status=status,
            amount_minor=amount,
            currency=order.currency,
            created_at=at,
            occurred_at=at,
        )
    )


@pytest.fixture()
def shop(seeded):
    with seeded.app_context():
        c = Customer(
            public_id=secrets.token_hex(8),
            email="buyer@example.com",
            display_name="Buyer Person",
            status="active",
            is_test_account=False,
            support_notes="",
        )
        db.session.add(c)
        db.session.flush()
        guide = _product("Calm Guide", "guide")
        course = _product("Calm Course", "course")
        journal = _product("Quiet Journal", "journal")
        unsold = _product("Never Sold Pack", "resource_pack")
        cat = ProductCategory(slug="wellbeing", name="Wellbeing")
        db.session.add(cat)
        guide.categories.append(cat)
        a = _order(c, [(guide, 1, 1500), (course, 1, 4900)])  # live USD, 64.00
        _order(c, [(guide, 1, 1200)])  # live USD; guide was cheaper then: 12.00
        _order(c, [(guide, 1, 1500)])  # live USD, 15.00
        b = _order(c, [(journal, 1, 2000)], currency="KES")  # live KES
        _order(c, [(guide, 1, 1500)], mode="test")  # test-mode only
        _order(c, [(course, 1, 4900)], status="awaiting_payment", charge=False)
        _order(c, [(course, 1, 4900)], status="failed", charge=False)
        _order(c, [(guide, 1, 1500)], paid_at=NOW - timedelta(days=200))  # out of range
        _tx(a, "refund", 4900, "processed", YESTERDAY)  # multi-line: unattributed
        _tx(b, "refund", 500, "processed", YESTERDAY)  # single line: the journal
        _tx(b, "refund", 100, "pending_provider", YESTERDAY)  # not processed: ignored
        ids = {"guide": guide.id, "course": course.id, "journal": journal.id, "unsold": unsold.id}
        db.session.commit()
    return seeded, ids


def _report(api, **params):
    res = api.get(URL, query_string={"range": "30d", **params})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def test_verified_revenue_refunds_net_currencies_and_modes(shop, as_role):
    _app, ids = shop
    finance = as_role("finance_manager")
    data = _report(finance)
    by = {c["currency"]: c for c in data["currencies"]}
    usd, kes = by["USD"], by["KES"]
    assert usd["gross"]["amount_minor"] == 6400 + 1200 + 1500
    assert usd["refunds"]["amount_minor"] == 4900
    assert usd["net"]["amount_minor"] == 9100 - 4900
    assert usd["orders"] == 3 and usd["verified_sales"] == 3
    assert usd["average_order_value"]["amount_minor"] == round(9100 / 3)
    assert kes["gross"]["amount_minor"] == 2000 and kes["refunds"]["amount_minor"] == 500
    # No combined cross-currency total exists anywhere in the report.
    assert "total" not in data and "gross" not in data
    # Pending and failed orders are counted by status but never as sales.
    assert data["order_statuses"]["awaiting_payment"] == 1
    assert data["order_statuses"]["failed"] == 1
    test = _report(finance, mode="test")
    assert [c["gross"]["amount_minor"] for c in test["currencies"]] == [1500]
    modes = {(m["mode"], m["currency"]): m["verified_sales"] for m in data["modes"]}
    assert modes == {("live", "KES"): 1, ("live", "USD"): 3, ("test", "USD"): 1}
    only_kes = _report(finance, currency="kes")
    assert [c["currency"] for c in only_kes["currencies"]] == ["KES"]


def test_products_use_historical_prices_groups_categories_and_refunds(shop, as_role):
    _app, ids = shop
    data = _report(as_role("finance_manager"))
    guide = next(p for p in data["products"] if p["product_id"] == ids["guide"])
    assert guide["units"] == 3 and guide["revenue"]["amount_minor"] == 1500 + 1200 + 1500
    assert data["products"][0]["product_id"] == ids["guide"]  # best seller by units
    groups = {(g["group"], g["currency"]): g["units"] for g in data["groups"]}
    assert groups == {("course", "USD"): 1, ("resource", "USD"): 3, ("resource", "KES"): 1}
    cats = {(c["category"], c["currency"]): c["units"] for c in data["categories"]}
    assert cats[("Wellbeing", "USD")] == 3 and cats[("Uncategorised", "USD")] == 1
    [refund] = data["refunds_by_product"]
    assert (refund["product_id"], refund["refunds"]["amount_minor"]) == (ids["journal"], 500)
    assert data["unattributed_refunds"][0]["amount_minor"] == 4900
    unsold = {p["product_id"] for p in data["unsold_products"]}
    assert ids["unsold"] in unsold and ids["guide"] not in unsold


def test_date_filters_and_trends(shop, as_role):
    api = as_role("finance_manager")
    day = YESTERDAY.date().isoformat()
    data = _report(api, date_from=day, date_to=day)
    usd = next(s for s in data["series"] if s["currency"] == "USD")
    assert [p["gross"]["amount_minor"] for p in usd["points"]] == [9100]
    old = (NOW - timedelta(days=200)).date().isoformat()
    past = _report(api, date_from=old, date_to=old)
    assert past["currencies"][0]["gross"]["amount_minor"] == 1500
    empty = _report(api, date_from="2020-01-01", date_to="2020-01-31")
    assert empty["has_data"] is False and empty["products"] == []
    assert api.get(URL, query_string={"mode": "sandbox"}).status_code == 400
    assert api.get(URL, query_string={"currency": "dollars"}).status_code == 400


def test_conversion_is_only_reported_where_measurements_are_compatible(shop, as_role):
    app, ids = shop
    api = as_role("finance_manager")
    data = _report(api)
    assert data["conversion"]["available"] is False  # no page views measured
    assert data["conversion"]["purchase_conversion"]["available"] is False
    with app.app_context():
        for i in range(40):
            db.session.add(
                AnalyticsPageView(
                    occurred_at=YESTERDAY,
                    day=YESTERDAY.date(),
                    path="/shop/calm-guide" if i < 10 else "/",
                    page_type="product" if i < 10 else "home",
                    source="direct",
                    visitor_hash=f"{i:016d}",
                )
            )
        db.session.commit()
    conv = _report(api)["conversion"]
    assert conv["available"] and conv["page_views"] == 40 and conv["orders"] == 4
    assert conv["orders_per_1000_page_views"] == 100.0
    guide = next(p for p in conv["product_pages"] if p["product_id"] == ids["guide"])
    assert (guide["product_page_views"], guide["units_per_100_views"]) == (10, 30.0)
    assert conv["purchase_conversion"]["available"] is False
    assert _report(api, mode="test")["conversion"]["available"] is False


def test_access_is_financial_and_aggregate_only(shop, as_role, client):
    assert client.get(URL).status_code == 401
    support = as_role("customer_support")
    for api in (as_role("analyst"), as_role("marketing_manager"), support):
        assert api.get(URL).status_code == 403
    finance = as_role("finance_manager")
    data = _report(finance)
    text = str(data)
    for private in ("buyer@example.com", "Buyer Person", "TPA-"):
        assert private not in text  # no order-level or customer data
    assert support.get(f"{URL}/export").status_code == 403


def test_csv_export_matches_the_report_and_is_audited(shop, as_role):
    app, _ids = shop
    finance = as_role("finance_manager")
    res = finance.get(f"{URL}/export", query_string={"range": "30d"})
    assert res.status_code == 200 and res.mimetype == "text/csv"
    rows = list(csv.reader(io.StringIO(res.get_data(as_text=True))))
    header = rows.index(
        ["currency", "verified_sales", "orders", "gross", "refunds", "net", "average_order_value"]
    )
    usd = next(r for r in rows[header + 1 :] if r and r[0] == "USD")
    assert usd[3:6] == ["91.00", "49.00", "42.00"]
    assert "buyer@example.com" not in res.get_data(as_text=True)
    from app.models import AuditLog

    with app.app_context():
        assert db.session.scalar(
            select(AuditLog.id).where(AuditLog.action == "finance.commerce_analytics_exported")
        )
