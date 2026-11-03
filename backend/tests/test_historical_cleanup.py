"""Historical URL cleanup (legacy toolkit `cleanup`, `verify-status`, `check-links`)."""

from __future__ import annotations

import io
import re
import time
import zipfile
from pathlib import Path

import pytest

from legacy_migration import cleanup, mapping, rewrite, status_check, verify
from legacy_migration.core import read_csv, write_csv
from legacy_migration.fetch import Fetcher
from tests.test_legacy_migration import FakeSite, moved, ok, sitemap

BASE = "https://thinkpositivealways.com"
ROOT = Path(__file__).resolve().parents[2]


def exports():
    def row(id_, slug, status, **extra):
        return {"id": str(id_), "slug": slug, "status": status, "title": slug, "author": "Jane",
                "published_at": "2025-01-01", **extra}  # fmt: skip

    return [
        row(1, "affirmations-that-feel-real", "published", category="lifestyle",
            url=f"{BASE}/articles/affirmations-that-feel-real",
            canonical_url=f"{BASE}/articles/affirmations-that-feel-real"),
        row(2, "50-kindness-quotes-to-brighten-your-day", "published", category="lifestyle",
            url=f"{BASE}/50-kindness-quotes-to-brighten-your-day"),
        row(7, "stop-comparing-yourself-to-others", "published", category="lifestyle",
            url=f"{BASE}/articles/stop-comparing-yourself-to-others"),
        row(20, "unfinished-draft", "draft", category="inspiration"),
        row(21, "old-draft", "draft", category="inspiration", url=f"{BASE}/articles/old-draft"),
    ]  # fmt: skip


NEW_SITE = {"/", "/articles", "/about", "/shop", "/shop/gratitude-journal", "/topics/everyday-calm"}
TAXONOMY = [
    {"legacy_category": "lifestyle", "decision": "REPLACE", "new_section": "everyday-calm", "approved": "yes"},
    {"legacy_category": "inspiration", "decision": "RETIRE", "approved": "yes"},
]  # fmt: skip


def coverage_files(tmp_path: Path) -> list[tuple[str, str]]:
    a = tmp_path / "not-found.csv"
    a.write_text("URL,Last crawled\n" + "".join(f"{BASE}{p},2026-09-0{i % 9 + 1}\n" for i, p in enumerate([
        "/forums/topic/12", "/forums/category/3", "/shop/product/9", "/article/7", "/article/999",
        "/articles/affirmations-that-feel-real", "/wp-login.php", "/cart/old-item",
        "/api/public/articles", "/lifestyle/", "/inspiration",
    ])))  # fmt: skip
    b = tmp_path / "crawled.csv"
    b.write_text("URL,Last crawled\n" + "".join(f"{u},2026-10-01\n" for u in [
        f"{BASE}/50-kindness-quotes-to-brighten-your-day",
        "http://www.thinkpositivealways.com/forums/topic/12",  # same URL as in report A
        f"{BASE}/articles?category=lifestyle", f"{BASE}/forums?page=2",
        f"{BASE}/articles/unfinished-draft", f"{BASE}/about-us/", f"{BASE}/mystery-page",
    ]))  # fmt: skip
    c = tmp_path / "redirects.zip"
    with zipfile.ZipFile(c, "w") as z:
        z.writestr("Table.csv", f"URL,Last crawled\n{BASE}/articles/old-draft,2026-08-01\n"
                                f"{BASE}/shop/gratitude-journal?utm_source=x,2026-08-02\n")  # fmt: skip
        z.writestr("Metadata.csv", "Property,Value\nIssue,Page with redirect\n")
    d = tmp_path / "indexed.csv"
    d.write_text("URL,Last crawled\n" + "".join(f"{BASE}{p},2026-10-10\n" for p in [
        "/", "/admin/dashboard", "/articles/stop-comparing-yourself-to-others",
    ]))  # fmt: skip
    return [("Not found (404)", str(a)), ("Crawled – currently not indexed", str(b)),
            ("", str(c)), ("Indexed", str(d))]  # fmt: skip


def context():
    return cleanup.Context(exports(), new_site_paths=NEW_SITE, taxonomy=rewrite.Taxonomy(TAXONOMY),
                           base_url=BASE)  # fmt: skip


def run(tmp_path, previous=None):
    coverage, counts = cleanup.load_coverage(coverage_files(tmp_path), BASE)
    ctx = context()
    result = cleanup.cleanup(coverage, ctx, previous=previous)
    return result, ctx, counts


def rows_by_path(result):
    return {r["path"]: r for r in result["rows"]}


# ---- import ---------------------------------------------------------------------------


def test_coverage_reports_are_imported_and_deduplicated(tmp_path):
    coverage, counts = cleanup.load_coverage(coverage_files(tmp_path), BASE)
    assert counts["rows"] == 23
    assert counts["distinct_urls"] == 22  # http://www. spelling merged into one URL
    assert counts["query_variants"] == 3
    forum = coverage[f"{BASE}/forums/topic/12"]
    assert forum["reports"] == {"Not found (404)", "Crawled – currently not indexed"}
    assert forum["statuses"] == {"NOT_FOUND_404", "CRAWLED_NOT_INDEXED"}
    assert forum["last_crawled"] == "2026-10-01"
    assert coverage[f"{BASE}/articles/old-draft"]["reports"] == {
        "Page with redirect"
    }  # from metadata


# ---- classification -----------------------------------------------------------------


def test_historical_urls_are_classified(tmp_path):
    result, _ctx, _ = run(tmp_path)
    r = rows_by_path(result)

    def got(path):
        return r[path]["family"], r[path]["proposed_class"], r[path]["proposed_target"]

    assert got("/forums/topic/12") == ("forum", "RETIRE_410", "")
    assert got("/forums?page=2")[1:] == ("RETIRE_410", "")  # follows its path
    assert got("/shop/product/9") == ("shop_account", "RETIRE_410", "")
    assert got("/shop/gratitude-journal?utm_source=x")[1] == "KEEP_200"
    assert got("/article/7") == (
        "previous_article_route",
        "REDIRECT_301",
        "/articles/stop-comparing-yourself-to-others",
    )
    assert got("/article/999") == ("previous_article_route", "ALLOW_404", "")
    assert got("/lifestyle/") == ("category", "REDIRECT_301", "/topics/everyday-calm")
    assert got("/inspiration") == ("category", "RETIRE_410", "")
    assert got("/articles?category=lifestyle") == ("filter", "KEEP_200", "")
    assert got("/about-us/") == ("page", "REDIRECT_301", "/about")
    assert got("/admin/dashboard") == ("app_shell", "KEEP_200", "")
    assert got("/wp-login.php")[1:] == ("ALLOW_404", "")
    assert got("/api/public/articles") == ("api", "ALLOW_404", "")
    assert got("/cart/old-item") == ("shop_account", "ALLOW_404", "")
    assert got("/") == ("home", "KEEP_200", "")
    # "Crawled - currently not indexed" alone never retires anything.
    assert got("/mystery-page") == ("page", "REVIEW", "")


def test_published_articles_and_canonical_urls_are_protected(tmp_path):
    result, ctx, _ = run(tmp_path)
    r = rows_by_path(result)
    kept = r["/articles/affirmations-that-feel-real"]  # listed in a 404 report: still kept
    assert (kept["family"], kept["proposed_class"], kept["effective_class"]) == (
        "current_article",
        "KEEP_200",
        "KEEP_200",
    )
    assert kept["protected"] and kept["cms_id"] == "1"
    moved_ = r["/50-kindness-quotes-to-brighten-your-day"]
    assert (moved_["proposed_class"], moved_["proposed_target"]) == (
        "REDIRECT_301", "/articles/50-kindness-quotes-to-brighten-your-day")  # fmt: skip
    assert "/articles/50-kindness-quotes-to-brighten-your-day" in ctx.planned_paths
    assert r["/articles/stop-comparing-yourself-to-others"]["effective_class"] == "KEEP_200"
    assert len(ctx.plan) == 3  # every published article, none dropped
    # No proposal ever retires or 404s a published article URL.
    for row in result["rows"]:
        if row["family"] == "current_article":
            assert row["proposed_class"] in ("KEEP_200", "REDIRECT_301", "REVIEW"), row["path"]


def test_drafts_are_never_published(tmp_path):
    result, _ctx, _ = run(tmp_path)
    r = rows_by_path(result)
    for path in ("/articles/unfinished-draft", "/articles/old-draft"):
        assert (r[path]["family"], r[path]["proposed_class"]) == ("draft", "ALLOW_404"), path
        assert r[path]["cms_status"] == "draft"
    bad, *_ = run(
        tmp_path, previous=[{"url": f"{BASE}/articles/unfinished-draft", "decision": "KEEP_200"}]
    )
    assert "draft_published" in {p["code"] for p in bad["problems"]}


def test_nothing_takes_effect_without_approval(tmp_path):
    result, *_ = run(tmp_path)
    effective = {r["effective_class"] for r in result["rows"]}
    assert "REDIRECT_301" not in effective and "RETIRE_410" not in effective
    approved = run(tmp_path, previous=[
        {"url": f"{BASE}/forums/topic/12", "decision": "RETIRE_410", "approved": "yes"},  # no approver
        {"url": f"{BASE}/about-us/", "decision": "REDIRECT_301", "target": "/about", "approved": "yes",
         "approved_by": "Editor"},
    ])[0]  # fmt: skip
    r = rows_by_path(approved)
    assert r["/forums/topic/12"]["effective_class"] == "REVIEW"
    assert (r["/about-us/"]["effective_class"], r["/about-us/"]["effective_target"]) == (
        "REDIRECT_301",
        "/about",
    )


# ---- validation ---------------------------------------------------------------------


def problems_for(tmp_path, decisions):
    previous = [{"url": f"{BASE}{path}", "approved": "yes", "approved_by": "Ed", **d}
                for path, d in decisions.items()]  # fmt: skip
    result, *_ = run(tmp_path, previous=previous)
    return {(p["path_key"], p["code"]) for p in result["problems"] if p["severity"] == "error"}


def test_protected_and_essential_routes_reject_cleanup_rules(tmp_path):
    found = problems_for(tmp_path, {
        "/articles/affirmations-that-feel-real": {"decision": "RETIRE_410"},
        "/50-kindness-quotes-to-brighten-your-day": {"decision": "ALLOW_404"},
        "/article/7": {"decision": "REDIRECT_301", "target": "/about"},
        "/articles?category=lifestyle": {"decision": "RETIRE_410"},
        "/": {"decision": "REDIRECT_301", "target": "/about"},
        "/api/public/articles": {"decision": "RETIRE_410"},
        "/admin/dashboard": {"decision": "REDIRECT_301", "target": "/about"},
        "/shop/gratitude-journal?utm_source=x": {"decision": "RETIRE_410"},
    })  # fmt: skip
    assert ("/articles/affirmations-that-feel-real", "protected_url") in found
    assert ("/50-kindness-quotes-to-brighten-your-day", "protected_url") in found
    assert ("/articles", "essential_route") in found  # a query variant can't retire the page
    assert ("/", "essential_route") in found
    assert ("/api/public/articles", "app_area") in found
    assert ("/admin/dashboard", "app_area") in found
    assert ("/shop/gratitude-journal", "essential_route") in found


@pytest.mark.parametrize(
    "path",
    ["/articles/page/3", "/topics/mindset/page/2", "/authors/jane-doe", "/authors/jane-doe/page/2"],
)
def test_generated_listing_and_author_pages_never_get_cleanup_rules(path):
    """The technical release's new pages: an exact-path 410 rule would shadow them."""
    assert cleanup._app_area(path)
    errors = cleanup.verify_snippet(cleanup.gone_snippet([path]), context(), [path])
    assert any("application area" in e for e in errors), errors


def test_search_and_feed_are_essential_and_ordinary_paths_unaffected():
    assert {"/search", "/feed.xml"} <= cleanup.ESSENTIAL_PATHS
    for path in ("/page/3", "/articles/some-old-post", "/topics/mindset", "/author/jane"):
        assert cleanup._app_area(path) is False, path


def test_redirects_are_direct_and_relevant(tmp_path):
    found = problems_for(tmp_path, {
        "/mystery-page": {"decision": "REDIRECT_301", "target": "/"},
        "/forums/category/3": {"decision": "REDIRECT_301", "target": "/forums/topic/12"},
        "/forums/topic/12": {"decision": "RETIRE_410"},
        "/shop/product/9": {"decision": "REDIRECT_301", "target": "/shop/old-thing"},
        "/about-us/": {"decision": "REDIRECT_301", "target": "/about-us"},
        "/article/999": {"decision": "REDIRECT_301", "target": "https://evil.example/x"},
        "/50-kindness-quotes-to-brighten-your-day": {"decision": "REDIRECT_301", "target": "/articles/elsewhere"},
    })  # fmt: skip
    assert ("/mystery-page", "homepage_redirect") in found
    assert ("/forums/category/3", "redirect_chain") in found
    assert ("/shop/product/9", "target_not_live") in found
    assert ("/about-us", "self_redirect") in found
    assert ("/article/999", "redirect_target") in found
    assert ("/50-kindness-quotes-to-brighten-your-day", "protected_target") in found


def test_query_variants_follow_their_path(tmp_path):
    conflict = problems_for(tmp_path, {
        "/forums/topic/12": {"decision": "RETIRE_410"},
        "/forums?page=2": {"decision": "RETIRE_410"},
    })  # fmt: skip
    assert not any(code == "variant_conflict" for _, code in conflict)
    result, ctx, _ = run(tmp_path, previous=[
        {"url": f"{BASE}/forums?page=2", "decision": "RETIRE_410", "approved": "yes", "approved_by": "Ed"}])  # fmt: skip
    _, gone = cleanup.approved_rules(result["rows"], result["problems"])
    assert gone == ["/forums"]  # the path rule covers every query string


# ---- Nginx 410 snippet ----------------------------------------------------------------


APPROVED_GONE = {
    "/forums/topic/12": {"decision": "RETIRE_410"},
    "/forums/category/3": {"decision": "RETIRE_410"},
    "/forums?page=2": {"decision": "RETIRE_410"},
    "/inspiration": {"decision": "RETIRE_410"},
    "/about-us/": {"decision": "REDIRECT_301", "target": "/about"},
    "/article/7": {"decision": "REDIRECT_301", "target": "/articles/stop-comparing-yourself-to-others"},
}  # fmt: skip


def write_cleanup(tmp_path, decisions):
    previous = [
        {"url": f"{BASE}{p}", "approved": "yes", "approved_by": "Ed", **d}
        for p, d in decisions.items()
    ]
    coverage, counts = cleanup.load_coverage(coverage_files(tmp_path), BASE)
    ctx = context()
    result = cleanup.cleanup(coverage, ctx, previous=previous)
    out = tmp_path / "out"
    return cleanup.write(out, result, ctx, counts), out


def test_nginx_snippet_has_exact_rules_for_approved_paths_only(tmp_path):
    summary, out = write_cleanup(tmp_path, APPROVED_GONE)
    assert summary["nginx_snippet"] == "verified"
    text = (out / "tpa-legacy-gone.conf").read_text()
    rules = [line for line in text.splitlines() if not line.startswith("#")]
    assert rules == [
        "location = /forums { return 410; }", "location = /forums/ { return 410; }",
        "location = /forums/category/3 { return 410; }", "location = /forums/category/3/ { return 410; }",
        "location = /forums/topic/12 { return 410; }", "location = /forums/topic/12/ { return 410; }",
        "location = /inspiration { return 410; }", "location = /inspiration/ { return 410; }",
    ]  # fmt: skip
    assert not re.search(r"location (~|\^~|/)", text)  # no regex or prefix rules
    assert "/shop/product/9" not in text  # proposed but never approved
    redirects = read_csv(out / "approved-redirects.csv")
    assert {(r["legacy_path"], r["target_path"]) for r in redirects} == {
        ("/about-us", "/about"), ("/article/7", "/articles/stop-comparing-yourself-to-others")}  # fmt: skip
    assert mapping.validate(redirects) == []  # ready for `flask legacy import-redirects` (dry run)
    assert summary["redirected_301"] == 2 and summary["retired_410"] == 4


def test_snippet_is_refused_when_a_410_rule_is_unsafe(tmp_path):
    summary, out = write_cleanup(tmp_path, {**APPROVED_GONE,
                                            "/articles/affirmations-that-feel-real": {"decision": "RETIRE_410"}})  # fmt: skip
    assert summary["nginx_snippet"] == "refused" and not (out / "tpa-legacy-gone.conf").exists()
    ctx = context()
    bad = cleanup.gone_snippet(["/articles"]) + "location /forums { return 410; }\n"
    errors = cleanup.verify_snippet(bad, ctx, ["/articles"])
    assert any("protected or live" in e for e in errors) and any(
        "not an exact" in e for e in errors
    )


def test_cleanup_summary_counts_every_outcome(tmp_path):
    summary, out = write_cleanup(tmp_path, APPROVED_GONE)
    assert summary["urls"] == 22
    assert (summary["preserved_200"] + summary["redirected_301"] + summary["retired_410"]
            + summary["left_404"] + summary["unresolved"]) == 22  # fmt: skip
    assert summary["left_404"] >= 6 and summary["unresolved"] >= 1
    assert summary["ready_for_staging"] is False  # unresolved URLs remain
    assert "| Retired (410, approved) | 4 |" in (out / "cleanup-summary.md").read_text()


def test_command_line_cleanup(tmp_path):
    from legacy_migration.__main__ import main

    export = tmp_path / "export.csv"
    write_csv(export, ("id", "slug", "status", "title", "author", "published_at", "category", "url",
                       "canonical_url"), exports())  # fmt: skip
    new_site = tmp_path / "new-site.csv"
    write_csv(
        new_site,
        ("path", "kind", "status"),
        [{"path": p, "kind": "page", "status": "live"} for p in NEW_SITE],
    )
    taxonomy = tmp_path / "taxonomy.csv"
    write_csv(taxonomy, rewrite.TAXONOMY_FIELDS, TAXONOMY)
    args = ["cleanup", "--export", str(export), "--new-site", str(new_site), "--taxonomy", str(taxonomy),
            "--out", str(tmp_path / "out")]  # fmt: skip
    for label, f in coverage_files(tmp_path):
        args += ["--coverage-report", label, f] if label else ["--coverage", f]
    assert main([*args, "--expect-urls", "22", "--expect-published", "3"]) == 0
    assert main([*args, "--expect-urls", "865"]) == 1
    assert main([*args, "--gate"]) == 1  # unresolved URLs: not ready for staging
    produced = {p.name for p in (tmp_path / "out").iterdir()}
    assert {"cleanup-decisions.csv", "cleanup-problems.csv", "cleanup-summary.md", "cleanup-summary.json",
            "approved-redirects.csv", "cleanup-mapping.csv", "tpa-legacy-gone.conf"} <= produced  # fmt: skip


# ---- read-only status verification ------------------------------------------------------


def staging_routes():
    page = "<html><head><title>{t}</title><link rel='canonical' href='{{base}}{t}'></head></html>"
    return {
        "/articles/affirmations-that-feel-real": ok(page.format(t="/articles/affirmations-that-feel-real")),
        "/about-us": moved("/about"), "/about-us/": moved("/about"),
        "/about": ok(page.format(t="/about")),
        "/forums/topic/12": (410, {}, "Gone"),
        "/slow": (200, {}, "slow"),
    }  # fmt: skip


def status_rows():
    return [
        {"url": f"{BASE}/articles/affirmations-that-feel-real", "effective_class": "KEEP_200"},
        {
            "url": f"{BASE}/about-us/",
            "effective_class": "REDIRECT_301",
            "effective_target": "/about",
        },
        {"url": f"{BASE}/forums/topic/12", "effective_class": "RETIRE_410"},
        {"url": f"{BASE}/article/999", "effective_class": "ALLOW_404"},
        {"url": f"{BASE}/mystery-page", "effective_class": "REVIEW"},
        {"url": "https://other.example.org/x", "effective_class": "REVIEW"},
    ]


def test_status_checks_are_read_only_resumable_and_report_progress(tmp_path):
    site = FakeSite(staging_routes())
    try:
        out, log = tmp_path / "status.csv", io.StringIO()
        fetcher = Fetcher([site.base.split("//", 1)[1]], delay=0, timeout=2)
        first = status_check.run(status_rows(), site.base, out, expect=True, limit=2, progress_every=1,
                                 fetcher=fetcher, log=log, site_hosts=["thinkpositivealways.com"])  # fmt: skip
        assert (first["checked"], first["remaining"], first["complete"]) == (2, 4, False)
        assert "[1/6]" in log.getvalue() and "run again to resume" in log.getvalue()
        second = status_check.run(
            status_rows(),
            site.base,
            out,
            expect=True,
            fetcher=fetcher,
            log=log,
            site_hosts=["thinkpositivealways.com"],
        )
        assert (second["already_done"], second["checked"], second["complete"]) == (2, 4, True)
        results = {r["url"].replace(BASE, ""): r for r in read_csv(out)}
        assert len(read_csv(out)) == 6  # nothing checked twice
        assert results["/articles/affirmations-that-feel-real"]["result"] == "pass"
        assert (
            results["/about-us/"]["result"] == "pass" and results["/about-us/"]["status"] == "301"
        )
        assert results["/forums/topic/12"]["result"] == "pass"
        assert results["/article/999"]["result"] == "pass"  # genuine 404
        assert results["/mystery-page"]["result"] == "info"
        assert results["https://other.example.org/x"]["result"] == "skipped"
        assert {m for m, _ in site.requests} == {"GET"}
    finally:
        site.close()


def test_status_check_flags_soft_404s(tmp_path):
    shell = "<html><head><title>Think Positive Always</title></head><body></body></html>"
    site = FakeSite({}, default=(200, {}, shell))  # an SPA answering 200 to everything
    try:
        fetcher = Fetcher([site.base.split("//", 1)[1]], delay=0, timeout=2)
        rows = [{"url": f"{BASE}/article/999", "effective_class": "ALLOW_404"},
                {"url": f"{BASE}/articles/affirmations-that-feel-real", "effective_class": "KEEP_200"}]  # fmt: skip
        summary = status_check.run(rows, site.base, tmp_path / "s.csv", expect=True, fetcher=fetcher,
                                   log=io.StringIO(), site_hosts=["thinkpositivealways.com"])  # fmt: skip
        assert summary["unknown_urls_answer_200"] is True and summary["fail"] == 2
        results = {r["url"].replace(BASE, ""): r for r in read_csv(tmp_path / "s.csv")}
        assert "genuine 404" in results["/article/999"]["problem"]
        assert (
            results["/articles/affirmations-that-feel-real"]["matches_unknown_url_response"]
            == "yes"
        )
    finally:
        site.close()


def test_status_checks_have_bounded_timeouts(tmp_path):
    import socket

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(5)  # accepts connections but never answers
    port = server.getsockname()[1]
    try:
        fetcher = Fetcher([f"127.0.0.1:{port}"], delay=0, timeout=0.5)
        rows = [{"url": f"{BASE}/a"}, {"url": f"{BASE}/b"}, {"url": f"{BASE}/c"}]
        started = time.monotonic()
        summary = status_check.run(rows, f"http://127.0.0.1:{port}", tmp_path / "t.csv",
                                   fetcher=fetcher, max_seconds=1, log=io.StringIO(),
                                   site_hosts=["thinkpositivealways.com"])  # fmt: skip
        assert time.monotonic() - started < 5
        assert summary["error"] >= 1 and not summary["complete"]
        assert all(r["result"] == "error" for r in read_csv(tmp_path / "t.csv"))
    finally:
        server.close()


def test_prelaunch_compare_and_sitemap_understand_allowed_404(tmp_path):
    site = FakeSite({
        "/sitemap.xml": (200, {"Content-Type": "application/xml"}, sitemap("/about", "/article/999")),
        "/about": ok("<html><head><link rel='canonical' href='{base}/about'></head></html>"),
        "/article/999": ok("<html><head><link rel='canonical' href='{base}/article/999'></head></html>"),
    })  # fmt: skip
    try:
        fetcher = Fetcher([site.base.split("//", 1)[1]], delay=0, timeout=2)
        rows = [{"legacy_path": "/article/999", "action": "ALLOW_404"},
                {"legacy_path": "/gone-for-real", "action": "ALLOW_404"}]  # fmt: skip
        results = {r["legacy_path"]: r for r in verify.compare(rows, site.base, fetcher)}
        assert results["/article/999"]["result"] == "fail"  # answers 200
        assert results["/gone-for-real"]["result"] == "pass"
        checked = {
            r["path"]: r for r in verify.sitemap_check(site.base + "/sitemap.xml", rows, fetcher)
        }
        assert "allowed_404_path" in checked["/article/999"]["problems"]
        assert checked["/about"]["result"] == "pass"
    finally:
        site.close()


# ---- essential routes stay in sync ------------------------------------------------------


def test_essential_routes_cover_the_new_sites_routes():
    from app.services.seo_service import STATIC_PATHS

    assert {p for p, _, _ in STATIC_PATHS} <= cleanup.ESSENTIAL_PATHS
    nav = (ROOT / "frontend" / "src" / "config" / "navigation.js").read_text()
    routes = set(re.findall(r':\s*"(/[^"]*)"', nav.split("export const legacyAuthRoutes")[0]))
    assert routes
    for route in routes:
        assert route in cleanup.ESSENTIAL_PATHS or cleanup._starts(
            route, cleanup.NO_RULE_PREFIXES
        ), route


# ---- links and navigation (new CMS, read-only) ---------------------------------------------


def test_check_links_reports_legacy_urls_in_content(seeded, tmp_path):
    from sqlalchemy import select

    from app.extensions import db
    from app.models import Article, Topic

    decisions = tmp_path / "cleanup-decisions.csv"
    write_csv(decisions, ("url", "path_key", "effective_class", "effective_target"), [
        {"url": f"{BASE}/forums/topic/12", "path_key": "/forums/topic/12", "effective_class": "RETIRE_410"},
        {"url": f"{BASE}/about-us/", "path_key": "/about-us", "effective_class": "REDIRECT_301",
         "effective_target": "/about"},
        {"url": f"{BASE}/article/7", "path_key": "/article/7", "effective_class": "REDIRECT_301",
         "effective_target": "/articles/x"},
        {"url": f"{BASE}/articles", "path_key": "/articles", "effective_class": "KEEP_200"},
    ])  # fmt: skip
    runner = seeded.test_cli_runner()
    clean = runner.invoke(args=["legacy", "check-links", str(decisions)])
    assert clean.exit_code == 0, clean.output  # default menus and sample content are clean
    with seeded.app_context():
        art = db.session.scalars(select(Article).where(Article.status == "published")).first()
        art.body = [*art.body, {"type": "button", "label": "Forum", "href": "/forums/topic/12"},
                    {"type": "paragraph", "text": f"See [our story]({BASE}/about-us/) and "
                     f'<a href="{BASE}/article/7">this</a>, or [all articles](/articles).'}]  # fmt: skip
        topic = db.session.scalars(select(Topic)).first()
        topic.intro = "Older posts live [here](/about-us)."
        db.session.commit()
        slug = art.slug
    result = runner.invoke(args=["legacy", "check-links", str(decisions)])
    assert result.exit_code == 1
    assert f"article:{slug}: /forums/topic/12 is RETIRE_410 -> remove the link" in result.output
    assert f"article:{slug}: {BASE}/about-us/ is REDIRECT_301 -> link to /about" in result.output
    assert "/article/7 is REDIRECT_301" in result.output
    assert "/articles is" not in result.output.replace("/articles/x", "")
    assert "topic:" in result.output and "4 link(s)" in result.output


def test_documentation_lists_every_column():
    doc = (ROOT / "docs" / "legacy-migration.md").read_text()
    for field in (*cleanup.DECISION_FIELDS, *status_check.RESULT_FIELDS, *cleanup.CLASSES):
        assert f"`{field}`" in doc, field


@pytest.mark.parametrize("path", ["/", "/articles", "/topics", "/shop", "/about", "/sitemap.xml"])
def test_essential_routes_are_never_retired(path):
    ctx = context()
    assert path in cleanup.ESSENTIAL_PATHS
    assert cleanup.verify_snippet(cleanup.gone_snippet([path]), ctx, [path])
