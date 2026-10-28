"""Batch 10.1: membership plans, immutable prices, included products, permissions,
public plan APIs and the cart exclusion. No billing exists yet."""

from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models import Entitlement, MembershipPlanPrice, Product

from .test_commerce_catalogue import PRODUCTS, _create, _sellable

PLANS = "/api/v1/admin/membership-plans"
PUBLIC = "/api/v1/memberships"


def _eligible(api, title, **extra):
    product = _sellable(api, title)
    res = api.patch(f"{PRODUCTS}/{product['id']}", {"membership_eligible": True, **extra})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _plan(api, **body):
    res = api.post(PLANS, {"name": "Positive Circle", **body})
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def _ready_plan(api, product):
    plan = _plan(
        api,
        tagline="Everything you need for calmer days",
        description="Members read every premium guide.\n\nNew resources monthly.",
        benefits=["All premium guides", "Member-only workbooks"],
    )
    plan = _price(api, plan, "month", "9.99")
    plan = _price(api, plan, "year", "99.00")
    res = api.put(
        f"{PLANS}/{plan['id']}/access",
        {"product_ids": [product["public_id"]], "lock_version": plan["lock_version"]},
    )
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


def _price(api, plan, interval, amount):
    res = api.post(
        f"{PLANS}/{plan['id']}/prices",
        {"interval": interval, "amount": amount, "lock_version": plan["lock_version"]},
    )
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def _publish(api, plan, status="published"):
    return api.post(
        f"{PLANS}/{plan['id']}/status", {"status": status, "lock_version": plan["lock_version"]}
    )


def test_plan_lifecycle_publication_and_public_api(seeded, as_role, client):
    admin = as_role("administrator")
    guide = _eligible(admin, "Calm Guide")
    assert client.get(PUBLIC).get_json()["data"]["plans"] == []

    draft = _plan(admin, name="Empty Draft")
    assert draft["status"] == "draft" and draft["slug"] == "empty-draft"
    res = _publish(admin, draft)
    assert res.status_code == 400
    assert len(res.get_json()["error"]["details"]["readiness"]) == 4
    # Drafts never leak.
    assert client.get(PUBLIC).get_json()["data"]["plans"] == []
    assert client.get(f"{PUBLIC}/positive-circle").status_code == 404

    plan = _ready_plan(admin, guide)
    assert plan["readiness"] == [] and plan["prices"]["month"]["price"]["formatted"] == "USD 9.99"
    published = _publish(admin, plan)
    assert published.status_code == 200, published.get_json()
    plan = published.get_json()["data"]
    assert plan["status"] == "published"
    assert all(p["shown_at"] for p in plan["price_history"])

    data = client.get(PUBLIC).get_json()["data"]
    assert data["billing"] == {
        "available": False,
        "status": "coming_soon",
        "message": "Paid memberships are coming soon. No payments are being taken yet.",
    }
    [public] = data["plans"]
    assert public["benefits"] == ["All premium guides", "Member-only workbooks"]
    assert [(p["interval"], p["price"]["amount_minor"]) for p in public["prices"]] == [
        ("month", 999),
        ("year", 9900),
    ]
    assert [i["title"] for i in public["included"]] == ["Calm Guide"]
    assert "product_id" not in public["included"][0] and "status" not in public["included"][0]
    assert client.get(f"{PUBLIC}/positive-circle").get_json()["data"]["plan"]["name"] == (
        "Positive Circle"
    )

    # Published plans keep their address; one paid tier at a time.
    res = admin.patch(
        f"{PLANS}/{plan['id']}", {"slug": "new", "lock_version": plan["lock_version"]}
    )
    assert res.status_code == 400
    second = _plan(admin, name="Second Tier", description="x", benefits=["y"])
    second = _price(admin, second, "month", "19.00")
    second = admin.put(
        f"{PLANS}/{second['id']}/access",
        {"product_ids": [guide["public_id"]], "lock_version": second["lock_version"]},
    ).get_json()["data"]
    assert second["tier_rank"] == 3
    assert _publish(admin, second).status_code == 409

    # Archive hides the plan and freezes it.
    archived = _publish(admin, plan, "archived")
    assert archived.status_code == 200
    plan = archived.get_json()["data"]
    assert client.get(PUBLIC).get_json()["data"]["plans"] == []
    res = admin.patch(f"{PLANS}/{plan['id']}", {"name": "X", "lock_version": plan["lock_version"]})
    assert res.status_code == 409


def test_prices_are_immutable_server_side_and_usd_only(seeded, as_role):
    admin = as_role("administrator")
    plan = _plan(admin)
    pid = plan["id"]
    for body, field in (
        ({"interval": "week", "amount": "5"}, "interval"),
        ({"interval": "month", "amount": "abc"}, "amount"),
        ({"interval": "month", "amount": "9.999"}, "amount"),
        ({"interval": "month", "amount": "0.50"}, "amount"),
        ({"interval": "month", "amount": "9.99", "currency": "KES"}, "currency"),
        ({"interval": "month", "amount_minor": "999"}, "amount"),
    ):
        res = admin.post(f"{PLANS}/{pid}/prices", {**body, "lock_version": plan["lock_version"]})
        assert res.status_code == 400 and field in res.get_json()["error"]["details"], body
    res = admin.post(
        f"{PLANS}/{pid}/prices",
        {"interval": "month", "amount": "9.99", "price_id": "x", "lock_version": 1},
    )
    assert res.status_code == 400  # unknown fields (no client-chosen ids or edits)

    plan = _price(admin, plan, "month", "9.99")
    first_id = plan["prices"]["month"]["id"]
    same = admin.post(
        f"{PLANS}/{pid}/prices",
        {"interval": "month", "amount": "9.99", "lock_version": plan["lock_version"]},
    )
    assert same.status_code == 409
    plan = _price(admin, plan, "month", "12.00")
    assert plan["prices"]["month"]["price"]["amount_minor"] == 1200
    # A never-public price that is replaced stays as retired history (not edited).
    statuses = {p["id"]: p["status"] for p in plan["price_history"]}
    assert statuses[first_id] == "retired" and len(statuses) == 2
    with seeded.app_context():
        rows = db.session.scalars(
            select(MembershipPlanPrice).order_by(MembershipPlanPrice.id)
        ).all()
        assert [(r.amount_minor, r.status) for r in rows] == [(999, "retired"), (1200, "active")]

    # An unshown price can be deleted; a shown one only retired; retired history stays.
    current = plan["prices"]["month"]["id"]
    res = admin.post(
        f"{PLANS}/{pid}/prices/{current}/remove", {"lock_version": plan["lock_version"]}
    )
    assert res.status_code == 200
    plan = res.get_json()["data"]
    assert plan["prices"] == {} and len(plan["price_history"]) == 1
    res = admin.post(
        f"{PLANS}/{pid}/prices/{first_id}/remove", {"lock_version": plan["lock_version"]}
    )
    assert res.status_code == 200  # never shown: removed entirely


def test_published_plan_keeps_a_price_and_shown_prices_are_retired_not_deleted(seeded, as_role):
    admin = as_role("administrator")
    guide = _eligible(admin, "Calm Guide")
    plan = _ready_plan(admin, guide)
    plan = _publish(admin, plan).get_json()["data"]
    month = plan["prices"]["month"]["id"]
    year = plan["prices"]["year"]["id"]
    res = admin.post(
        f"{PLANS}/{plan['id']}/prices/{year}/remove", {"lock_version": plan["lock_version"]}
    )
    assert res.status_code == 200
    plan = res.get_json()["data"]
    retired = next(p for p in plan["price_history"] if p["id"] == year)
    assert retired["status"] == "retired"  # shown publicly: kept for the record
    res = admin.post(
        f"{PLANS}/{plan['id']}/prices/{month}/remove", {"lock_version": plan["lock_version"]}
    )
    assert res.status_code == 409  # the last price of a published plan
    # Replacing a published price marks the new one as shown immediately.
    plan = _price(admin, plan, "month", "11.00")
    assert plan["prices"]["month"]["shown_at"]


def test_included_products_follow_membership_eligibility(seeded, as_role, client):
    admin = as_role("administrator")
    eligible = _eligible(admin, "Calm Guide")
    not_flagged = _sellable(admin, "Not Included")
    course = _create(admin, "Calm Course", product_type="course")
    admin.patch(f"{PRODUCTS}/{course['id']}", {"membership_eligible": True})
    plan = _plan(admin)

    options = admin.get("/api/v1/admin/membership-eligible-products").get_json()["data"]
    titles = {o["title"]: o for o in options}
    assert "Calm Guide" in titles and "Not Included" not in titles
    assert titles["Calm Course"]["kind"] == "course"

    res = admin.put(
        f"{PLANS}/{plan['id']}/access",
        {"product_ids": [not_flagged["public_id"]], "lock_version": plan["lock_version"]},
    )
    assert res.status_code == 400
    assert "Not marked as included" in res.get_json()["error"]["details"]["product_ids"][0]
    res = admin.put(
        f"{PLANS}/{plan['id']}/access",
        {"product_ids": ["nope"], "lock_version": plan["lock_version"]},
    )
    assert res.status_code == 400

    res = admin.put(
        f"{PLANS}/{plan['id']}/access",
        {
            "product_ids": [eligible["public_id"], course["public_id"]],
            "lock_version": plan["lock_version"],
        },
    )
    assert res.status_code == 200
    plan = res.get_json()["data"]
    assert {i["title"] for i in plan["included"]} == {"Calm Guide", "Calm Course"}

    # Unflagging a product afterwards is reported, and it is never shown publicly.
    admin.patch(f"{PRODUCTS}/{eligible['id']}", {"membership_eligible": False})
    detail = admin.get(f"{PLANS}/{plan['id']}").get_json()["data"]
    flagged = next(i for i in detail["included"] if i["title"] == "Calm Guide")
    assert flagged["problem"] and "Include at least one published" in detail["readiness"][-1]

    # Nothing is granted: memberships don't create entitlements in this batch.
    with seeded.app_context():
        assert (
            db.session.scalar(select(Entitlement).where(Entitlement.source == "membership")) is None
        )


def test_concurrent_edits_are_refused(seeded, as_role):
    admin = as_role("administrator")
    plan = _plan(admin)
    ok = admin.patch(
        f"{PLANS}/{plan['id']}", {"tagline": "A", "lock_version": plan["lock_version"]}
    )
    assert ok.status_code == 200
    stale = admin.patch(
        f"{PLANS}/{plan['id']}", {"tagline": "B", "lock_version": plan["lock_version"]}
    )
    assert stale.status_code == 409 and stale.get_json()["error"]["code"] == "edit_conflict"
    missing = admin.patch(f"{PLANS}/{plan['id']}", {"tagline": "C"})
    assert missing.status_code == 400
    res = admin.post(PLANS, {"name": "Dup", "slug": "positive-circle"})
    assert res.status_code == 409
    res = admin.post(PLANS, {"name": "Html", "description": "<script>x</script>"})
    assert res.status_code == 400
    res = admin.patch(
        f"{PLANS}/{plan['id']}", {"benefits": ["x"] * 13, "lock_version": plan["lock_version"] + 1}
    )
    assert res.status_code == 400


def test_permissions_are_enforced_by_the_api(seeded, as_role, client):
    admin = as_role("administrator")
    guide = _eligible(admin, "Calm Guide")
    plan = _ready_plan(admin, guide)

    viewer = as_role("customer_support")
    assert viewer.get(PLANS).status_code == 200
    assert viewer.get(f"{PLANS}/{plan['id']}").status_code == 200
    assert viewer.post(PLANS, {"name": "No"}).status_code == 403
    assert (
        viewer.patch(f"{PLANS}/{plan['id']}", {"name": "No", "lock_version": 1}).status_code == 403
    )

    manager = as_role("product_manager")
    res = manager.patch(
        f"{PLANS}/{plan['id']}", {"tagline": "Edited", "lock_version": plan["lock_version"]}
    )
    assert res.status_code == 200
    plan = res.get_json()["data"]
    assert _publish(manager, plan).status_code == 403  # no memberships.publish

    for role in ("analyst", "content_editor"):
        assert as_role(role).get(PLANS).status_code == 403
    assert client.get(PLANS).status_code == 401


def test_membership_products_are_never_sold_through_the_cart(seeded, as_role, client):
    admin = as_role("administrator")
    product = _sellable(admin, "Sneaky Membership")
    with seeded.app_context():
        row = db.session.scalar(select(Product).where(Product.public_id == product["public_id"]))
        row.product_type = "membership"
        db.session.commit()
    quote = client.post(
        "/api/v1/cart/quote", json={"items": [product["public_id"]], "currency": "USD"}
    ).get_json()["data"]
    assert quote["can_checkout"] is False
    assert quote["lines"][0]["problem"] == "Memberships are joined from the membership page."
