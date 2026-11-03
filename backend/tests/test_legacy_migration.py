"""Batch 12.4A: legacy website inventory and SEO migration.

Fake legacy and new sites run on 127.0.0.1; nothing here touches the real website.
"""

from __future__ import annotations

import csv
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import Article, Redirect
from app.services.seo_service import sitemap_entries
from legacy_migration import inventory, mapping, report, rewrite, verify
from legacy_migration.core import (
    classify_path,
    path_key,
    path_of,
    publication_status,
    read_csv,
    write_csv,
)
from legacy_migration.fetch import Fetcher

# ---- a tiny fake website -------------------------------------------------------------


def html(title, *, canonical=None, body="", head="", words=0):
    link = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    text = " ".join(["word"] * words)
    return (
        f"<!doctype html><html><head><title>{title}</title>"
        f'<meta name="description" content="About {title}">{link}{head}</head>'
        f"<body><h1>{title}</h1>{body}<p>{text}</p></body></html>"
    )


def article(title, path, *, author="Jane Writer", noindex=False, words=450):
    head = (
        '<meta property="og:type" content="article">'
        f'<meta name="author" content="{author}">'
        '<meta property="article:published_time" content="2025-03-01T08:00:00Z">'
    )
    if noindex:
        head += '<meta name="robots" content="noindex,follow">'
    return html(title, canonical=f"{{base}}{path}", head=head, words=words)


class FakeSite:
    def __init__(self, routes, default=(404, {}, "<html><title>Not found</title></html>")):
        self.routes = routes
        self.default = default
        self.requests: list[tuple[str, str]] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self):
                site.requests.append((self.command, self.path))
                status, headers, body = site.routes.get(self.path, site.default)
                body = body.replace("{base}", site.base) if isinstance(body, str) else body
                data = body.encode() if isinstance(body, str) else body
                self.send_response(status)
                headers = {"Content-Type": "text/html; charset=utf-8", **headers}
                for key, value in headers.items():
                    self.send_header(key, value.replace("{base}", site.base))
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = _answer
            do_HEAD = _answer
            do_POST = _answer

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def ok(body, **headers):
    return (200, headers, body)


def moved(location, status=301):
    return (status, {"Location": location}, "")


SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{}</urlset>"""


def sitemap(*paths):
    return SITEMAP.format("".join(f"<url><loc>{{base}}{p}</loc></url>" for p in paths))


LEGACY_ROUTES = {
    "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nDisallow: /private\nSitemap: {base}/sitemap.xml\n"),
    "/sitemap.xml": (200, {"Content-Type": "application/xml"}, sitemap(
        "/", "/articles/", "/articles/kept-article", "/about-us/", "/old-post", "/lifestyle/",
        "/noindexed-article", "/chain-a",
    )),
    "/": ok(html("Home", canonical="{base}/", body=(
        '<a href="/articles/">Articles</a><a href="/about-us/">About</a>'
        '<a href="/broken-link-target">Broken</a><a href="/no-canonical">No canonical</a>'
        '<a href="/private/secret">Private</a><a href="/login">Sign in</a>'
        '<a href="https://elsewhere.example.org/x">External</a><a href="mailto:a@b.c">Mail</a>'
        '<a href="/articles/?utm_source=x">Tracked</a><img src="/images/photo.jpg">'
    ))),
    "/articles/": ok(html("All articles", canonical="{base}/articles/", body=(
        '<a href="/articles/kept-article">Kept</a><a href="/articles/moved-article">Moved</a>'
        '<a href="/articles/?page=2">Next</a>'
    ))),
    "/articles/?page=2": ok(html("All articles 2", canonical="{base}/articles/?page=2", body=(
        '<a href="/articles/paged-article">Paged</a>'
    ))),
    "/articles/kept-article": ok(article("Kept article", "/articles/kept-article")),
    "/articles/moved-article": ok(article("Moved article", "/articles/moved-article")),
    "/articles/paged-article": ok(article("Paged article", "/articles/paged-article", words=120)),
    "/old-post": moved("/articles/moved-article"),
    "/chain-a": moved("/chain-b"),
    "/chain-b": moved("/articles/kept-article", 302),
    "/about-us/": ok(html("About us", canonical="{base}/about-us/")),
    "/lifestyle/": ok(html("Lifestyle", canonical="{base}/lifestyle/", head=(
        '<script type="application/ld+json">{"@type": "CollectionPage"}</script>'
    ))),
    "/noindexed-article": ok(article("Hidden by mistake", "/noindexed-article", noindex=True)),
    "/no-canonical": ok(html("No canonical")),
    "/hidden-article": ok(article("Not in the archive", "/hidden-article")),
    "/redirect-home": moved("/"),
    "/images/photo.jpg": (200, {"Content-Type": "image/jpeg"}, b"\xff\xd8\xff"),
    "/api/public/articles": (200, {"Content-Type": "application/json"}, json.dumps({"data": [
        {"id": 7, "slug": "kept-article", "title": "Kept article", "author": "Jane Writer", "status": "published"},
        {"id": 9, "slug": "lost-article", "title": "Lost article", "author": {"name": "Sam"}, "status": "published"},
        {"id": 11, "slug": "draft-article", "title": "Draft", "status": "draft"},
        {"id": 12, "slug": "no-status-article", "title": "No status"},
        {"id": 13, "slug": "draft-visible", "title": "Draft online", "status": "Draft",
         "url": "/articles/draft-visible"},
    ]})),
    "/articles/draft-visible": ok(article("Draft online", "/articles/draft-visible")),
}  # fmt: skip


@pytest.fixture()
def legacy_site():
    site = FakeSite(LEGACY_ROUTES)
    yield site
    site.close()


def run_inventory(site, tmp_path, *, seeds=(), **kwargs) -> tuple[dict, dict[str, dict]]:
    seed_file = tmp_path / "gsc-pages.csv"
    with seed_file.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Top pages", "Clicks", "Impressions"])
        for url, clicks in seeds:
            writer.writerow([site.base + url, clicks, clicks * 10])
    settings = inventory.Settings(
        base_url=site.base,
        hosts=[site.base.split("//", 1)[1]],
        starts=[site.base + "/articles/"],
        seed_files=[str(seed_file)],
        article_apis=[site.base + "/api/public/articles"],
        **kwargs,
    )
    out = tmp_path / "run"
    summary = inventory.run(settings, Fetcher(settings.hosts, delay=0, timeout=5), out)
    rows = {r["path"]: r for r in read_csv(out / "inventory.csv")}
    return summary, rows


# ---- core ------------------------------------------------------------------------------


def test_paths_are_normalised_and_classified():
    assert path_key("/about-us/") == path_key("/about-us") == "/about-us"
    assert path_key("/") == "/" and path_key("/a/?page=2#x") == "/a"
    assert classify_path("/articles/stop-comparing") == "article"
    assert classify_path("/2024/05/old-post/") == "article"
    assert classify_path("/category/mindset") == "category"
    assert classify_path("/wp-admin/") == "system" and classify_path("/login") == "system"
    assert classify_path("/uploads/a.JPG") == "media"
    assert classify_path("/50-kindness-quotes-to-brighten-your-day") == "page"


def test_csv_cells_never_start_a_spreadsheet_formula(tmp_path):
    write_csv(tmp_path / "x.csv", ["title", "n"], [{"title": "=HYPERLINK(1)", "n": -3}])
    raw = (tmp_path / "x.csv").read_text()
    assert "'=HYPERLINK(1)" in raw and ",-3" in raw
    assert read_csv(tmp_path / "x.csv")[0]["title"] == "=HYPERLINK(1)"


# ---- inventory -------------------------------------------------------------------------


def test_inventory_records_status_redirects_canonicals_and_metadata(legacy_site, tmp_path):
    summary, rows = run_inventory(
        legacy_site, tmp_path, seeds=[("/hidden-article", 4), ("/gone-page", 0)]
    )
    kept = rows["/articles/kept-article"]
    assert kept["final_status"] == "200" and kept["page_class"] == "ok"
    assert kept["kind"] == "article" and kept["canonical_status"] == "self"
    assert kept["title"] == "Kept article" and kept["meta_description"] == "About Kept article"
    assert kept["author"] == "Jane Writer" and kept["published_time"].startswith("2025-03-01")
    assert kept["in_archive"] == "yes" and kept["in_sitemap"] == "yes"
    assert "sitemap" in kept["discovered_via"] and "link" in kept["discovered_via"]

    old = rows["/old-post"]
    assert old["status"] == "301" and old["final_status"] == "200"
    assert old["final_url"].endswith("/articles/moved-article") and old["redirect_hops"] == "1"
    chain = rows["/chain-a"]
    assert chain["redirect_hops"] == "2" and "302 " in chain["redirect_chain"]
    assert {"redirect_chain", "temporary_redirect", "sitemap_lists_non_indexable"} <= set(
        chain["issues"].split(";")
    )

    assert rows["/gone-page"]["page_class"] == "gone" and rows["/gone-page"]["seed_clicks"] == ""
    assert rows["/hidden-article"]["seed_clicks"] == "4"
    assert "missing_from_archive" in rows["/hidden-article"]["issues"]
    assert rows["/articles/paged-article"]["in_archive"] == "yes"  # via ?page=2
    assert rows["/lifestyle/"]["kind"] == "category"
    assert rows["/images/photo.jpg"]["kind"] == "media"


def test_inventory_flags_broken_links_missing_canonicals_and_accidental_noindex(
    legacy_site, tmp_path
):
    _, rows = run_inventory(legacy_site, tmp_path)
    home = set(rows["/"]["issues"].split(";"))
    assert "broken_links:1" in home
    assert "linked_but_broken" in rows["/broken-link-target"]["issues"]
    assert "missing_canonical" in rows["/no-canonical"]["issues"]
    noindexed = set(rows["/noindexed-article"]["issues"].split(";"))
    assert {"noindex", "accidental_noindex", "sitemap_lists_non_indexable"} <= noindexed
    links = read_csv(tmp_path / "run" / "links.csv")
    assert any(
        row["target_url"].endswith("/broken-link-target") and row["broken"] == "yes"
        for row in links
    )


def test_inventory_is_read_only_and_stays_on_the_site(legacy_site, tmp_path):
    _, rows = run_inventory(legacy_site, tmp_path)
    methods = {method for method, _ in legacy_site.requests}
    assert methods == {"GET"}
    paths = {path for _, path in legacy_site.requests}
    assert "/private/secret" not in paths  # robots.txt Disallow
    assert "/login" not in paths  # system URLs are never requested
    assert rows["/private/secret"]["error"] == "disallowed by robots.txt"
    assert not any("elsewhere.example.org" in r["url"] for r in rows.values())
    assert not any("utm_source" in r["url"] for r in rows.values())


def test_article_records_find_missing_articles_without_inventing_urls(legacy_site, tmp_path):
    summary, rows = run_inventory(legacy_site, tmp_path)
    records = {r["slug"]: r for r in read_csv(tmp_path / "run" / "legacy-articles.csv")}
    assert records["kept-article"]["matched_url"].endswith("/articles/kept-article")
    assert records["kept-article"]["match"] == "slug"
    lost = records["lost-article"]
    assert lost["matched_url"] == "" and lost["no_public_url"] == "yes"
    assert lost["author"] == "Sam"
    assert records["draft-article"]["no_public_url"] == ""  # unpublished: not expected online
    assert records["draft-article"]["publication_status"] == "draft"
    # No explicit status: never assumed published, so never reported missing.
    unknown = records["no-status-article"]
    assert unknown["publication_status"] == "unknown" and unknown["no_public_url"] == ""
    # A draft that is publicly reachable is flagged, but not as a missing published article.
    visible = rows["/articles/draft-visible"]["issues"].split(";")
    assert "draft_record_is_public" in visible and "missing_from_archive" not in visible
    assert records["draft-visible"]["missing_from_archive"] == ""
    assert not any("lost-article" in path for path in rows)  # no URL was constructed for it
    assert summary["articles_without_public_url"] == 1


def test_single_page_app_shell_is_not_taken_as_proof_of_a_page(tmp_path):
    shell = html("Think Positive Always", canonical="{base}/")
    site = FakeSite({"/robots.txt": (404, {}, "")}, default=(200, {}, shell))
    try:
        _, rows = run_inventory(site, tmp_path, seeds=[("/articles/some-article", 2)])
    finally:
        site.close()
    assert rows["/articles/some-article"]["page_class"] == "shell_only"
    assert "shell_only" in rows["/articles/some-article"]["issues"]


# ---- mapping ---------------------------------------------------------------------------

INV_FIELDS = inventory.INVENTORY_FIELDS


def inv_file(tmp_path, name, rows, checked_at="2026-11-01T10:00:00Z"):
    full = []
    for r in rows:
        full.append({"checked_at": checked_at, "page_class": "ok", "final_status": "200",
                     "kind": classify_path(r["path"]), "url": "https://old.example.com" + r["path"], **r})  # fmt: skip
    path = tmp_path / f"{name}.csv"
    write_csv(path, INV_FIELDS, full)
    return str(path)


def new_site(tmp_path, rows):
    path = tmp_path / "new-site.csv"
    write_csv(path, ("path", "kind", "slug", "status", "original_url", "original_slug"), rows)
    return mapping.NewSite.load(path)


SITE_ROWS = [
    {"path": "/", "kind": "page", "status": "live"},
    {"path": "/about", "kind": "page", "status": "live"},
    {"path": "/articles", "kind": "page", "status": "live"},
    {"path": "/articles/kept-article", "kind": "article", "slug": "kept-article", "status": "live"},
    {"path": "/articles/moved-article", "kind": "article", "slug": "moved-article", "status": "live"},
    {"path": "/articles/50-kindness-quotes", "kind": "article", "slug": "50-kindness-quotes", "status": "live"},
    {"path": "/articles/renamed-new", "kind": "article", "slug": "renamed-new", "status": "live",
     "original_url": "https://old.example.com/2019/04/renamed-old/"},
    {"path": "/topics/lifestyle", "kind": "topic", "slug": "lifestyle", "status": "live"},
]  # fmt: skip


def map_rows(tmp_path, inventories, *, site_rows=SITE_ROWS, **kwargs):
    entries = mapping.load_inventories(inventories)
    mapper = mapping.Mapper(entries, new_site(tmp_path, site_rows), **kwargs)
    rows, excluded = mapper.rows()
    return {r["legacy_path"]: r for r in rows}, excluded, mapper


def test_mapping_keeps_existing_urls_and_redirects_only_to_matching_pages(tmp_path):
    inv = inv_file(tmp_path, "run1", [
        {"path": "/"},
        {"path": "/articles/"},
        {"path": "/articles/kept-article"},
        {"path": "/50-kindness-quotes/"},
        {"path": "/2019/04/renamed-old/"},
        {"path": "/lifestyle/", "kind": "category"},
        {"path": "/about-us/"},
        {"path": "/old-post", "final_url": "https://old.example.com/articles/moved-article"},
        {"path": "/redirected-home", "final_url": "https://old.example.com/"},
        {"path": "/article/7", "kind": "article"},
        {"path": "/brand-new-legacy-page"},
        {"path": "/login", "kind": "system"},
    ])  # fmt: skip
    articles = [{"id": "7", "slug": "kept-article", "matched_url": ""}]
    rows, excluded, _ = map_rows(tmp_path, [inv], articles=articles)
    assert (rows["/"]["action"], rows["/"]["target_path"]) == ("KEEP", "/")
    assert rows["/articles"]["action"] == "KEEP"  # trailing slash variant of a live path
    assert rows["/articles/kept-article"]["action"] == "KEEP"
    assert rows["/articles/kept-article"]["approved"] == "yes"

    def redirect(path):
        return rows[path]["action"], rows[path]["target_path"], rows[path]["confidence"]

    assert redirect("/50-kindness-quotes") == (
        "REDIRECT_301",
        "/articles/50-kindness-quotes",
        "slug",
    )
    assert redirect("/2019/04/renamed-old") == (
        "REDIRECT_301",
        "/articles/renamed-new",
        "cms_original_url",
    )
    # A new topic with the same slug is not enough: legacy taxonomy is never reused
    # automatically (see test_category_urls_move_only_by_approved_taxonomy_decision).
    assert redirect("/lifestyle") == ("REVIEW", "", "")
    assert redirect("/about-us") == ("REDIRECT_301", "/about", "rule")
    assert redirect("/old-post")[:2] == ("REDIRECT_301", "/articles/moved-article")
    assert redirect("/article/7")[:2] == ("REDIRECT_301", "/articles/kept-article")
    # Proposals still need approval; the homepage is never a fallback target.
    assert rows["/50-kindness-quotes"]["approved"] == ""
    assert (
        rows["/redirected-home"]["action"] == "REVIEW"
        and "homepage" in rows["/redirected-home"]["reason"]
    )
    assert rows["/brand-new-legacy-page"]["action"] == "REVIEW"
    assert not any(r["target_path"] == "/" for p, r in rows.items() if p != "/")
    assert {"legacy_path": "/login", "kind": "system"} in excluded


def test_slugs_are_never_regenerated(tmp_path):
    inv = inv_file(
        tmp_path, "run1", [{"path": "/articles/Kept-Article"}, {"path": "/articles/kept-articles"}]
    )
    rows, _, _ = map_rows(tmp_path, [inv])
    assert rows["/articles/Kept-Article"]["action"] == "REVIEW"  # no case folding or fuzzy matching
    assert rows["/articles/kept-articles"]["action"] == "REVIEW"


@pytest.mark.parametrize(
    ("observed", "traffic", "expected"),
    [
        (["2026-11-01"], 0, "REVIEW"),  # one 404 never retires a URL
        (["2026-11-01", "2026-11-02"], 0, "REVIEW"),  # repeated, but only a day apart
        (["2026-11-01", "2026-11-10"], 0, "RETIRE_410"),
        (["2026-11-01", "2026-11-10"], 3, "REVIEW"),  # search traffic: a person decides
    ],
)
def test_gone_urls_retire_only_on_repeated_evidence(tmp_path, observed, traffic, expected):
    runs = [
        inv_file(tmp_path, f"run{i}", [{"path": "/old-promo", "final_status": "404", "page_class": "gone",
                                        "seed_clicks": str(traffic) if traffic else ""}], f"{day}T09:00:00Z")
        for i, day in enumerate(observed)
    ]  # fmt: skip
    rows, _, _ = map_rows(tmp_path, runs)
    assert rows["/old-promo"]["action"] == expected
    assert rows["/old-promo"]["approved"] == ""


def test_gone_articles_are_never_proposed_for_retirement(tmp_path):
    runs = [
        inv_file(tmp_path, f"run{i}", [{"path": "/articles/old", "kind": "article", "final_status": "410",
                                        "page_class": "gone"}], day)
        for i, day in enumerate(["2026-10-01T00:00:00Z", "2026-11-01T00:00:00Z"])
    ]  # fmt: skip
    rows, _, _ = map_rows(tmp_path, runs)
    assert rows["/articles/old"]["action"] == "REVIEW"


def test_approved_overrides_win_and_unapproved_ones_are_ignored(tmp_path):
    inv = inv_file(tmp_path, "run1", [{"path": "/brand-new-legacy-page"}, {"path": "/other-page"}])
    overrides = [
        {"legacy_path": "/brand-new-legacy-page", "action": "REDIRECT_301", "target_path": "/about",
         "approved": "yes", "approved_by": "editor@example.com", "note": "Merged into About"},
        {"legacy_path": "/other-page", "action": "RETIRE_410", "approved": ""},
    ]  # fmt: skip
    rows, _, _ = map_rows(tmp_path, [inv], overrides=overrides)
    row = rows["/brand-new-legacy-page"]
    assert (row["action"], row["target_path"], row["confidence"]) == (
        "REDIRECT_301",
        "/about",
        "manual",
    )
    assert row["approved"] == "yes" and row["approved_by"] == "editor@example.com"
    assert rows["/other-page"]["action"] == "REVIEW"


def test_content_worklist_rewrites_published_articles_and_skips_drafts(tmp_path):
    inv = inv_file(tmp_path, "run1", [
        {"path": "/articles/long-read", "kind": "article", "word_count": "900", "author": "Jane",
         "published_time": "2024-02-02", "title": "Long read"},
        {"path": "/articles/short-note", "kind": "article", "word_count": "120"},
        {"path": "/articles/draft-leak", "kind": "article"},
        {"path": "/uploads/photo.jpg", "kind": "media"},
        {"path": "/articles/spa-only", "kind": "article", "page_class": "shell_only"},
    ])  # fmt: skip
    articles = [
        {"slug": "lost-article", "title": "Lost", "author": "Sam", "no_public_url": "yes",
         "status": "published", "source": "api"},
        {"slug": "lost-draft", "title": "Draft", "no_public_url": "yes", "status": "draft"},
        {"slug": "lost-unknown", "title": "?", "no_public_url": "yes", "status": ""},
        {"slug": "draft-leak", "status": "draft",
         "matched_url": "https://old.example.com/articles/draft-leak"},
    ]  # fmt: skip
    rows, _, mapper = map_rows(tmp_path, [inv], articles=articles)
    work = {w["keep_slug"] or w["legacy_url"]: w for w in mapper.worklist(list(rows.values()))}
    # Legacy text is never copied: published articles are rewritten from scratch.
    assert {work[s]["content_action"] for s in ("long-read", "short-note", "spa-only")} == {
        "REWRITE"
    }
    assert work["long-read"]["new_path"] == "/articles/long-read"
    assert (work["long-read"]["author"], work["long-read"]["published_time"]) == (
        "Jane",
        "2024-02-02",
    )
    assert work["https://old.example.com/uploads/photo.jpg"]["content_action"] == "IMPORT_MEDIA"
    lost = work["lost-article"]
    assert (
        lost["content_action"] == "FIND_URL" and lost["legacy_url"] == "" and lost["new_path"] == ""
    )
    # A draft (or a record without an explicit status) is never a missing published article.
    assert "lost-draft" not in work and "lost-unknown" not in work
    assert rows["/articles/draft-leak"]["content_action"] == "DRAFT_NO_ACTION"
    assert "draft-leak" not in work


# ---- validation and redirect rules -----------------------------------------------------


def codes(rows, site=None):
    return {(p["legacy_path"], p["code"]) for p in mapping.validate(rows, site)}


def test_validation_blocks_unsafe_redirects():
    rows = [
        {"legacy_path": "/a", "action": "REDIRECT_301", "target_path": "/"},
        {"legacy_path": "/b", "action": "REDIRECT_301", "target_path": "/b/"},
        {"legacy_path": "/c", "action": "REDIRECT_301", "target_path": "/d"},
        {"legacy_path": "/d", "action": "REDIRECT_301", "target_path": "/e"},
        {"legacy_path": "/x", "action": "REDIRECT_301", "target_path": "/y"},
        {"legacy_path": "/y", "action": "REDIRECT_301", "target_path": "/x"},
        {"legacy_path": "/ext", "action": "REDIRECT_301", "target_path": "https://evil.example"},
        {"legacy_path": "/none", "action": "REDIRECT_301", "target_path": ""},
        {"legacy_path": "/index.html", "action": "REDIRECT_301", "target_path": "/"},
        {"legacy_path": "/gone", "action": "RETIRE_410", "observations": "2026-11-01=404"},
        {"legacy_path": "/to-gone", "action": "REDIRECT_301", "target_path": "/gone2"},
        {"legacy_path": "/gone2", "action": "RETIRE_410", "approved": "yes"},
        {"legacy_path": "/dup/", "action": "KEEP"},
        {"legacy_path": "/dup", "action": "KEEP"},
        {"legacy_path": "/what", "action": "DELETE"},
        {"legacy_path": "/later", "action": "REVIEW"},
    ]
    found = codes(rows)
    assert ("/a", "homepage_redirect") in found
    assert ("/index.html", "homepage_redirect") not in found  # a homepage alias may
    assert ("/b", "self_redirect") in found
    assert ("/c", "redirect_chain") in found
    assert ("/x", "redirect_loop") in found
    assert ("/ext", "external_target") in found and ("/none", "missing_target") in found
    assert ("/gone", "retire_without_evidence") in found
    assert ("/gone2", "retire_without_evidence") not in found  # approved decision
    assert ("/to-gone", "redirect_to_retired") in found
    assert ("/dup", "duplicate_source") in found and ("/what", "invalid_action") in found
    problems = {p["code"]: p["severity"] for p in mapping.validate(rows)}
    assert problems["unresolved"] == "warning" and problems["homepage_redirect"] == "error"


def test_validation_checks_targets_against_the_new_site(tmp_path):
    site = new_site(tmp_path, SITE_ROWS)
    rows = [
        {"legacy_path": "/articles/kept-article", "action": "KEEP"},
        {"legacy_path": "/articles/not-imported", "action": "KEEP"},
        {"legacy_path": "/old", "action": "REDIRECT_301", "target_path": "/articles/missing"},
    ]
    found = codes(rows, site)
    assert ("/articles/not-imported", "keep_missing_on_new_site") in found
    assert ("/old", "target_missing") in found
    assert ("/articles/kept-article", "keep_missing_on_new_site") not in found


def test_nginx_410_rules_only_for_approved_safe_paths():
    text = mapping.nginx_gone_rules([
        {"legacy_path": "/old-promo", "action": "RETIRE_410", "approved": "yes"},
        {"legacy_path": "/unapproved", "action": "RETIRE_410", "approved": ""},
        {"legacy_path": "/bad;path{", "action": "RETIRE_410", "approved": "yes"},
        {"legacy_path": "/", "action": "RETIRE_410", "approved": "yes"},
    ])  # fmt: skip
    assert "location = /old-promo { return 410; }" in text
    assert "location = /old-promo/ { return 410; }" in text
    assert "unapproved" not in text and "bad" not in text and "location = / " not in text


# ---- prelaunch comparison and sitemap -----------------------------------------------------


def new_page(path, *, noindex=False):
    head = '<meta name="robots" content="noindex">' if noindex else ""
    return ok(html(path, canonical="{base}" + path, head=head))


NEW_ROUTES = {
    "/articles/kept-article": new_page("/articles/kept-article"),
    "/articles/moved-article": new_page("/articles/moved-article"),
    "/old-post": moved("{base}/articles/moved-article"),
    "/chain-x": moved("/chain-y"),
    "/chain-y": moved("/articles/kept-article"),
    "/about-us": moved("/about", 302),
    "/about": new_page("/about"),
    "/retired": (410, {}, "Gone"),
    "/noindex-page": new_page("/noindex-page", noindex=True),
    "/sitemap.xml": (200, {"Content-Type": "application/xml"},
                     sitemap("/articles/kept-article", "/old-post", "/noindex-page")),
}  # fmt: skip


@pytest.fixture()
def new_site_server():
    site = FakeSite(NEW_ROUTES)
    yield site
    site.close()


MAPPING = [
    {"legacy_path": "/articles/kept-article", "kind": "article", "action": "KEEP", "approved": "yes", "priority": "high"},
    {"legacy_path": "/old-post", "kind": "article", "action": "REDIRECT_301", "target_path": "/articles/moved-article", "approved": "yes"},
    {"legacy_path": "/chain-x", "action": "REDIRECT_301", "target_path": "/articles/kept-article", "approved": "yes"},
    {"legacy_path": "/about-us", "kind": "page", "action": "REDIRECT_301", "target_path": "/about", "approved": "yes"},
    {"legacy_path": "/retired", "action": "RETIRE_410", "approved": "yes"},
    {"legacy_path": "/old-promo", "action": "RETIRE_410", "approved": "yes"},
    {"legacy_path": "/noindex-page", "action": "KEEP", "approved": "yes"},
    {"legacy_path": "/unapproved", "action": "REDIRECT_301", "target_path": "/about"},
    {"legacy_path": "/undecided-article", "action": "REVIEW", "priority": "high"},
    {"legacy_path": "/undecided-tag", "action": "REVIEW", "priority": "normal"},
]  # fmt: skip


def test_prelaunch_comparison_checks_every_legacy_url(new_site_server):
    site = new_site_server
    fetcher = Fetcher([site.base.split("//", 1)[1]], delay=0, timeout=5)
    results = {r["legacy_path"]: r for r in verify.compare(MAPPING, site.base, fetcher)}
    assert results["/articles/kept-article"]["result"] == "pass"
    assert results["/old-post"]["result"] == "pass"
    assert results["/old-post"]["status"] == 301 and results["/old-post"]["redirect_hops"] == 1
    assert "redirect_chain" in results["/chain-x"]["problems"]
    assert "expected_301_got:302" in results["/about-us"]["problems"]
    assert results["/retired"]["result"] == "pass"
    assert (
        results["/old-promo"]["result"] == "warn"
        and "404_not_410" in results["/old-promo"]["problems"]
    )
    assert (
        "noindex" in results["/noindex-page"]["problems"]
        and results["/noindex-page"]["result"] == "fail"
    )
    assert "expected_301_got:404" in results["/unapproved"]["problems"]
    assert results["/undecided-article"]["result"] == "fail"  # high priority blocks launch
    assert results["/undecided-tag"]["result"] == "unresolved"
    lenient = {
        r["legacy_path"]: r
        for r in verify.compare(MAPPING, site.base, fetcher, strict_unresolved=False)
    }
    assert lenient["/undecided-article"]["result"] == "unresolved"
    assert {m for m, _ in site.requests} == {"GET"}


def test_sitemap_check_accepts_only_canonical_indexable_urls(new_site_server):
    site = new_site_server
    fetcher = Fetcher([site.base.split("//", 1)[1]], delay=0, timeout=5)
    results = verify.sitemap_check(site.base + "/sitemap.xml", MAPPING, fetcher)
    by_path = {r["path"]: r for r in results}
    assert by_path["/articles/kept-article"]["result"] == "pass"
    assert "legacy_redirect_source" in by_path["/old-post"]["problems"]
    assert "redirects" in by_path["/old-post"]["problems"]
    assert "noindex" in by_path["/noindex-page"]["problems"]
    assert by_path["/articles/moved-article"]["problems"] == "mapped_target_not_in_sitemap"
    assert by_path["/about"]["result"] == "warn"


def test_report_totals():
    rows = [dict(r) for r in MAPPING]
    rep = report.build(rows, excluded=2)
    assert rep["totals"] == {
        "legacy_urls_mapped": 10,
        "preserved_keep": 2,
        "redirected_301": 4,
        "redirected_301_approved": 3,
        "retired_410": 2,
        "retired_410_approved": 2,
        "unresolved_review": 2,
        "unresolved_high_priority": 1,
        "excluded_system_urls": 2,
    }
    assert "| Redirected (301) | 4 | 3 |" in report.markdown(rep)


def test_command_line_end_to_end(legacy_site, tmp_path):
    from legacy_migration.__main__ import main

    out = tmp_path / "inv"
    assert (
        main(
            [
                "inventory",
                "--base-url",
                legacy_site.base,
                "--start",
                "/articles/",
                "--delay",
                "0",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    site_csv = tmp_path / "new.csv"
    write_csv(site_csv, ("path", "kind", "slug", "status"), SITE_ROWS)
    assert main(["map", "--inventory", str(out / "inventory.csv"), "--new-site", str(site_csv),
                 "--articles", str(out / "legacy-articles.csv"), "--out", str(tmp_path / "map")]) == 0  # fmt: skip
    produced = {p.name for p in (tmp_path / "map").iterdir()}
    assert {
        "url-mapping.csv",
        "content-worklist.csv",
        "migration-report.md",
        "mapping-problems.csv",
    } <= produced
    rows = {r["legacy_path"]: r for r in read_csv(tmp_path / "map" / "url-mapping.csv")}
    assert rows["/articles/kept-article"]["action"] == "KEEP"
    assert rows["/about-us"]["target_path"] == "/about"


# ---- rewrite plan: status filtering, canonical preservation, taxonomy, suitability -------

LEGACY = "https://thinkpositivealways.com"


def export_row(id_, slug, status="published", **extra):
    return {"id": str(id_), "slug": slug, "title": extra.pop("title", f"Title {id_}"),
            "status": status, "author": "Jane", "published_at": f"2025-01-0{id_ % 9 + 1}",
            "category": extra.pop("category", "lifestyle"), **extra}  # fmt: skip


def plan_for(exports, **kwargs):
    kwargs.setdefault("base_url", LEGACY)
    return rewrite.build_plan(exports, **kwargs)


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"status": "Published"}, "published"),
        ({"status": "publish"}, "published"),
        ({"status": "draft"}, "draft"),
        ({"status": "PENDING"}, "draft"),
        ({"status": ""}, "unknown"),
        ({}, "unknown"),
        ({"status": "weird"}, "unknown"),
        ({"status": "scheduled"}, "scheduled"),
        ({"is_published": "1"}, "published"),
        ({"is_published": "false"}, "draft"),
    ],
)
def test_publication_status_is_explicit(row, expected):
    assert publication_status(row) == expected


def test_rewrite_plan_contains_published_articles_only(tmp_path):
    exports = [export_row(i, f"published-{i}") for i in range(1, 46)]
    exports += [export_row(100 + i, f"draft-{i}", "draft") for i in range(1, 45)]
    exports += [export_row(200, "no-status", ""), export_row(201, "archived", "archived")]
    plan = plan_for(exports)
    assert plan["summary"]["published"] == 45 and plan["summary"]["draft"] == 44
    assert plan["summary"]["other_status"] == 2 and plan["summary"]["records"] == 91
    assert {r["original_slug"] for r in plan["rewrite"]} == {f"published-{i}" for i in range(1, 46)}
    assert not any(r["original_slug"].startswith("draft-") for r in plan["rewrite"])
    assert all(d["note"].startswith("Draft: not rewritten") for d in plan["drafts"])
    assert {r["original_slug"] for r in plan["other_status"]} == {"no-status", "archived"}
    # The editorial plan copies no legacy text and starts every article as NOT_STARTED.
    assert set(rewrite.REWRITE_FIELDS).isdisjoint({"body", "content", "excerpt"})
    assert {r["rewrite_status"] for r in plan["rewrite"]} == {"NOT_STARTED"}
    problems = rewrite.validate_plan([{**plan["rewrite"][0], "publication_status": "draft"}])
    assert "not_published" in {p["code"] for p in problems}


def test_rewrite_plan_cli_checks_the_expected_counts(tmp_path):
    from legacy_migration.__main__ import main

    export = tmp_path / "export.csv"
    rows = [export_row(1, "a", url=f"{LEGACY}/articles/a"), export_row(2, "b", "draft")]
    write_csv(
        export, ("id", "slug", "title", "status", "author", "published_at", "category", "url"), rows
    )
    args = [
        "rewrite-plan",
        "--export",
        str(export),
        "--base-url",
        LEGACY,
        "--out",
        str(tmp_path / "plan"),
    ]
    assert main([*args, "--expect-published", "1", "--expect-draft", "1"]) == 0
    assert main([*args, "--expect-published", "45", "--expect-draft", "44"]) == 1
    produced = {p.name for p in (tmp_path / "plan").iterdir()}
    assert {"rewrite-worklist.csv", "draft-articles.csv", "other-status-articles.csv",
            "rewrite-problems.csv", "rewrite-summary.json"} <= produced  # fmt: skip
    assert [r["original_slug"] for r in read_csv(tmp_path / "plan" / "rewrite-worklist.csv")] == [
        "a"
    ]
    assert [r["original_slug"] for r in read_csv(tmp_path / "plan" / "draft-articles.csv")] == ["b"]


def inventory_rows(*rows):
    return [{"page_class": "ok", "kind": "article", **r, "path": path_of(r["url"])} for r in rows]


def test_canonical_paths_are_preserved_and_never_derived_from_titles():
    exports = [
        export_row(
            1, "kept", url=f"{LEGACY}/articles/kept", canonical_url=f"{LEGACY}/articles/kept"
        ),
        export_row(2, "root-article", url=f"{LEGACY}/root-article"),
        export_row(3, "old-slug", url=f"{LEGACY}/old-slug"),
        export_row(4, "in-inventory"),
        export_row(5, "shell-page"),
        export_row(6, "twice"),
        export_row(7, "", title="Ten Ways To Smile"),
        export_row(8, "not-online", title="Not Online"),
        export_row(9, "Bad_Slug", url=f"{LEGACY}/Bad_Slug"),
    ]
    inventory = inventory_rows(
        {"url": f"{LEGACY}/old-slug", "canonical": f"{LEGACY}/articles/established-slug"},
        {"url": f"{LEGACY}/articles/in-inventory/", "canonical": f"{LEGACY}/articles/in-inventory"},
        {
            "url": f"{LEGACY}/articles/shell-page",
            "page_class": "shell_only",
            "canonical": f"{LEGACY}/",
        },
        {"url": f"{LEGACY}/twice"},
        {"url": f"{LEGACY}/articles/twice"},
    )
    rows = {r["legacy_id"]: r for r in plan_for(exports, inventory_rows=inventory)["rewrite"]}

    def got(i):
        r = rows[str(i)]
        return r["proposed_new_path"], r["canonical_preserved"], r["url_status"]

    assert got(1) == ("/articles/kept", "yes", "EXPORT_ONLY")
    assert rows["1"]["canonical_source"] == "export"
    assert got(2) == ("/articles/root-article", "no", "EXPORT_ONLY")  # keeps its slug + one 301
    assert "301" in rows["2"]["url_note"]
    # The page's own canonical is the established URL, not the URL in the export.
    assert got(3) == ("/articles/established-slug", "yes", "CONFIRMED")
    assert rows["3"]["original_canonical_url"] == f"{LEGACY}/articles/established-slug"
    assert got(4) == ("/articles/in-inventory", "yes", "FOUND_BY_SLUG")
    # An app-shell canonical (pointing at the homepage) is not trusted.
    assert got(5) == ("/articles/shell-page", "yes", "FOUND_BY_SLUG")
    assert rows["5"]["canonical_source"] == "unverified_app_shell"
    assert got(6) == ("", "", "AMBIGUOUS") and "/articles/twice" in rows["6"]["url_candidates"]
    # No slug or URL: nothing is derived from the title.
    assert got(7) == ("", "", "FIND_URL") and "ten-ways" not in str(rows["7"])
    assert got(8) == ("", "", "FIND_URL")
    assert got(9) == ("", "no", "EXPORT_ONLY")  # not a valid new-CMS slug: needs a decision
    edited = {**rows["4"], "proposed_new_path": "/articles/in-inventory-new"}
    assert "slug_changed" in {p["code"] for p in rewrite.validate_plan([edited])}
    dupe = {**rows["3"], "legacy_id": "33"}
    assert "duplicate_new_path" in {p["code"] for p in rewrite.validate_plan([rows["3"], dupe])}


TAXONOMY_A = [
    {"legacy_category": "Lifestyle", "new_section": "everyday-wellbeing", "approved": "yes"},
    {"legacy_category": "quotes", "new_section": "affirmations", "approved": ""},  # not approved
]
TAXONOMY_B = [
    {"legacy_category": "lifestyle", "new_section": "personal-growth", "approved": "yes"},
    {"legacy_path": "/lifestyle/", "new_section": "personal-growth", "approved": "yes"},
]


def test_sections_come_only_from_editorial_taxonomy_decisions():
    exports = [export_row(1, "a", url=f"{LEGACY}/articles/a"),
               export_row(2, "b", url=f"{LEGACY}/b", category="quotes")]  # fmt: skip
    none = {r["legacy_id"]: r for r in plan_for(exports)["rewrite"]}
    assert none["1"]["proposed_section"] == "" and none["1"]["section_status"] == "NEEDS_DECISION"
    assert none["1"]["legacy_category"] == "lifestyle"  # kept for reference only
    a = {
        r["legacy_id"]: r
        for r in plan_for(exports, taxonomy=rewrite.Taxonomy(TAXONOMY_A))["rewrite"]
    }
    assert (a["1"]["proposed_section"], a["1"]["section_status"]) == (
        "everyday-wellbeing",
        "DECIDED",
    )
    assert a["2"]["proposed_section"] == ""  # unapproved decision ignored
    b = {
        r["legacy_id"]: r
        for r in plan_for(exports, taxonomy=rewrite.Taxonomy(TAXONOMY_B))["rewrite"]
    }
    assert b["1"]["proposed_section"] == "personal-growth"
    # Restructuring the taxonomy never changes a URL.
    for key in (
        "proposed_new_path",
        "canonical_preserved",
        "original_url",
        "original_canonical_url",
    ):
        assert (
            [none[i][key] for i in "12"] == [a[i][key] for i in "12"] == [b[i][key] for i in "12"]
        )


def test_category_urls_move_only_by_approved_taxonomy_decision(tmp_path):
    inv = inv_file(tmp_path, "run1", [
        {"path": "/lifestyle/", "kind": "category"},
        {"path": "/articles/kept-article", "kind": "article"},
        {"path": "/lifestyle/moved-piece", "kind": "article"},
    ])  # fmt: skip
    site_rows = [*SITE_ROWS,
                 {"path": "/topics/personal-growth", "kind": "topic", "slug": "personal-growth", "status": "live"},
                 {"path": "/articles/moved-piece", "kind": "article", "slug": "moved-piece", "status": "live"}]  # fmt: skip
    results = {}
    for name, taxonomy in (("none", None), ("a", TAXONOMY_A), ("b", TAXONOMY_B)):
        rows, _, _ = map_rows(tmp_path, [inv], site_rows=site_rows,
                              taxonomy=rewrite.Taxonomy(taxonomy) if taxonomy else None)  # fmt: skip
        results[name] = rows
    assert results["none"]["/lifestyle"]["action"] == "REVIEW"  # same-slug topic not reused
    assert results["a"]["/lifestyle"]["action"] == "REVIEW"  # decided target not live
    assert (results["b"]["/lifestyle"]["action"], results["b"]["/lifestyle"]["target_path"],
            results["b"]["/lifestyle"]["confidence"]) == ("REDIRECT_301", "/topics/personal-growth", "taxonomy")  # fmt: skip
    # Article mappings are independent of any category change.
    for path in ("/articles/kept-article", "/lifestyle/moved-piece"):
        decided = {(r[path]["action"], r[path]["target_path"]) for r in results.values()}
        assert len(decided) == 1, path
    assert results["none"]["/lifestyle/moved-piece"]["target_path"] == "/articles/moved-piece"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "How therapy helped my anxiety disorder",
            {"mental_health:anxiety disorder", "mental_health:therapy"},
        ),
        (
            "Supplements that cure insomnia",
            {"medical:supplement", "medical:cure", "medical:insomnia"},
        ),
        ("What to do before a divorce", {"legal:divorce"}),
        ("Pay off debt and start investing", {"financial:debt", "financial:investing"}),
        ("A taxi ride, a lawn and an investigation", set()),
        ("50 kindness quotes to brighten your day", set()),
    ],
)
def test_specialist_topics_are_flagged_for_expert_review(title, expected):
    assert set(rewrite.suitability_flags(title)) == expected


def test_flagged_articles_need_a_recorded_expert_decision(tmp_path):
    exports = [export_row(1, "coping-with-depression", url=f"{LEGACY}/articles/coping-with-depression",
                          title="Coping with depression"),
               export_row(2, "morning-gratitude", url=f"{LEGACY}/articles/morning-gratitude",
                          title="Morning gratitude")]  # fmt: skip
    rows = {r["legacy_id"]: r for r in plan_for(exports)["rewrite"]}
    assert rows["1"]["editorial_suitability"] == "EXPERT_REVIEW"
    assert "mental_health:depress" in rows["1"]["suitability_flags"]
    assert rows["2"]["editorial_suitability"] == "GENERAL" and rows["2"]["suitability_flags"] == ""
    codes_ = lambda r: {p["code"] for p in rewrite.validate_plan([r])}  # noqa: E731
    assert "specialist_topic_unreviewed" in codes_(
        {**rows["1"], "editorial_suitability": "GENERAL"}
    )
    assert "expert_review_pending" in codes_({**rows["1"], "rewrite_status": "READY"})
    reviewed = {**rows["1"], "rewrite_status": "READY", "suitability_decided_by": "Dr A. Reviewer"}
    assert not {"expert_review_pending", "specialist_topic_unreviewed"} & codes_(reviewed)
    assert "invalid_rewrite_status" in codes_({**rows["2"], "rewrite_status": "COPIED"})


def test_rerunning_the_plan_keeps_editor_decisions():
    exports = [export_row(1, "a", url=f"{LEGACY}/articles/a", title="Debt-free living")]
    first = plan_for(exports)["rewrite"][0]
    edited = {**first, "proposed_section": "money-mindset", "section_status": "EDITOR",
              "editorial_suitability": "EXCLUDE", "suitability_decided_by": "Editor",
              "rewrite_status": "ASSIGNED", "rewrite_owner": "Writer", "editor_notes": "Rework angle",
              "proposed_new_path": "/articles/tampered"}  # fmt: skip
    again = plan_for(exports, previous=[edited])["rewrite"][0]
    for field in rewrite.EDITOR_FIELDS:
        assert again[field] == edited[field], field
    assert again["proposed_new_path"] == "/articles/a"  # URLs are recomputed, not carried over


# ---- new CMS: export, redirect import, sitemap ---------------------------------------------


def write_mapping(tmp_path, rows):
    path = tmp_path / "url-mapping.csv"
    write_csv(path, mapping.MAPPING_FIELDS, rows)
    return str(path)


def test_import_redirects_is_a_dry_run_by_default_and_never_overwrites(seeded, tmp_path):
    app = seeded
    with app.app_context():
        slug = db.session.scalars(select(Article.slug).where(Article.status == "published")).first()
        db.session.add(Redirect(source_path="/already-there", destination="/articles/" + slug))
        db.session.commit()
    rows = [
        {"legacy_path": "/old-one", "action": "REDIRECT_301", "target_path": f"/articles/{slug}", "approved": "yes"},
        {"legacy_path": "/already-there", "action": "REDIRECT_301", "target_path": "/about", "approved": "yes"},
        {"legacy_path": f"/articles/{slug}", "action": "KEEP", "approved": "yes"},
        {"legacy_path": "/not-approved", "action": "REDIRECT_301", "target_path": "/about"},
    ]  # fmt: skip
    path = write_mapping(tmp_path, rows)
    runner = app.test_cli_runner()
    dry = runner.invoke(args=["legacy", "import-redirects", path])
    assert dry.exit_code == 0, dry.output
    assert "Dry run" in dry.output and "created 1" in dry.output and "not_approved 1" in dry.output
    with app.app_context():
        assert db.session.scalar(select(Redirect).where(Redirect.source_path == "/old-one")) is None
    applied = runner.invoke(args=["legacy", "import-redirects", path, "--apply"])
    assert applied.exit_code == 0, applied.output
    with app.app_context():
        created = db.session.scalar(select(Redirect).where(Redirect.source_path == "/old-one"))
        assert (created.destination, created.status_code, created.origin) == (
            f"/articles/{slug}",
            301,
            "import",
        )
        kept = db.session.scalar(select(Redirect).where(Redirect.source_path == "/already-there"))
        assert kept.destination == f"/articles/{slug}"  # existing redirect untouched
        assert (
            db.session.scalar(select(Redirect).where(Redirect.source_path == "/not-approved"))
            is None
        )
        assert "/old-one" not in {e["path"] for e in sitemap_entries()}


def test_import_redirects_refuses_an_invalid_mapping(seeded, tmp_path):
    path = write_mapping(tmp_path, [
        {"legacy_path": "/lots-of-old-urls", "action": "REDIRECT_301", "target_path": "/", "approved": "yes"},
    ])  # fmt: skip
    result = seeded.test_cli_runner().invoke(args=["legacy", "import-redirects", path, "--apply"])
    assert result.exit_code != 0 and "homepage_redirect" in result.output
    with seeded.app_context():
        assert (
            db.session.scalar(select(Redirect).where(Redirect.source_path == "/lots-of-old-urls"))
            is None
        )


def test_export_cms_lists_live_urls_with_original_slugs(seeded, tmp_path):
    with seeded.app_context():
        art = db.session.scalars(select(Article).where(Article.status == "published")).first()
        art.original_url, art.source = "https://thinkpositivealways.com/old-path/", "migrated"
        db.session.commit()
        slug = art.slug
    out = tmp_path / "new-site.csv"
    result = seeded.test_cli_runner().invoke(args=["legacy", "export-cms", "--out", str(out)])
    assert result.exit_code == 0, result.output
    rows = {r["path"]: r for r in read_csv(out)}
    row = rows[f"/articles/{slug}"]
    assert row["kind"] == "article" and row["status"] == "live" and row["indexable"] == "yes"
    assert row["original_url"].endswith("/old-path/") and row["source"] == "migrated"
    assert rows["/"]["indexable"] == "yes"
    site = mapping.NewSite.load(out)
    assert site.by_original_url["/old-path"] == f"/articles/{slug}"


def test_sitemap_never_lists_an_active_redirect_source(seeded):
    with seeded.app_context():
        slug = db.session.scalars(select(Article.slug).where(Article.status == "published")).first()
        assert f"/articles/{slug}" in {e["path"] for e in sitemap_entries()}
        db.session.add(Redirect(source_path=f"/articles/{slug}", destination="/about"))
        db.session.commit()
        assert f"/articles/{slug}" not in {e["path"] for e in sitemap_entries()}


def test_mapping_documentation_lists_every_column():
    doc = (Path(__file__).resolve().parents[2] / "docs" / "legacy-migration.md").read_text()
    for field in (
        *mapping.MAPPING_FIELDS,
        *inventory.INVENTORY_FIELDS,
        *mapping.WORKLIST_FIELDS,
        *rewrite.REWRITE_FIELDS,
        *rewrite.DRAFT_FIELDS,
        *rewrite.TAXONOMY_FIELDS,
        *rewrite.REWRITE_STATUSES,
        *rewrite.SUITABILITY,
    ):
        assert f"`{field}`" in doc, field
