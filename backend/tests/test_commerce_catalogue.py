"""Digital product CMS: CRUD, publishing, permissions, prices, bundles, private files,
homepage showcase, sitemap and public catalogue."""

from __future__ import annotations

from pathlib import Path

from app.extensions import db, limiter
from app.models import Product, ProductFileVersion, Redirect

from .conftest import make_photo, make_zip, minimal_pdf

PRODUCTS = "/api/v1/admin/products"


def _create(api, title="Calm Mornings Workbook", product_type="workbook", **extra):
    res = api.post(PRODUCTS, {"title": title, "product_type": product_type, **extra})
    assert res.status_code == 201, res.get_json()
    return res.get_json()["data"]


def _upload(api, product_id, data=None, name="workbook.pdf", **form):
    payload = minimal_pdf() if data is None else data
    return api.upload(f"{PRODUCTS}/{product_id}/files", payload, name, **form)


def _sellable(api, title="Calm Mornings Workbook", price=1500, currency="USD"):
    """A published, on-sale product with a file and a price."""
    product = _create(api, title, short_description="A gentle workbook for calmer mornings.")
    assert _upload(api, product["id"]).status_code == 201
    res = api.post(
        f"{PRODUCTS}/{product['id']}/prices", {"currency": currency, "amount_minor": price}
    )
    assert res.status_code == 201, res.get_json()
    res = api.patch(f"{PRODUCTS}/{product['id']}", {"sales_status": "on_sale"})
    assert res.status_code == 200, res.get_json()
    res = api.post(f"{PRODUCTS}/{product['id']}/publish")
    assert res.status_code == 200, res.get_json()
    return res.get_json()["data"]


# ---- CRUD, drafts and publishing ------------------------------------------------------------


def test_product_lifecycle_drafts_never_leak(seeded, as_role, client):
    api = as_role("product_manager")
    product = _create(api, short_description="First version.")
    assert product["status"] == "draft" and product["purchasable"] is False
    assert client.get(f"/api/v1/shop/products/{product['slug']}").status_code == 404

    res = api.post(f"{PRODUCTS}/{product['id']}/publish")
    assert res.status_code == 200, res.get_json()
    public = client.get(f"/api/v1/shop/products/{product['slug']}").get_json()["data"]
    assert public["title"] == "Calm Mornings Workbook"
    assert public["availability"] == "coming-soon" and public["prices"] == []

    # A draft edit is invisible until it is published again.
    detail = api.get(f"{PRODUCTS}/{product['id']}").get_json()["data"]
    res = api.patch(
        f"{PRODUCTS}/{product['id']}",
        {"subtitle": "Unreleased subtitle", "lock_version": detail["lock_version"]},
    )
    assert res.status_code == 200
    assert res.get_json()["data"]["has_unpublished_changes"] is True
    public = client.get(f"/api/v1/shop/products/{product['slug']}").get_json()["data"]
    assert public["subtitle"] == ""
    # Stale lock versions are refused (optimistic concurrency).
    stale = api.patch(
        f"{PRODUCTS}/{product['id']}", {"subtitle": "x", "lock_version": detail["lock_version"]}
    )
    assert stale.status_code == 409

    # Preview shows the draft privately (no-store, noindex).
    preview = api.get(f"{PRODUCTS}/{product['id']}/preview")
    assert preview.get_json()["data"]["subtitle"] == "Unreleased subtitle"
    assert preview.headers["Cache-Control"] == "no-store"
    assert "noindex" in preview.headers["X-Robots-Tag"]

    # Discard returns the draft to the published version.
    res = api.post(f"{PRODUCTS}/{product['id']}/discard")
    assert res.get_json()["data"]["subtitle"] == ""

    revisions = api.get(f"{PRODUCTS}/{product['id']}/revisions").get_json()["data"]
    assert {r["kind"] for r in revisions} >= {"draft", "publish"}
    first = revisions[-1]
    assert (
        api.post(f"{PRODUCTS}/{product['id']}/revisions/{first['id']}/restore").status_code == 200
    )

    copy = api.post(f"{PRODUCTS}/{product['id']}/duplicate").get_json()["data"]
    assert copy["status"] == "draft" and copy["slug"] != product["slug"] and copy["prices"] == []

    assert api.post(f"{PRODUCTS}/{product['id']}/archive").status_code == 200
    assert client.get(f"/api/v1/shop/products/{product['slug']}").status_code == 404
    assert api.patch(f"{PRODUCTS}/{product['id']}", {"subtitle": "x"}).status_code == 409
    assert api.post(f"{PRODUCTS}/{product['id']}/restore").get_json()["data"]["status"] == "draft"


def test_published_slug_change_creates_redirect(seeded, as_role, client):
    api = as_role("product_manager")
    product = _create(api, short_description="Text.")
    api.post(f"{PRODUCTS}/{product['id']}/publish")
    api.patch(f"{PRODUCTS}/{product['id']}", {"slug": "calm-mornings"})
    api.post(f"{PRODUCTS}/{product['id']}/publish")
    assert client.get("/api/v1/shop/products/calm-mornings").status_code == 200
    with seeded.app_context():
        redirect = db.session.scalar(
            db.select(Redirect).where(Redirect.source_path == f"/shop/{product['slug']}")
        )
        assert redirect.destination == "/shop/calm-mornings" and redirect.status_code == 301


def test_product_validation(seeded, as_role):
    api = as_role("product_manager")
    assert api.post(PRODUCTS, {"title": "X", "product_type": "course"}).status_code == 400
    assert api.post(PRODUCTS, {"title": "", "product_type": "ebook"}).status_code == 400
    product = _create(api)
    pid = product["id"]
    for payload in (
        {"slug": "collections"},  # reserved by the shop
        {"slug": "Not A Slug"},
        {"subtitle": "<b>bold</b>"},
        {"page_count": 0},
        {"page_count": 1.5},
        {"faq": [{"question": "Q?"}]},
        {"cover_media_id": 999999},
        {"price": 10},  # unknown field
        {"language": "english!"},
    ):
        res = api.patch(f"{PRODUCTS}/{pid}", payload)
        assert res.status_code == 400, payload
    # Real page counts are optional and stored exactly as entered.
    ok = api.patch(
        f"{PRODUCTS}/{pid}", {"page_count": 120, "faq": [{"question": "Q?", "answer": "A."}]}
    )
    assert ok.get_json()["data"]["page_count"] == 120
    # Cannot be put on sale without files and a price.
    res = api.patch(f"{PRODUCTS}/{pid}", {"sales_status": "on_sale"})
    assert res.status_code == 400
    assert "No deliverable files uploaded." in res.get_json()["error"]["details"]["sales_status"]


def test_product_permissions_are_granular(seeded, as_role):
    owner = as_role("product_manager", email="pm@example.org")
    product = _create(owner)
    pid = product["id"]
    editor = as_role("editor")
    assert editor.get(PRODUCTS).status_code == 403  # editorial roles gain nothing
    marketing = as_role("marketing_manager")
    assert marketing.get(PRODUCTS).status_code == 200
    assert marketing.post(PRODUCTS, {"title": "X", "product_type": "ebook"}).status_code == 403
    assert marketing.patch(f"{PRODUCTS}/{pid}", {"subtitle": "x"}).status_code == 403
    support = as_role("customer_support")
    assert support.get(f"{PRODUCTS}/{pid}").status_code == 200
    assert (
        support.post(f"{PRODUCTS}/{pid}/prices", {"currency": "USD", "amount_minor": 1}).status_code
        == 403
    )
    assert _upload(support, pid).status_code == 403
    orders = as_role("orders_manager")
    assert orders.post(f"{PRODUCTS}/{pid}/publish").status_code == 403
    limiter.reset()  # many sign-ins from one test client address
    finance = as_role("finance_manager")
    assert finance.patch(f"{PRODUCTS}/{pid}", {"pricing_model": "free"}).status_code == 403
    writer = as_role("content_writer")
    assert writer.get(PRODUCTS).status_code == 403
    analyst = as_role("analyst")
    assert analyst.get("/api/v1/admin/orders").status_code == 403


# ---- prices --------------------------------------------------------------------------------


def test_prices_use_integer_minor_units_and_explicit_currencies(seeded, as_role, client):
    api = as_role("product_manager")
    product = _create(api, short_description="Text.")
    url = f"{PRODUCTS}/{product['id']}/prices"
    assert api.post(url, {"currency": "USD", "amount_minor": 12.5}).status_code == 400  # float
    assert api.post(url, {"currency": "USD", "amount_minor": "1250"}).status_code == 400
    assert api.post(url, {"currency": "XXX", "amount_minor": 1250}).status_code == 400
    assert api.post(url, {"currency": "USD", "amount_minor": 0}).status_code == 400
    assert (
        api.post(
            url, {"currency": "USD", "amount_minor": 1250, "compare_at_minor": 1000}
        ).status_code
        == 400
    )
    assert (
        api.post(url, {"currency": "USD", "kind": "promotional", "amount_minor": 900}).status_code
        == 400
    )
    res = api.post(url, {"currency": "USD", "amount_minor": 1250, "compare_at_minor": 1800})
    assert res.status_code == 201
    assert api.post(url, {"currency": "KES", "amount_minor": 150000}).status_code == 201
    # Promotional prices must be lower and are time-boxed.
    assert (
        api.post(url, {"currency": "USD", "kind": "promotional", "amount_minor": 1300}).status_code
        == 400
    )
    res = api.post(
        url,
        {
            "currency": "USD",
            "kind": "promotional",
            "amount_minor": 999,
            "starts_at": "2020-01-01T00:00:00Z",
            "ends_at": "2099-01-01T00:00:00Z",
        },
    )
    assert res.status_code == 201, res.get_json()
    prices = {p["currency"]: p for p in res.get_json()["data"]["prices"]}
    assert prices["USD"]["amount_minor"] == 999 and prices["USD"]["formatted"] == "USD 9.99"
    assert prices["KES"]["formatted"] == "KES 1,500.00"
    # Free products cannot carry prices.
    free = _create(api, "Free Worksheet", "worksheet")
    api.patch(f"{PRODUCTS}/{free['id']}", {"pricing_model": "free"})
    assert (
        api.post(
            f"{PRODUCTS}/{free['id']}/prices", {"currency": "USD", "amount_minor": 100}
        ).status_code
        == 400
    )


def test_coming_soon_products_never_show_prices_or_purchase(seeded, as_role, client):
    api = as_role("product_manager")
    product = _create(api, short_description="Text.")
    _upload(api, product["id"])
    api.post(f"{PRODUCTS}/{product['id']}/prices", {"currency": "USD", "amount_minor": 1500})
    api.post(f"{PRODUCTS}/{product['id']}/publish")
    data = client.get(f"/api/v1/shop/products/{product['slug']}").get_json()["data"]
    assert data["availability"] == "coming-soon" and data["prices"] == []
    assert data["purchasable"] is False


# ---- bundles -------------------------------------------------------------------------------


def test_bundles_prevent_cycles_and_self_inclusion(seeded, as_role):
    api = as_role("product_manager")
    a = _create(api, "Bundle A", "bundle")
    b = _create(api, "Bundle B", "bundle")
    item = _create(api, "Journal", "journal")
    url = f"{PRODUCTS}/{a['id']}/bundle-items"
    assert api.put(url, {"product_ids": [a["id"]]}).status_code == 400
    assert api.put(url, {"product_ids": [b["id"], item["id"]]}).status_code == 200
    res = api.put(f"{PRODUCTS}/{b['id']}/bundle-items", {"product_ids": [a["id"]]})
    assert res.status_code == 400
    assert "circular" in str(res.get_json()["error"]["details"])
    assert (
        api.put(f"{PRODUCTS}/{item['id']}/bundle-items", {"product_ids": [a["id"]]}).status_code
        == 400
    )
    # Bundles have no files of their own.
    assert _upload(api, a["id"]).status_code == 400
    editor_of_content = as_role("marketing_manager")
    assert editor_of_content.put(url, {"product_ids": []}).status_code == 403


# ---- private files -------------------------------------------------------------------------


def test_private_file_uploads_are_validated(seeded, as_role, app):
    api = as_role("product_manager")
    pid = _create(api)["id"]
    ok = _upload(api, pid, minimal_pdf(), "My Workbook (final).pdf", description="Printable A4")
    assert ok.status_code == 201, ok.get_json()
    file = ok.get_json()["data"]
    assert file["current_version"]["format"] == "pdf"
    assert file["current_version"]["original_filename"] == "My Workbook (final).pdf"
    assert "storage_key" not in str(file) and "/" not in file["current_version"]["sha256"]

    epub = make_zip(
        {"META-INF/container.xml": "<container/>", "OEBPS/a.xhtml": "<p>x</p>"}, epub=True
    )
    assert _upload(api, pid, epub, "book.epub").status_code == 201
    pack = make_zip({"worksheets/day-1.pdf": minimal_pdf(), "readme.txt": "Hello"})
    assert _upload(api, pid, pack, "pack.zip").status_code == 201

    rejected = [
        (b"MZ\x90\x00 fake executable", "workbook.pdf"),
        (minimal_pdf(b"/JavaScript (app.alert(1))\n"), "workbook.pdf"),
        (minimal_pdf(b"/Launch << /F (cmd.exe) >>\n"), "workbook.pdf"),
        (b"%PDF-1.4\nno end marker", "workbook.pdf"),
        (minimal_pdf(), "workbook.exe"),
        (minimal_pdf(), "workbook.zip"),
        (make_zip({"../../etc/passwd": "x"}), "pack.zip"),
        (make_zip({"/abs/path.txt": "x"}), "pack.zip"),
        (make_zip({"setup.exe": "MZ"}), "pack.zip"),
        (make_zip({"inner.zip": "PK"}), "pack.zip"),
        (make_zip({"art.svg": "<svg onload=alert(1)>"}), "pack.zip"),
        (make_zip({"bomb.txt": b"0" * 3_000_000}), "pack.zip"),
        (b"plain text", "notes.txt"),
        (b"", "empty.pdf"),
    ]
    for data, name in rejected:
        res = _upload(api, pid, data, name)
        assert res.status_code == 400, (name, data[:20], res.get_json())
    with app.app_context():
        versions = db.session.scalars(db.select(ProductFileVersion)).all()
        assert len(versions) == 3
        root = Path(app.config["PRODUCT_FILES_ROOT"]).resolve()
        media_root = Path(app.config["MEDIA_ROOT"]).resolve()
        for v in versions:
            path = (root / v.storage_key).resolve()
            assert path.is_file() and root in path.parents
            assert media_root not in path.parents
            assert v.original_filename not in v.storage_key  # random keys only
            assert oct(path.stat().st_mode)[-3:] == "600"
        # Uploads are received in UPLOAD_TEMP_ROOT; rejected ones leave nothing there.
        assert not list(Path(app.config["UPLOAD_TEMP_ROOT"]).iterdir())


def test_zip_symlinks_and_encryption_are_refused(seeded, as_role):
    import io
    import zipfile

    api = as_role("product_manager")
    pid = _create(api)["id"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        info = zipfile.ZipInfo("link.txt")
        info.external_attr = 0o120777 << 16
        archive.writestr(info, "/etc/passwd")
    assert _upload(api, pid, buf.getvalue(), "pack.zip").status_code == 400
    # zipfile cannot write encrypted entries, so set the "encrypted" flag bit directly in
    # the local header (offset 6) and the central directory record (offset 8).
    data = bytearray(make_zip({"secret.txt": "x"}))
    data[6] |= 0x1
    central = data.index(b"PK\x01\x02")
    data[central + 8] |= 0x1
    assert _upload(api, pid, bytes(data), "pack.zip").status_code == 400


def test_file_versions_replacement_deactivation_and_admin_download(seeded, as_role, client):
    api = as_role("product_manager")
    pid = _create(api)["id"]
    file = _upload(api, pid).get_json()["data"]
    res = api.upload(
        f"{PRODUCTS}/{pid}/files/{file['id']}/versions", minimal_pdf(b"% v2\n"), "v2.pdf"
    )
    assert res.status_code == 201
    replaced = res.get_json()["data"]
    assert replaced["current_version"]["version"] == 2 and len(replaced["versions"]) == 2
    v1 = replaced["versions"][-1]
    download = api.get(f"{PRODUCTS}/{pid}/files/{file['id']}/versions/{v1['id']}/download")
    assert download.status_code == 200
    assert download.data.startswith(b"%PDF") and b"% v2" not in download.data
    assert "attachment" in download.headers["Content-Disposition"]
    assert "no-store" in download.headers["Cache-Control"]
    viewer = as_role("customer_support")
    assert (
        viewer.get(f"{PRODUCTS}/{pid}/files/{file['id']}/versions/{v1['id']}/download").status_code
        == 403
    )
    assert (
        client.get(f"{PRODUCTS}/{pid}/files/{file['id']}/versions/{v1['id']}/download").status_code
        == 401
    )
    # Rollback to v1 and deactivate.
    res = api.patch(f"{PRODUCTS}/{pid}/files/{file['id']}", {"current_version_id": v1["id"]})
    assert res.get_json()["data"]["current_version"]["version"] == 1
    res = api.patch(f"{PRODUCTS}/{pid}/files/{file['id']}", {"status": "inactive"})
    assert res.get_json()["data"]["status"] == "inactive"
    # Private files are not reachable through the public media route.
    assert client.get("/media/" + "x" * 10).status_code == 404


def test_malware_scanner_runs_outside_requests_and_gates_delivery(seeded, as_role, app):
    import json
    import sys

    from app.services.commerce.catalogue import readiness
    from app.services.commerce.product_files import scan_pending

    script = Path(app.config["PRODUCT_FILES_ROOT"]).parent / "scan.py"
    script.write_text(
        "import sys; sys.exit(1 if b'EICAR' in open(sys.argv[1],'rb').read() else 0)\n"
    )
    app.config["PRODUCT_FILES_SCAN_COMMAND"] = json.dumps([sys.executable, str(script), "{path}"])
    api = as_role("product_manager")
    pid = _create(api)["id"]
    clean = _upload(api, pid).get_json()["data"]
    assert clean["current_version"]["scan_status"] == "pending"
    bad = _upload(api, pid, minimal_pdf(b"% EICAR test\n"), "bad.pdf").get_json()["data"]
    with app.app_context():
        product = db.session.get(Product, pid)
        assert any("scan" in i for i in readiness(product)["issues"])
        assert scan_pending() == {"clean": 1, "infected": 1, "error": 0}
        db.session.commit()
        product = db.session.get(Product, pid)
        statuses = {f.id: f.current_version.scan_status for f in product.files}
        assert statuses == {clean["id"]: "clean", bad["id"]: "infected"}


# ---- categories, collections, homepage, sitemap -------------------------------------------


def test_collections_categories_and_homepage_showcase(seeded, as_role, client):
    api = as_role("super_admin")
    first = _sellable(api, "Alpha Guide")
    second = _create(api, "Hidden Draft", short_description="Draft only.")
    res = api.post(
        "/api/v1/admin/product-collections",
        {"name": "Morning Set", "product_ids": [second["id"], first["id"]]},
    )
    assert res.status_code == 201, res.get_json()
    collection = res.get_json()["data"]
    public = client.get("/api/v1/shop/collections/morning-set").get_json()["data"]
    assert [p["title"] for p in public["products"]] == ["Alpha Guide"]  # drafts never appear

    cat = api.post("/api/v1/admin/product-categories", {"name": "Morning"}).get_json()["data"]
    api.patch(f"{PRODUCTS}/{first['id']}", {"category_ids": [cat["id"]]})
    api.post(f"{PRODUCTS}/{first['id']}/publish")
    listing = client.get("/api/v1/shop/products?category=morning").get_json()["data"]
    assert [p["title"] for p in listing] == ["Alpha Guide"]
    assert api.delete(f"/api/v1/admin/product-categories/{cat['id']}").status_code == 409

    home = api.get("/api/v1/admin/homepage").get_json()["data"]
    sections = home["sections"]
    showcase = next(s for s in sections if s["section_type"] == "product_previews")
    showcase["content"].update(mode="manual", products=[second["id"], first["id"]], count=3)
    res = api.put(
        f"/api/v1/admin/pages/{home['id']}/draft",
        {"lock_version": home["lock_version"], "sections": sections},
    )
    assert res.status_code == 200, res.get_json()
    preview = api.post(f"/api/v1/admin/pages/{home['id']}/preview", {}).get_json()["data"]
    block = next(s for s in preview["page"]["sections"] if s["type"] == "product_previews")
    assert [p["title"] for p in block["data"]["products"]] == ["Alpha Guide"]
    assert block["data"]["products"][0]["prices"][0]["formatted"] == "USD 15.00"

    showcase["content"].update(mode="collection", products=[], collection=[collection["id"]])
    detail = api.get(f"/api/v1/admin/pages/{home['id']}").get_json()["data"]
    res = api.put(
        f"/api/v1/admin/pages/{home['id']}/draft",
        {"lock_version": detail["lock_version"], "sections": sections},
    )
    assert res.status_code == 200, res.get_json()
    showcase["content"]["products"] = [999999]
    showcase["content"]["mode"] = "manual"
    detail = api.get(f"/api/v1/admin/pages/{home['id']}").get_json()["data"]
    res = api.put(
        f"/api/v1/admin/pages/{home['id']}/draft",
        {"lock_version": detail["lock_version"], "sections": sections},
    )
    assert res.status_code == 400  # unknown product reference


def test_sitemap_lists_published_products_only(seeded, as_role, client):
    api = as_role("super_admin")
    live = _sellable(api, "Sitemap Product")
    hidden = _create(api, "Noindex Product", short_description="x")
    api.patch(f"{PRODUCTS}/{hidden['id']}", {"noindex": True})
    api.post(f"{PRODUCTS}/{hidden['id']}/publish")
    draft = _create(api, "Draft Product")
    paths = [e["path"] for e in client.get("/api/v1/sitemap").get_json()["data"]]
    assert f"/shop/{live['slug']}" in paths
    assert f"/shop/{hidden['slug']}" not in paths and f"/shop/{draft['slug']}" not in paths
    assert "/shop/collections/fresh-start" in paths  # seeded collection with published titles


def test_public_catalogue_filters_sort_and_search(seeded, as_role, client):
    api = as_role("super_admin")
    _sellable(api, "Zebra Planner", price=900)
    _sellable(api, "Aardvark Journal", price=2900)
    body = client.get("/api/v1/shop/products?sort=price_asc&currency=USD").get_json()
    titles = [p["title"] for p in body["data"]]
    assert titles.index("Zebra Planner") < titles.index("Aardvark Journal")
    assert body["meta"]["display_currencies"] == ["USD", "KES"]
    found = client.get("/api/v1/shop/products?q=aardvark").get_json()["data"]
    assert [p["title"] for p in found] == ["Aardvark Journal"]
    assert client.get("/api/v1/shop/products?sort=nope").status_code == 400
    assert client.get("/api/v1/shop/products/not-a-product").status_code == 404
    product = client.get("/api/v1/shop/products/zebra-planner").get_json()["data"]
    assert product["purchasable"] and product["formats"] == ["PDF"]
    assert product["files"][0]["format"] == "PDF" and "storage" not in str(product)
    assert "rating" not in str(product).lower() and "review" not in str(product).lower()


def test_cover_images_in_use_cannot_be_deleted(seeded, as_role):
    api = as_role("super_admin")
    asset = api.upload(
        "/api/v1/admin/media", make_photo(800, 1200), "cover.jpg", alt_text="Cover"
    ).get_json()["data"]
    product = _create(api, cover_media_id=asset["id"], short_description="x")
    api.post(f"{PRODUCTS}/{product['id']}/publish")
    assert api.delete(f"/api/v1/admin/media/{asset['id']}").status_code == 409
