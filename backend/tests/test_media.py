"""Media uploads, optimisation, storage safety and permissions."""

import io
from pathlib import Path

import pytest
from PIL import Image

from app.extensions import db
from app.media import processing
from app.models import Article, AuditLog, MediaAsset, MediaVariant
from app.storage import LocalStorage, StorageError, validate_key

from .conftest import make_photo, make_png, png_header_only

MEDIA = "/api/v1/admin/media"


def _files(app, public=True):
    root = Path(app.config["MEDIA_ROOT"]) / ("public" if public else "private")
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


def _upload(api, data=None, filename="Sunrise Over Hills.JPG", **form):
    res = api.upload(MEDIA, data or make_photo(), filename, **form)
    assert res.status_code in (200, 201), res.get_json()
    return res.get_json()["data"]


# ---- processing --------------------------------------------------------------------


def test_upload_generates_optimised_variants(app, as_role):
    api = as_role("super_admin")
    source = make_photo(1800, 1200, gps=True)
    asset = _upload(api, source, alt_text="Hills at sunrise", title="Sunrise")
    assert asset["managed"] and asset["width"] == 1800 and asset["height"] == 1200
    responsive = [v for v in asset["variants"] if v["preset"] == "responsive"]
    widths = sorted({v["width"] for v in responsive})
    assert widths == [160, 320, 640, 960, 1280, 1600]  # never above the 1600px cap
    webp = {v["width"]: v for v in responsive if v["format"] == "webp"}
    jpeg = {v["width"]: v for v in responsive if v["format"] == "jpeg"}
    assert set(jpeg) == {640, 1280}
    # WebP beats the JPEG fallback at the same size, and everything beats the source.
    assert webp[1280]["size_bytes"] < jpeg[1280]["size_bytes"] < len(source)
    for v in asset["variants"]:
        if v["format"] == "avif":
            assert v["size_bytes"] < webp[v["width"]]["size_bytes"]
    social = [v for v in asset["variants"] if v["preset"] == "social"]
    assert [(v["format"], v["width"], v["height"]) for v in social] == [("jpeg", 1200, 630)]
    avatar = {(v["width"], v["height"]) for v in asset["variants"] if v["preset"] == "avatar"}
    assert (320, 320) in avatar
    # Stable, application-generated keys; the uploaded file name is only a slug.
    for path in _files(app):
        rel = path.relative_to(Path(app.config["MEDIA_ROOT"]) / "public").as_posix()
        assert rel.startswith(asset["url"].split("/")[2]) or "/" in rel
        assert " " not in rel and rel.islower()
        assert "sunrise-over-hills" in rel
    # Public derivatives carry no EXIF/GPS metadata; the private original is kept.
    with Image.open(_files(app)[0]) as derived:
        assert not derived.getexif()
    originals = _files(app, public=False)
    assert len(originals) == 1 and originals[0].read_bytes() == source
    with app.app_context():
        record = db.session.get(MediaAsset, asset["id"])
        assert record.original_size == len(source) and record.checksum
        assert db.session.scalar(db.select(AuditLog).where(AuditLog.action == "media.uploaded"))


def test_exif_orientation_is_applied(app, as_role):
    api = as_role("super_admin")
    asset = _upload(api, make_photo(900, 600, exif_orientation=6))
    assert (asset["width"], asset["height"]) == (600, 900)


def test_small_images_are_never_upscaled(app, as_role):
    asset = _upload(as_role("super_admin"), make_photo(300, 200))
    assert max(v["width"] for v in asset["variants"]) == 300
    assert {v["width"] for v in asset["variants"] if v["preset"] == "responsive"} == {160, 300}


def test_transparency_is_preserved_with_png_fallback(app, as_role):
    asset = _upload(as_role("super_admin"), make_png(alpha=True), "badge.png")
    assert asset["has_alpha"] is True
    formats = {v["format"] for v in asset["variants"] if v["preset"] == "responsive"}
    assert "png" in formats and "jpeg" not in formats


def test_flat_graphics_keep_sharp_edges():
    data = make_png(800, 500, flat=True)
    image, _ = processing.open_validated(
        data, max_bytes=10**7, max_pixels=10**8, max_dimension=9000
    )
    image, _ = processing.normalise(image)
    assert processing.is_graphic(image)
    webp = processing.encode_webp(image, processing.PRESETS["responsive"], graphic=True)
    assert processing.psnr(image, webp) >= 40  # lossless or near-lossless


def test_avif_is_dropped_when_not_smaller(monkeypatch):
    image = Image.new("RGB", (64, 64), (200, 100, 50))
    monkeypatch.setattr(processing, "encode", lambda *a, **k: b"x" * 5000)
    assert processing.maybe_avif(image, b"y" * 1000, graphic=False) is None


def test_cmyk_and_icc_images_are_normalised_to_srgb():
    img = Image.new("CMYK", (200, 120), (0, 80, 80, 0))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    result = processing.process(
        buf.getvalue(), max_bytes=10**7, max_pixels=10**8, max_dimension=9000, avif=False
    )
    with Image.open(io.BytesIO(result.files[0].data)) as out:
        assert out.mode in ("RGB", "RGBA")


# ---- validation ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "data,filename,message",
    [
        (b"GIF89a not really", "x.gif", "not a supported image"),
        (b"hello world", "photo.jpg", "not a supported image"),
        (
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            "a.svg",
            "SVG",
        ),
        (b"\xef\xbb\xbf<?xml version='1.0'?><svg/>", "b.png", "SVG"),
        (b"", "empty.png", "empty"),
        (make_photo(400, 400)[:6000], "cut.jpg", "damaged"),
    ],
)
def test_invalid_uploads_are_rejected(app, as_role, data, filename, message):
    res = as_role("super_admin").upload(MEDIA, data, filename)
    assert res.status_code == 400
    assert message.lower() in res.get_json()["error"]["message"].lower()
    assert _files(app) == [] and _files(app, public=False) == []
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(MediaAsset.id))) == 0


def test_animated_images_are_rejected(app, as_role):
    frames = [Image.new("RGB", (40, 40), c) for c in ((255, 0, 0), (0, 255, 0))]
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=100)
    res = as_role("super_admin").upload(MEDIA, buf.getvalue(), "anim.gif")
    assert res.status_code == 400 and "Animated" in res.get_json()["error"]["message"]


def test_decompression_bombs_are_rejected_before_decoding(app, as_role):
    api = as_role("super_admin")
    res = api.upload(MEDIA, png_header_only(11000, 11000), "bomb.png")
    assert res.status_code == 400 and "too many pixels" in res.get_json()["error"]["message"]
    res = api.upload(MEDIA, png_header_only(13000, 100), "wide.png")
    assert res.status_code == 400 and "12000px" in res.get_json()["error"]["message"]
    app.config["MEDIA_MAX_DIMENSION"] = 60000
    res = api.upload(MEDIA, png_header_only(9000, 9000), "bomb2.png")  # 81 MP > 50 MP
    assert res.status_code == 400 and "too many pixels" in res.get_json()["error"]["message"]


def test_oversized_uploads_are_rejected(app, as_role):
    api = as_role("super_admin")
    app.config["MEDIA_MAX_UPLOAD_MB"] = 0
    res = api.upload(MEDIA, make_photo(300, 200), "big.jpg")
    assert res.status_code == 400 and "larger than" in res.get_json()["error"]["message"]
    app.config["MAX_CONTENT_LENGTH"] = 2000
    res = api.upload(MEDIA, make_photo(300, 200), "big.jpg")
    assert res.status_code == 413


def test_storage_keys_cannot_escape_the_media_root(tmp_path):
    storage = LocalStorage(tmp_path)
    for bad in ("../etc/passwd", "/abs/path", "a/../../b", "UPPER/case", "a//b", "", "x\x00y"):
        with pytest.raises(StorageError):
            validate_key(bad)
        with pytest.raises(StorageError):
            storage.save(bad, b"x", public=True)
    storage.save("abc123/v1/ok-file-320.webp", b"data", public=True)
    assert (tmp_path / "public" / "abc123/v1/ok-file-320.webp").read_bytes() == b"data"


def test_hostile_filenames_only_become_slugs(app, as_role):
    asset = _upload(as_role("super_admin"), make_photo(400, 300), "../../etc/<script>pa ss.jpg")
    assert asset["filename"] == "etc-script-pa-ss"
    assert all(".." not in v["url"] for v in asset["variants"])


def test_identical_uploads_reuse_the_existing_asset(app, as_role):
    api = as_role("super_admin")
    data = make_photo(500, 300)
    first = _upload(api, data)
    res = api.upload(MEDIA, data, "copy.jpg")
    assert res.status_code == 200 and res.get_json()["data"]["duplicate"] is True
    assert res.get_json()["data"]["id"] == first["id"]


def test_failed_processing_leaves_no_files_or_records(app, as_role, monkeypatch):
    from app.storage import LocalStorage as Storage

    calls = {"n": 0}
    original = Storage.save

    def flaky(self, key, data, *, public):
        calls["n"] += 1
        if calls["n"] == 5:
            raise OSError("disk full")
        return original(self, key, data, public=public)

    monkeypatch.setattr(Storage, "save", flaky)
    res = as_role("super_admin").upload(MEDIA, make_photo(700, 500), "x.jpg")
    assert res.status_code == 500
    assert _files(app) == [] and _files(app, public=False) == []
    with app.app_context():
        db.session.rollback()
        assert db.session.scalar(db.select(db.func.count(MediaAsset.id))) == 0


# ---- library operations ------------------------------------------------------------------


def test_library_search_filters_and_sorting(seeded, as_role):
    api = as_role("super_admin")
    _upload(api, make_photo(400, 300, seed=1), "alpha-field.jpg", alt_text="Field")
    _upload(api, make_png(alpha=True), "zeta-badge.png")
    data = api.get(f"{MEDIA}?q=alpha").get_json()
    assert [m["filename"] for m in data["data"]] == ["alpha-field"]
    unused = api.get(f"{MEDIA}?usage=unused&sort=filename").get_json()["data"]
    assert [m["filename"] for m in unused][:2] == ["alpha-field", "zeta-badge"]
    used = api.get(f"{MEDIA}?usage=used").get_json()["data"]
    assert used and all(m["usage_count"] > 0 for m in used)
    missing = api.get(f"{MEDIA}?usage=missing_alt").get_json()["data"]
    assert [m["filename"] for m in missing] == ["zeta-badge"]
    pngs = api.get(f"{MEDIA}?type=image/png").get_json()["data"]
    assert any(m["filename"] == "zeta-badge" for m in pngs)
    by_size = api.get(f"{MEDIA}?sort=size").get_json()["data"]
    sizes = [m["size_bytes"] for m in by_size]
    assert sizes == sorted(sizes, reverse=True)
    assert api.get(f"{MEDIA}?sort=evil").status_code == 400


def test_metadata_edit_keeps_urls_and_focal_point_regenerates(app, as_role):
    api = as_role("super_admin")
    asset = _upload(api, make_photo(1200, 800))
    res = api.patch(
        f"{MEDIA}/{asset['id']}",
        {"alt_text": "A calm lake", "caption": "Lake Bled", "credit": "TPA"},
    )
    body = res.get_json()["data"]
    assert res.status_code == 200 and body["url"] == asset["url"] and body["version"] == 1
    assert api.patch(f"{MEDIA}/{asset['id']}", {"alt_text": "<b>x</b>"}).status_code == 400
    res = api.patch(f"{MEDIA}/{asset['id']}", {"focal_x": 0.2, "focal_y": 0.3})
    body = res.get_json()["data"]
    assert body["version"] == 2 and body["focal_point"] == {"x": 0.2, "y": 0.3}
    assert body["url"] != asset["url"]


def test_replace_supersedes_variants_and_prune_removes_them(app, as_role):
    api = as_role("super_admin")
    asset = _upload(api, make_photo(800, 600, seed=1))
    old_files = set(_files(app))
    replacement = make_photo(900, 600, seed=2)
    res = api.upload(f"{MEDIA}/{asset['id']}/replace", replacement, "new.jpg")
    body = res.get_json()["data"]
    assert res.status_code == 200 and body["version"] == 2 and body["changed"] is True
    assert body["width"] == 900
    # Old files stay until pruned (already-built pages keep working).
    assert old_files <= set(_files(app))
    with app.app_context():
        from app.services.admin.media_admin import prune_superseded

        result = prune_superseded(days=0)
        db.session.commit()
        assert result["variants_removed"] == len(asset["variants"])
    assert not (old_files & set(_files(app)))
    same = api.upload(f"{MEDIA}/{asset['id']}/replace", replacement, "n.jpg")
    assert same.get_json()["data"]["changed"] is False


def test_referenced_media_cannot_be_deleted_but_can_be_archived(seeded, as_role):
    api = as_role("super_admin")
    asset = _upload(api, make_photo(600, 400))
    with seeded.app_context():
        article = db.session.get(Article, 1)
        article.body = [*article.body, {"type": "image", "media_id": asset["id"], "align": "wide"}]
        db.session.commit()
    res = api.delete(f"{MEDIA}/{asset['id']}")
    assert res.status_code == 409
    assert res.get_json()["error"]["details"]["usage"][0]["type"] == "article"
    assert api.post(f"{MEDIA}/{asset['id']}/archive").status_code == 200
    # Archived images keep serving but cannot be newly chosen.
    assert api.get(asset["url"]).status_code == 200
    new = api.post("/api/v1/admin/articles", {"title": "New", "featured_image_id": asset["id"]})
    assert new.status_code == 400
    listed = api.get(MEDIA).get_json()["data"]
    assert asset["id"] not in [m["id"] for m in listed]
    archived = api.get(f"{MEDIA}?status=archived").get_json()["data"]
    assert [m["id"] for m in archived] == [asset["id"]]
    assert api.post(f"{MEDIA}/{asset['id']}/restore").status_code == 200


def test_unused_media_is_deleted_with_its_files(app, as_role):
    api = as_role("super_admin")
    asset = _upload(api, make_photo(500, 300))
    assert _files(app)
    assert api.delete(f"{MEDIA}/{asset['id']}").status_code == 200
    assert _files(app) == [] and _files(app, public=False) == []
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(MediaVariant.id))) == 0


def test_built_in_images_are_protected(seeded, as_role):
    api = as_role("super_admin")
    legacy = api.get(MEDIA).get_json()["data"][0]
    assert legacy["managed"] is False
    res = api.upload(f"{MEDIA}/{legacy['id']}/replace", make_photo(300, 200), "x.jpg")
    assert res.status_code == 409


def test_media_files_are_served_with_immutable_caching(app, as_role, client):
    asset = _upload(as_role("super_admin"), make_photo(400, 300))
    res = client.get(asset["variants"][0]["url"])
    assert res.status_code == 200
    assert "immutable" in res.headers["Cache-Control"]
    assert res.headers["Content-Type"].startswith("image/")
    # Private originals are not reachable over HTTP.
    assert client.get("/media/originals/x/v1.jpg").status_code == 404
    assert client.get("/media/../private/x").status_code == 404


def test_media_permissions(app, as_role):
    owner = as_role("super_admin", email="owner@example.org")
    asset = _upload(owner, make_photo(400, 300))
    analyst = as_role("analyst")
    assert analyst.get(MEDIA).status_code == 200
    assert analyst.upload(MEDIA, make_photo(300, 200), "a.jpg").status_code == 403
    assert analyst.patch(f"{MEDIA}/{asset['id']}", {"alt_text": "x"}).status_code == 403
    writer = as_role("content_writer")
    assert writer.upload(MEDIA, make_photo(310, 200), "w.jpg").status_code == 201
    assert writer.patch(f"{MEDIA}/{asset['id']}", {"alt_text": "x"}).status_code == 403
    up = f"{MEDIA}/{asset['id']}/replace"
    assert writer.upload(up, make_photo(320, 200), "r.jpg").status_code == 403
    assert writer.delete(f"{MEDIA}/{asset['id']}").status_code == 403
    assert writer.post(f"{MEDIA}/{asset['id']}/archive").status_code == 403
    affiliates = as_role("affiliate_manager")  # future-module template: no media access
    assert affiliates.get(MEDIA).status_code == 403
    pm = as_role("product_manager")  # uploads product covers, cannot delete media
    assert pm.get(MEDIA).status_code == 200
    assert pm.delete(f"{MEDIA}/{asset['id']}").status_code == 403


def test_public_article_api_serves_responsive_images(seeded, as_role, client):
    api = as_role("super_admin")
    asset = _upload(api, make_photo(1400, 900), alt_text="Morning light")
    with seeded.app_context():
        article = db.session.scalar(db.select(Article).where(Article.status == "published"))
        article.featured_image_id = asset["id"]
        article.body = [
            *article.body,
            {"type": "image", "media_id": asset["id"], "caption": "Light", "align": "wide"},
            {"type": "image", "media_id": 99999, "align": "wide"},  # dangling: dropped
        ]
        slug = article.slug
        db.session.commit()
    data = client.get(f"/api/v1/articles/{slug}").get_json()["data"]["article"]
    image = data["image"]
    assert image["src"].endswith(".jpg") and image["width"] == 1400
    assert "image/webp" in image["sources"] and " 640w" in image["sources"]["image/webp"]
    assert image["alt"] == "Morning light" and image["placeholder"].startswith("#")
    blocks = [b for b in data["body"] if b["type"] == "image"]
    assert len(blocks) == 1 and blocks[0]["image"]["srcset"]
    assert data["seo"]["og_image"]["width"] == 1200 and data["seo"]["og_image"]["height"] == 630
