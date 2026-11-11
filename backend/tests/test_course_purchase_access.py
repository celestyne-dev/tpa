"""Opening a course you bought while signed in, before confirming your email.

The exception is narrow: only premium courses backed by the customer's own paid,
non-guest order open before the email is confirmed. Payment must be verified by
Paystack first, other customers never get in, refunds end access, and free courses,
staff grants, memberships and guest purchases still need a confirmed email.
"""

# ruff: noqa: F811 - the shared ``premium`` fixture is imported from its module

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.extensions import db
from app.models import CourseEnrollment, Customer, Entitlement, Order, Product, User

from .conftest import register_customer
from .test_commerce_checkout import _checkout, _send_webhook
from .test_courses_learning import LEARN, _pay, premium  # noqa: F401

VERIFY_REQUIRED = "email_verification_required"


def _lesson_url(premium):
    return f"{LEARN}/resilience-course/lessons/{premium['lesson']['slug']}"


def _code(res):
    return (res.get_json().get("error") or {}).get("code")


def _customer_id(app, email):
    with app.app_context():
        return db.session.scalar(db.select(Customer.id).where(Customer.email == email))


def _enrollments(app):
    with app.app_context():
        return [
            (e.customer_id, e.source) for e in db.session.scalars(db.select(CourseEnrollment)).all()
        ]


@pytest.mark.parametrize("verified", [True, False], ids=["verified", "unverified"])
def test_bought_course_opens_after_confirmed_payment(seeded, premium, client, verified):
    email = "confirmed@example.com" if verified else "new@example.com"
    buyer = register_customer(seeded, email, verify=verified)
    # Not bought yet: no access (unverified accounts are told to confirm their email).
    before = buyer.get(_lesson_url(premium))
    assert before.status_code == 403
    assert _code(before) == ("not_enrolled" if verified else VERIFY_REQUIRED)
    status = buyer.get(f"{LEARN}/resilience-course/status").get_json()["data"]
    assert status["enrolled"] is False and status["can_open"] is verified

    _pay(client, premium, buyer)
    assert _enrollments(seeded) == [(_customer_id(seeded, email), "purchase")]
    lesson = buyer.get(_lesson_url(premium))
    assert lesson.status_code == 200, lesson.get_json()
    assert buyer.get(f"{LEARN}/resilience-course").status_code == 200
    status = buyer.get(f"{LEARN}/resilience-course/status").get_json()["data"]
    assert status["enrolled"] and status["access"] == "active" and status["can_open"] is True
    mine = buyer.get(LEARN).get_json()["data"]
    assert mine["verified"] is verified
    assert [e["course"]["slug"] for e in mine["enrollments"]] == ["resilience-course"]
    # Progress is saved for the buyer.
    done = buyer.post(f"{_lesson_url(premium)}/complete", {})
    assert done.status_code == 200, done.get_json()
    with seeded.app_context():
        customer = db.session.get(Customer, _customer_id(seeded, email))
        assert (customer.email_verified_at is not None) is verified  # buying doesn't verify


def test_unpaid_and_failed_payments_never_open_the_course(seeded, premium, client):
    buyer = register_customer(seeded, "new@example.com", verify=False)
    res = _checkout(buyer, [premium["public_id"]])
    order = res.get_json()["data"]["order"]
    # Awaiting payment, and the browser coming back from Paystack, grant nothing.
    pending = buyer.post(f"/api/v1/checkout/orders/{order['id']}/verify").get_json()["data"]
    assert pending["order"]["status"] == "awaiting_payment"
    assert _code(buyer.get(_lesson_url(premium))) == VERIFY_REQUIRED
    # A failed charge grants nothing either.
    premium["paystack"].pay(order["payment"]["reference"], status="failed")
    failed = buyer.post(f"/api/v1/checkout/orders/{order['id']}/verify").get_json()["data"]
    assert failed["order"]["status"] == "failed"
    assert _code(buyer.get(_lesson_url(premium))) == VERIFY_REQUIRED
    assert buyer.get(LEARN).get_json()["data"]["enrollments"] == []
    assert _enrollments(seeded) == []
    with seeded.app_context():
        assert db.session.scalar(db.select(db.func.count(Entitlement.id))) == 0


def test_wrong_amount_never_opens_the_course(seeded, premium, client):
    buyer = register_customer(seeded, "new@example.com", verify=False)
    order = _checkout(buyer, [premium["public_id"]]).get_json()["data"]["order"]
    tx = premium["paystack"].pay(order["payment"]["reference"], amount=100)
    tx["paid_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    res = _send_webhook(client, premium["paystack"], "charge.success", tx)
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "rejected"
    assert _code(buyer.get(_lesson_url(premium))) == VERIFY_REQUIRED
    assert _enrollments(seeded) == []


def test_other_customers_cannot_open_someone_elses_course(seeded, premium, client):
    buyer = register_customer(seeded, "new@example.com", verify=False)
    _pay(client, premium, buyer)
    assert buyer.get(_lesson_url(premium)).status_code == 200
    for email, verified in (("other@example.com", False), ("reader@example.com", True)):
        other = register_customer(seeded, email, verify=verified)
        res = other.get(_lesson_url(premium))
        assert res.status_code == 403
        assert _code(res) == ("not_enrolled" if verified else VERIFY_REQUIRED)
        assert other.get(LEARN).get_json()["data"]["enrollments"] == []
        status = other.get(f"{LEARN}/resilience-course/status").get_json()["data"]
        assert status["enrolled"] is False
        assert other.post(f"{_lesson_url(premium)}/complete", {}).status_code == 403
    assert client.get(_lesson_url(premium)).status_code == 401  # signed out
    assert [cid for cid, _ in _enrollments(seeded)] == [_customer_id(seeded, "new@example.com")]


def test_refund_ends_an_unverified_buyers_access(seeded, premium, client):
    from app.services.commerce import entitlements as ent_service

    buyer = register_customer(seeded, "new@example.com", verify=False)
    _pay(client, premium, buyer)
    assert buyer.get(_lesson_url(premium)).status_code == 200
    with seeded.app_context():
        ent_service.revoke(db.session.scalar(db.select(Entitlement)), "Refunded", None)
        db.session.commit()
    res = buyer.get(_lesson_url(premium))
    assert res.status_code == 403 and _code(res) == VERIFY_REQUIRED
    assert buyer.get(LEARN).get_json()["data"]["enrollments"] == []


def test_staff_grants_still_need_a_confirmed_email(seeded, premium):
    from app.services.commerce import entitlements as ent_service

    learner = register_customer(seeded, "new@example.com", verify=False)
    with seeded.app_context():
        customer = db.session.get(Customer, _customer_id(seeded, "new@example.com"))
        product = db.session.get(Product, premium["product"]["id"])
        actor = db.session.scalar(db.select(User))
        ent_service.grant_manual(customer, product, "Gift from the team", actor)
        db.session.commit()
    res = learner.get(_lesson_url(premium))
    assert res.status_code == 403 and _code(res) == VERIFY_REQUIRED
    assert learner.get(LEARN).get_json()["data"] == {"verified": False, "enrollments": []}
    status = learner.get(f"{LEARN}/resilience-course/status").get_json()["data"]
    assert status["can_open"] is False


def test_guest_purchase_still_needs_a_confirmed_email(seeded, premium, client):
    seeded.config["PAYMENTS_TEST_CHECKOUT_PUBLIC"] = True
    from .test_commerce_checkout import _key

    res = client.post(
        "/api/v1/checkout/guest",
        json={
            "email": "buyer@example.com",
            "items": [{"product_id": premium["public_id"]}],
            "currency": "USD",
            "expected_total_minor": 4900,
            "idempotency_key": _key(),
            "accept_terms": True,
            "age_confirmed": True,
        },
    )
    order = res.get_json()["data"]["order"]
    tx = premium["paystack"].pay(order["payment"]["reference"])
    tx["paid_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    assert _send_webhook(client, premium["paystack"], "charge.success", tx).status_code == 200
    claimant = register_customer(seeded, "buyer@example.com", verify=False)
    assert _code(claimant.get(_lesson_url(premium))) == VERIFY_REQUIRED
    with seeded.app_context():
        assert db.session.scalar(db.select(Order.is_guest)) is True
    assert _enrollments(seeded) == []


def test_free_courses_still_need_a_confirmed_email(seeded, as_role):
    from .test_courses_admin import COURSES, add_lesson, add_module, create_course

    editor = as_role("editor")
    course = create_course(editor, "Calm Basics")
    module = add_module(editor, course["id"])
    add_lesson(editor, course["id"], module["id"], "Notice")
    editor.post(f"{COURSES}/{course['id']}/publish", {})
    newbie = register_customer(seeded, "new@example.com", verify=False)
    res = newbie.post(f"{LEARN}/calm-basics/enroll")
    assert res.status_code == 403 and _code(res) == VERIFY_REQUIRED
    assert newbie.get(f"{LEARN}/calm-basics/status").get_json()["data"]["can_open"] is False
