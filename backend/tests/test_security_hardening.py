"""Batch 12.1: release security hardening regressions."""

from __future__ import annotations

import csv
import io
import secrets
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.config import ProductionConfig
from app.extensions import db
from app.models import Order, OrderItem, Subscriber
from app.utils.csv_safe import SafeWriter, safe_cell

from .test_commerce_analytics import shop  # noqa: F401

ADMIN = "/api/v1/admin"
FORMULA = "=HYPERLINK(evil)"
PAYLOADS = ("=1+1", "+1+A1", "-2+A1", "@SUM(A1)", "\tx", "\rx")


def _rows(res):
    assert res.status_code == 200, res.get_data(as_text=True)
    return list(csv.reader(io.StringIO(res.get_data(as_text=True))))


def _no_raw_formula(rows):
    for row in rows:
        for cell in row:
            assert safe_cell(cell) == cell, row  # nothing a spreadsheet would evaluate


# ---- shared CSV rule ------------------------------------------------------------------


def test_safe_cell_neutralises_formulas_but_keeps_numbers_and_empty_cells():
    for bad in PAYLOADS:
        assert safe_cell(bad) == "'" + bad
    for kept in ("", "Calm Guide", "-3.00", "+254", "12", 5, None, -7):
        assert safe_cell(kept) == kept
    writer = SafeWriter()
    writer.writerow(["=cmd", "", "-3.00", "a@b"])
    assert writer.value() == "'=cmd,,-3.00,a@b\r\n"


# ---- finance and order exports --------------------------------------------------------


def test_revenue_export_neutralises_product_titles(shop, as_role):  # noqa: F811
    app, ids = shop
    with app.app_context():
        for item in db.session.scalars(
            select(OrderItem).where(OrderItem.product_id == ids["guide"])
        ):
            item.title = FORMULA
        db.session.commit()
    rows = _rows(as_role("finance_manager").get(f"{ADMIN}/reports/revenue/export"))
    titles = [r[0] for r in rows if len(r) == 4 and r[1] == "USD"]
    assert "'" + FORMULA in titles and FORMULA not in titles
    _no_raw_formula(rows)


def test_orders_export_neutralises_emails_and_titles(shop, as_role):  # noqa: F811
    app, ids = shop
    with app.app_context():
        for item in db.session.scalars(select(OrderItem)):
            item.title = "@SUM(A1)"
        for order in db.session.scalars(select(Order)):
            order.email = "=cmd@example.com"
        db.session.commit()
    rows = _rows(as_role("super_admin").get(f"{ADMIN}/orders/export"))
    body = rows[1:]
    assert body and all(r[5] == "'=cmd@example.com" for r in body)
    assert all(r[9].startswith("'@SUM(A1)") for r in body)
    assert all(r[2] == "" for r in body if r[3] in ("awaiting_payment", "failed"))
    _no_raw_formula(rows)


# ---- redirect and subscriber exports --------------------------------------------------


def test_redirect_export_neutralises_staff_notes(seeded, as_role):
    seo = as_role("seo_manager")
    res = seo.post(
        f"{ADMIN}/redirects",
        {"source_path": "/old", "destination": "/articles/new", "note": "=IMPORTXML(x)"},
    )
    assert res.status_code == 201, res.get_json()
    rows = _rows(seo.get(f"{ADMIN}/redirects/export"))
    [row] = [r for r in rows if r[0] == "/old"]
    assert row[4] == "'=IMPORTXML(x)" and row[2] == "301"


def test_subscriber_export_guard_covers_tab_cr_and_keeps_empty_cells(seeded, as_role):
    with seeded.app_context():
        db.session.add(
            Subscriber(
                public_id=secrets.token_hex(8),
                email="formula@example.com",
                first_name="\t=cmd",
                status="subscribed",
                source="footer",
                consent_text="\r=cmd",
                consent_version="",
                created_at=datetime.now(UTC),
            )
        )
        db.session.commit()
    rows = _rows(as_role("newsletter_manager").get(f"{ADMIN}/subscribers/export"))
    header, *body = rows
    [row] = [r for r in body if r[0] == "formula@example.com"]
    cell = dict(zip(header, row, strict=True))
    assert cell["first_name"] == "'\t=cmd" and cell["consent_text"] == "'\r=cmd"
    assert cell["consent_version"] == "" and cell["unsubscribed_at"] == ""  # not "'"


def test_partnership_export_uses_safe_writer(monkeypatch):
    from app.services.partnerships import reports

    monkeypatch.setattr(
        reports, "report", lambda args: {"by_currency": [{"currency": "=X"}], "filters": {}}
    )
    monkeypatch.setattr(reports.audit_service, "record", lambda *a, **k: None)
    assert reports.export_csv({}, None) == "currency\r\n'=X\r\n"


# ---- production payment configuration -------------------------------------------------


def _problems(monkeypatch, **env) -> str:
    for key in ("PAYSTACK_SECRET_KEY", "PAYSTACK_PUBLIC_KEY", "MEMBERSHIP_BILLING_MODE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError) as err:  # other settings are missing in tests
        monkeypatch.delenv("SECRET_KEY", raising=False)
        ProductionConfig.validate()
    return str(err.value)


@pytest.mark.parametrize(
    ("secret", "public", "rejected"),
    [
        ("sk_live_abc", "pk_test_abc", True),
        ("sk_test_abc", "pk_live_abc", True),
        ("sk_test_abc", "sk_test_abc", True),
        ("sk_test_abc", "pk_test_abc", False),
        ("sk_live_abc", "pk_live_abc", False),
    ],
)
def test_production_rejects_mismatched_paystack_keys(monkeypatch, secret, public, rejected):
    text = _problems(monkeypatch, PAYSTACK_SECRET_KEY=secret, PAYSTACK_PUBLIC_KEY=public)
    assert ("PAYSTACK_PUBLIC_KEY" in text) is rejected


@pytest.mark.parametrize(
    ("mode", "rejected"), [("live", True), ("tset", True), ("disabled", False), ("TEST", False)]
)
def test_production_membership_billing_never_live(monkeypatch, mode, rejected):
    text = _problems(monkeypatch, MEMBERSHIP_BILLING_MODE=mode)
    assert ("MEMBERSHIP_BILLING_MODE" in text) is rejected


def test_production_still_rejects_public_test_checkout(monkeypatch):
    text = _problems(monkeypatch, PAYMENTS_TEST_CHECKOUT_PUBLIC="true")
    assert "PAYMENTS_TEST_CHECKOUT_PUBLIC" in text
