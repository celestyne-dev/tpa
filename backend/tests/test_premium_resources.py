"""Batch 08: premium resources on top of commerce products — resource types, access rules
(download limits, access periods), related resources, version management, the premium
file library, delivery through entitlements (paid, guest, free, future memberships and
courses), download activity and admin permissions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.extensions import db
from app.models import Customer, DownloadEvent, Entitlement, Product
from app.services.commerce import access

from .conftest import minimal_pdf, register_customer
from .test_commerce_catalogue import PRODUCTS, _create, _sellable, _upload
from .test_commerce_checkout import _key, _library_file, _paid_order, shop  # noqa: F401
from .test_vps_storage import ooxml

FILES = "/api/v1/admin/premium-files"


def _entitlement(app, product_id=None):
    with app.app_context():
        stmt = db.select(Entitlement)
        if product_id:
            stmt = stmt.where(Entitlement.product_id == product_id)
        return db.session.scalars(stmt.order_by(Entitlement.id)).all()


def _expire(app, entitlement_id):
    with app.app_context():
        ent = db.session.get(Entitlement, entitlement_id)
        ent.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()


# ---- resource CMS -------------------------------------------------------------------------


def test_written_resource_types_access_rules_and_permissions(seeded, as_role, client):
    api = as_role("product_manager")
    options = api.get(f"{PRODUCTS}/options").get_json()["data"]
    types = {t["value"] for t in options["types"]}
    assert {"ebook", "workbook", "planner", "worksheet", "guide", "template", "checklist"} <= types
    assert "learning_pack" in types
    product = _create(api, "Morning checklist", product_type="checklist")
    res = api.patch(
        f"{PRODUCTS}/{product['id']}",
        {"download_limit": 5, "access_days": 365, "membership_eligible": True},
    )
    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    assert (data["download_limit"], data["access_days"], data["membership_eligible"]) == (
        5,
        365,
        True,
    )
    assert data["effective_download_limit"] == 5
    for bad in ({"download_limit": 0}, {"access_days": -1}, {"access_days": "soon"}):
        assert api.patch(f"{PRODUCTS}/{product['id']}", bad).status_code == 400
    # Access rules are commercial terms: roles without price management can't change them.
    viewer = as_role("affiliate_manager", email="aff@example.org")
    res = viewer.patch(f"{PRODUCTS}/{product['id']}", {"access_days": 30})
    assert res.status_code == 403
    listed = api.get(f"{PRODUCTS}?group=resources&access=premium").get_json()["data"]
    assert product["id"] in [p["id"] for p in listed]
    entry = next(p for p in listed if p["id"] == product["id"])
    assert entry["access_days"] == 365 and entry["membership_eligible"] is True


def test_related_resources_follow_publishing(seeded, as_role, client):
    api = as_role("product_manager")
    main = _sellable(api, "Main workbook")
    first = _sellable(api, "First related")
    second = _sellable(api, "Second related")
    draft = _create(api, "Draft resource", product_type="guide")
    archived = _create(api, "Archived resource", product_type="guide")
    api.post(f"{PRODUCTS}/{archived['id']}/archive")
    url = f"{PRODUCTS}/{main['id']}"
    assert api.patch(url, {"related_ids": [main["id"]]}).status_code == 400  # not itself
    assert api.patch(url, {"related_ids": [archived["id"]]}).status_code == 400
    assert api.patch(url, {"related_ids": [999999]}).status_code == 400
    res = api.patch(url, {"related_ids": [second["id"], draft["id"], first["id"]]})
    assert res.status_code == 200
    assert res.get_json()["data"]["related_ids"] == [second["id"], draft["id"], first["id"]]
    slug = main["published_slug"]
    public = client.get(f"/api/v1/shop/products/{slug}").get_json()["data"]
    # Not published yet: the public snapshot has no chosen relations, so the editor's order
    # isn't applied (automatic suggestions follow product order instead).
    assert [r["title"] for r in public["related"]][:2] == ["First related", "Second related"]
    assert api.get(url).get_json()["data"]["has_unpublished_changes"] is True
    assert api.post(f"{url}/publish").status_code == 200
    public = client.get(f"/api/v1/shop/products/{slug}").get_json()["data"]
    titles = [r["title"] for r in public["related"]]
    assert titles[:2] == ["Second related", "First related"]  # chosen order, drafts left out
    assert "Draft resource" not in titles
    assert public["access"] == {"lifetime": True, "days": None, "download_limit": None}


def test_public_resource_listing_filters(seeded, as_role, client):
    api = as_role("product_manager")
    _sellable(api, "Paid workbook")
    free = _create(
        api, "Free checklist", product_type="checklist", short_description="A free checklist."
    )
    assert _upload(api, free["id"]).status_code == 201
    api.patch(f"{PRODUCTS}/{free['id']}", {"pricing_model": "free"})
    api.patch(f"{PRODUCTS}/{free['id']}", {"sales_status": "on_sale"})
    assert api.post(f"{PRODUCTS}/{free['id']}/publish").status_code == 200
    res = client.get("/api/v1/shop/products?group=resources&access=free").get_json()
    assert [p["title"] for p in res["data"]] == ["Free checklist"]
    types = {t["key"]: t["count"] for t in res["meta"]["types"]}
    assert types["checklist"] == 1 and types["workbook"] >= 1  # options from all resources
    premium = client.get("/api/v1/shop/products?group=resources&access=premium").get_json()
    assert "Free checklist" not in [p["title"] for p in premium["data"]]
    assert client.get("/api/v1/shop/products?access=gold").status_code == 400


# ---- access rules at purchase time --------------------------------------------------------


def test_access_period_and_download_limit_apply_to_purchases(shop, client):  # noqa: F811
    admin, pid = shop["admin"], shop["product"]["id"]
    res = admin.patch(f"{PRODUCTS}/{pid}", {"access_days": 30, "download_limit": 2})
    assert res.status_code == 200, res.get_json()
    _paid_order(shop, client)
    ent = _entitlement(shop["app"])[0]
    assert ent.download_limit == 2
    assert ent.expires_at is not None
    left = ent.expires_at - datetime.now(UTC)
    assert timedelta(days=29, hours=23) < left <= timedelta(days=30)
    shopper = shop["shopper"]
    item, version = _library_file(shopper)
    assert item["expires_at"] and item["status"] == "active"
    url = f"/api/v1/account/library/{item['id']}/downloads"
    assert shopper.post(url, {"version_id": version["version_id"]}).status_code == 200
    link = shopper.post(url, {"version_id": version["version_id"]}).get_json()["data"]["url"]
    third = shopper.post(url, {"version_id": version["version_id"]})
    assert third.status_code == 403  # the resource's own limit, not the store default
    # When the access period ends, new and already issued links stop working.
    _expire(shop["app"], ent.id)
    assert shopper.get(link).status_code == 403
    library = shopper.get("/api/v1/account/library").get_json()["data"]
    assert library[0]["status"] == "expired" and library[0]["files"] == []
    with shop["app"].app_context():
        reasons = {
            e.reason for e in db.session.scalars(db.select(DownloadEvent)) if e.status == "denied"
        }
    assert "entitlement_expired" in reasons
    # An expired purchase doesn't count as owned: the customer can buy it again.
    quote = shopper.post(
        "/api/v1/cart/quote", {"items": [{"product_id": shop["public_id"]}], "currency": "USD"}
    ).get_json()["data"]
    assert quote["can_checkout"] is True


def test_lifetime_access_is_the_default(shop, client):  # noqa: F811
    _paid_order(shop, client)
    ent = _entitlement(shop["app"])[0]
    assert ent.expires_at is None and ent.download_limit is None


def test_free_resources_with_an_access_period_can_be_claimed_again(seeded, as_role, client):
    api = as_role("product_manager")
    free = _create(
        api, "Free worksheet", product_type="worksheet", short_description="A free worksheet."
    )
    assert _upload(api, free["id"]).status_code == 201
    api.patch(f"{PRODUCTS}/{free['id']}", {"pricing_model": "free", "access_days": 7})
    api.patch(f"{PRODUCTS}/{free['id']}", {"sales_status": "on_sale"})
    published = api.post(f"{PRODUCTS}/{free['id']}/publish").get_json()["data"]
    shopper = register_customer(seeded, "free@example.com")
    claim = shopper.post("/api/v1/account/free-claims", {"product_id": published["public_id"]})
    assert claim.status_code == 201, claim.get_json()
    ent = _entitlement(seeded, free["id"])[0]
    assert ent.expires_at is not None
    _expire(seeded, ent.id)
    assert shopper.get("/api/v1/account/library").get_json()["data"][0]["status"] == "expired"
    again = shopper.post("/api/v1/account/free-claims", {"product_id": published["public_id"]})
    assert again.status_code == 200
    assert shopper.get("/api/v1/account/library").get_json()["data"][0]["status"] == "active"


# ---- versions and the premium file library ------------------------------------------------


def test_version_replacement_and_safe_deletion(shop, client):  # noqa: F811
    admin, app = shop["admin"], shop["app"]
    pid = shop["product"]["id"]
    file_id = admin.get(f"{PRODUCTS}/{pid}").get_json()["data"]["files"][0]["id"]
    # An unsold draft version can be deleted.
    res = admin.upload(
        f"{PRODUCTS}/{pid}/files/{file_id}/versions", minimal_pdf(b"% v2\n"), "v2.pdf"
    )
    assert res.status_code == 201, res.get_json()
    detail = admin.get(f"{FILES}/{file_id}").get_json()["data"]
    v1, v2 = sorted(detail["versions"], key=lambda v: v["version"])
    assert v2["deletable"] is False and "current" in v2["delete_blocked_reason"]
    assert v1["deletable"] is True
    # A buyer receives v2 (the current version): it is then protected.
    _paid_order(shop, client)
    detail = admin.get(f"{FILES}/{file_id}").get_json()["data"]
    v1, v2 = sorted(detail["versions"], key=lambda v: v["version"])
    assert v2["deletable"] is False
    # Replace again: buyers get the latest and keep the version they bought.
    admin.upload(f"{PRODUCTS}/{pid}/files/{file_id}/versions", minimal_pdf(b"% v3\n"), "v3.pdf")
    item, _ = _library_file(shop["shopper"])
    kinds = {v["kind"]: v["version"] for v in item["files"][0]["versions"]}
    assert kinds == {"latest": 3, "purchased": 2}
    detail = admin.get(f"{FILES}/{file_id}").get_json()["data"]
    by_number = {v["version"]: v for v in detail["versions"]}
    assert "Buyers received" in by_number[2]["delete_blocked_reason"]
    res = admin.delete(f"{FILES}/{file_id}/versions/{by_number[2]['id']}")
    assert res.status_code == 409
    with app.app_context():
        from app.models import ProductFileVersion

        v1_key = db.session.get(ProductFileVersion, by_number[1]["id"]).storage_key
    path = Path(app.config["PRODUCT_FILES_ROOT"]) / v1_key
    assert path.is_file()
    res = admin.delete(f"{FILES}/{file_id}/versions/{by_number[1]['id']}")
    assert res.status_code == 200, res.get_json()
    assert not path.exists()
    assert [v["version"] for v in res.get_json()["data"]["versions"]] == [3, 2]
    # The file was sold: it can be archived but never deleted.
    res = admin.delete(f"{FILES}/{file_id}")
    assert res.status_code == 409 and "Archive" in res.get_json()["error"]["message"]


def test_premium_file_library_lists_usage_and_respects_permissions(shop, client, as_role):  # noqa: F811
    admin = shop["admin"]
    _paid_order(shop, client)
    item, version = _library_file(shop["shopper"])
    link = (
        shop["shopper"]
        .post(
            f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
        )
        .get_json()["data"]["url"]
    )
    assert shop["shopper"].get(link).status_code == 200
    template = _create(admin, "Budget template", product_type="template")
    assert _upload(admin, template["id"], ooxml("xlsx"), "budget.xlsx").status_code == 201
    res = admin.get(FILES).get_json()
    files = {f["product"]["title"]: f for f in res["data"]}
    sold = files["Calm Mornings Workbook"]
    assert sold["downloads"] == 1 and sold["category"] == "workbooks"
    assert sold["current_version"]["format"] == "pdf"
    assert files["Budget template"]["category"] == "templates"
    assert "storage_key" not in str(res)
    assert res["meta"]["summary"]["by_category"] == {"workbooks": 1, "templates": 1}
    only = admin.get(f"{FILES}?format=xlsx").get_json()["data"]
    assert [f["product"]["title"] for f in only] == ["Budget template"]
    # Never sold or downloaded: the whole file can be deleted.
    tid = files["Budget template"]["id"]
    assert admin.get(f"{FILES}/{tid}").get_json()["data"]["deletable"] is True
    assert admin.delete(f"{FILES}/{tid}").status_code == 200
    assert admin.get(f"{FILES}/{tid}").status_code == 404
    writer = as_role("content_writer", email="writer@example.org")
    assert writer.get(FILES).status_code == 403
    viewer = as_role("affiliate_manager", email="aff@example.org")  # products.view only
    assert viewer.get(FILES).status_code == 200
    assert viewer.delete(f"{FILES}/{sold['id']}").status_code == 403


def test_download_activity_summary(shop, client, as_role):  # noqa: F811
    _paid_order(shop, client)
    shopper = shop["shopper"]
    item, version = _library_file(shopper)
    link = shopper.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    ).get_json()["data"]["url"]
    shopper.get(link)
    client.get(link)  # no session: refused
    auditor = as_role("orders_manager", email="orders@example.org")
    summary = auditor.get("/api/v1/admin/downloads/summary?days=7").get_json()["data"]
    assert summary["served"] == 1 and summary["denied"] == 1 and summary["authorized"] == 1
    assert summary["top_resources"][0]["title"] == "Calm Mornings Workbook"
    assert summary["denial_reasons"] == [{"reason": "session_mismatch", "count": 1}]
    assert summary["daily"][-1]["served"] == 1
    pid = shop["product"]["id"]
    rows = auditor.get(f"/api/v1/admin/downloads?product_id={pid}&status=served").get_json()
    assert len(rows["data"]) == 1
    assert (
        as_role("content_writer", email="w@example.org")
        .get("/api/v1/admin/downloads/summary")
        .status_code
        == 403
    )


def test_nginx_delivery_header_points_inside_the_category_folder(shop, client):  # noqa: F811
    shop["app"].config["PRODUCT_FILES_ACCEL_REDIRECT_PREFIX"] = "/_protected_downloads"
    _paid_order(shop, client)
    shopper = shop["shopper"]
    item, version = _library_file(shopper)
    link = shopper.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    ).get_json()["data"]["url"]
    res = shopper.get(link)
    assert res.status_code == 200
    header = res.headers["X-Accel-Redirect"]
    assert header.startswith("/_protected_downloads/workbooks/") and ".." not in header
    assert res.headers["Cache-Control"] == "private, no-store"


# ---- future memberships and courses -------------------------------------------------------


def test_membership_and_course_access_use_the_same_entitlements(shop, client):  # noqa: F811
    app, admin = shop["app"], shop["admin"]
    pid = shop["product"]["id"]
    shopper = shop["shopper"]
    with app.app_context():
        customer = db.session.scalar(db.select(Customer))
        product = db.session.get(Product, pid)
        try:
            access.grant(customer, product, source="membership", reference="membership-1")
        except Exception as exc:  # not eligible yet
            assert "not included in memberships" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("ineligible resource was unlocked by a membership")
        db.session.rollback()
    admin.patch(f"{PRODUCTS}/{pid}", {"membership_eligible": True})
    later = datetime.now(UTC) + timedelta(days=30)
    with app.app_context():
        customer = db.session.scalar(db.select(Customer))
        product = db.session.get(Product, pid)
        assert access.can_download(customer, product) is False
        ent = access.grant(
            customer, product, source="membership", reference="membership-1", expires_at=later
        )
        again = access.grant(
            customer,
            product,
            source="membership",
            reference="membership-1",
            expires_at=later + timedelta(days=30),
        )
        assert again.id == ent.id  # renewal extends the same entitlement
        course = access.grant(customer, product, source="course", reference="course-7")
        db.session.commit()
        assert access.can_download(customer, product) is True
        ids = (ent.id, course.id)
    library = shopper.get("/api/v1/account/library").get_json()["data"]
    sources = sorted(i["source"] for i in library)
    assert sources == ["course", "membership"]
    item = next(i for i in library if i["source"] == "membership")
    version = item["files"][0]["versions"][0]
    res = shopper.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    )
    assert res.status_code == 200
    assert shopper.get(res.get_json()["data"]["url"]).status_code == 200
    with app.app_context():
        assert access.revoke("membership", "membership-1", "Membership ended") == 1
        assert access.revoke("course", "course-7", "Unenrolled") == 1
        db.session.commit()
        customer = db.session.scalar(db.select(Customer))
        assert access.can_download(customer, db.session.get(Product, pid)) is False
        states = {e.id: e.status for e in db.session.scalars(db.select(Entitlement))}
        assert {states[i] for i in ids} == {"revoked"}
    res = shopper.post(
        f"/api/v1/account/library/{item['id']}/downloads", {"version_id": version["version_id"]}
    )
    assert res.status_code == 403


def test_guest_purchases_of_written_resources_download(shop, client):  # noqa: F811
    from .test_guest_checkout import HEADER, _paid_guest_order

    shop["app"].config["PAYMENTS_TEST_CHECKOUT_PUBLIC"] = True
    admin, pid = shop["admin"], shop["product"]["id"]
    file_id = admin.get(f"{PRODUCTS}/{pid}").get_json()["data"]["files"][0]["id"]
    admin.upload(f"{PRODUCTS}/{pid}/files/{file_id}/versions", ooxml("docx"), "workbook-edit.docx")
    order, token = _paid_guest_order(shop, client)
    status = client.get(
        f"/api/v1/checkout/guest-orders/{order['id']}", headers={HEADER: token}
    ).get_json()["data"]
    item = status["library"][0]
    version = item["files"][0]["versions"][0]
    assert version["format"] == "DOCX"
    res = client.post(
        f"/api/v1/checkout/guest-orders/{order['id']}/downloads",
        json={"entitlement_id": item["id"], "version_id": version["version_id"]},
        headers={HEADER: token},
    )
    download = client.get(res.get_json()["data"]["url"])
    assert download.status_code == 200 and download.data.startswith(b"PK")
    assert ".docx" in download.headers["Content-Disposition"]
