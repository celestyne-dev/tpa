"""THROWAWAY (visual-check branch only, never merged): extra CI fixtures so the built
homepage shows every editorial section for screenshots: article images, free resources,
reading statistics and Editor's Picks. Throwaway development databases only."""

from __future__ import annotations

import io
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import create_app  # noqa: E402
from app.auth.passwords import hash_password  # noqa: E402
from app.auth.roles import set_user_roles  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import AnalyticsDailyPage, Article, User  # noqa: E402

PASSWORD = "Visual-Check-Password-1"
EMAIL = "visual-check@example.org"
PALETTE = [
    ((61, 90, 72), (214, 184, 120)),
    ((176, 141, 69), (244, 237, 224)),
    ((44, 62, 54), (158, 186, 160)),
    ((120, 98, 72), (240, 222, 190)),
    ((88, 120, 98), (250, 246, 238)),
    ((150, 110, 60), (60, 80, 66)),
]


def photo(i: int) -> bytes:
    a, b = PALETTE[i % len(PALETTE)]
    img = Image.new("RGB", (1600, 1000))
    draw = ImageDraw.Draw(img)
    for y in range(1000):
        t = y / 1000
        draw.line([(0, y), (1600, y)], fill=tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3)))
    draw.ellipse([900 - i * 60, 180, 1400 - i * 60, 680], fill=b)
    draw.rectangle([0, 760, 1600, 1000], fill=a)
    img = img.filter(ImageFilter.GaussianBlur(2))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def main() -> int:
    app = create_app()
    with app.app_context():
        if not app.config.get("ALLOW_SAMPLE_SEED") or app.config.get("ENV_NAME") == "production":
            print("Refusing: throwaway databases only.")
            return 2
        user = User(email=EMAIL, display_name="Visual check", password_hash=hash_password(PASSWORD), status="active")
        db.session.add(user)
        db.session.flush()
        set_user_roles(user, ["super_admin"], assigned_by=None)
        db.session.commit()

    c = app.test_client()
    assert c.post("/api/v1/admin/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200

    def h():
        cookie = c.get_cookie("csrf_access_token")
        return {"X-CSRF-TOKEN": cookie.value if cookie else ""}

    def upload_image(i, alt):
        res = c.post(
            "/api/v1/admin/media",
            data={"file": (io.BytesIO(photo(i)), f"visual-{i}.jpg"), "alt_text": alt},
            headers=h(),
            content_type="multipart/form-data",
        )
        assert res.status_code in (200, 201), res.get_json()  # 200: identical image reused
        return res.get_json()["data"]["id"]

    with app.app_context():
        articles = list(
            db.session.scalars(
                select(Article).where(Article.status == "published").order_by(Article.published_at.desc())
            )
        )
        targets = [(a.id, a.title) for a in articles if a.featured_image_id is None][:14]
    for i, (article_id, title) in enumerate(targets):
        media_id = upload_image(i, f"Illustration for {title}")
        with app.app_context():
            db.session.get(Article, article_id).featured_image_id = media_id
            db.session.commit()

    # Free resources (one with a cover, two with the designed brand cover).
    for i, (title, ptype) in enumerate(
        [("Morning Reset Checklist", "checklist"), ("Weekly Reflection Worksheet", "worksheet"), ("Boundaries Starter Guide", "guide")]
    ):
        res = c.post(
            "/api/v1/admin/products",
            json={"title": title, "product_type": ptype, "short_description": f"A short, practical {ptype} to help you take the next step with calm and clarity."},
            headers=h(),
        )
        assert res.status_code == 201, res.get_json()
        pid = res.get_json()["data"]["id"]
        pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< >>\n%%EOF\n"
        res = c.post(
            f"/api/v1/admin/products/{pid}/files",
            data={"file": (io.BytesIO(pdf), f"{ptype}.pdf")},
            headers=h(),
            content_type="multipart/form-data",
        )
        assert res.status_code == 201, res.get_json()
        patch = {"pricing_model": "free"}
        if i == 0:
            patch["cover_media_id"] = upload_image(5, "")
        assert c.patch(f"/api/v1/admin/products/{pid}", json=patch, headers=h()).status_code == 200
        assert c.patch(f"/api/v1/admin/products/{pid}", json={"sales_status": "on_sale"}, headers=h()).status_code == 200
        res = c.post(f"/api/v1/admin/products/{pid}/publish", headers=h())
        assert res.status_code == 200, res.get_json()

    # Reading statistics (aggregates) for Popular articles.
    with app.app_context():
        today = datetime.now(UTC).date()
        for rank, a in enumerate(articles[2:8]):
            db.session.add(
                AnalyticsDailyPage(
                    day=today - timedelta(days=1), path=f"/articles/{a.slug}", page_type="article",
                    content_type="article", content_id=a.id, views=100 - rank * 9, visitors=80 - rank * 7,
                )
            )
        db.session.commit()
        picks = [a.id for a in articles[8:12]]

    # Editor's Picks on the published homepage.
    home = c.get("/api/v1/admin/homepage").get_json()["data"]
    sections = []
    for s in home["sections"]:
        item = {k: s[k] for k in ("id", "name", "section_type", "variant", "content", "design", "is_visible")}
        item |= {"visibility": s["visibility"], "reusable_section_id": s["reusable_section_id"]}
        if s["key"] == "editors-picks":
            item["content"] = {**item["content"], "articles": picks}
        sections.append(item)
    res = c.put(f"/api/v1/admin/pages/{home['id']}/draft", json={"lock_version": home["lock_version"], "sections": sections}, headers=h())
    assert res.status_code == 200, res.get_json()
    res = c.post(f"/api/v1/admin/pages/{home['id']}/publish", json={"lock_version": res.get_json()["data"]["lock_version"]}, headers=h())
    assert res.status_code == 200, res.get_json()
    # A real author with a bio, so the author page, the authors index and the article
    # author box can be checked.
    from app.models import Author

    with app.app_context():
        author = db.session.scalar(select(Author).order_by(Author.id))
        author.is_person = True
        author.bio = (
            "Writes about resilience, confidence and the small daily habits that help people "
            "move forward with intention."
        )
        db.session.commit()
    print("Visual-check fixtures ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
