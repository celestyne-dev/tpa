"""Search Console reconciliation and selective migration (legacy toolkit `reconcile`)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from legacy_migration import gsc, reconcile, rewrite
from legacy_migration.core import read_csv, write_csv

BASE = "https://thinkpositivealways.com"


def export_rows():
    def row(id_, slug, status, **extra):
        return {"id": str(id_), "slug": slug, "status": status, "title": extra.pop("title", slug),
                "author": "Jane", "published_at": "2025-03-01", **extra}  # fmt: skip

    return [
        row(1, "affirmations-that-feel-real", "published", category="Lifestyle",
            url=f"{BASE}/articles/affirmations-that-feel-real",
            canonical_url=f"{BASE}/articles/affirmations-that-feel-real"),
        row(2, "50-kindness-quotes-to-brighten-your-day", "published", category="Quotes"),
        row(3, "coping-with-depression", "published", title="Coping with depression",
            category="Wellbeing", section="Life", url=f"{BASE}/articles/coping-with-depression"),
        row(4, "quiet-article", "published", category="Lifestyle", url=f"{BASE}/articles/quiet-article"),
        row(5, "conflicted", "published", category="Lifestyle", url=f"{BASE}/articles/conflicted"),
        row(6, "unfinished-draft", "draft", category="Lifestyle"),
        row(7, "draft-two", "draft", category="Quotes"),
    ]  # fmt: skip


INVENTORY = [
    {"url": f"{BASE}/articles/affirmations-that-feel-real", "path": "/articles/affirmations-that-feel-real",
     "kind": "article", "page_class": "ok", "final_status": "200", "redirect_hops": "0",
     "canonical": f"{BASE}/articles/affirmations-that-feel-real", "title": "Affirmations"},
    {"url": f"{BASE}/50-kindness-quotes-to-brighten-your-day", "path": "/50-kindness-quotes-to-brighten-your-day",
     "kind": "page", "page_class": "shell_only", "final_status": "200", "canonical": f"{BASE}/"},
    {"url": f"{BASE}/about-us/", "path": "/about-us/", "kind": "page", "page_class": "ok",
     "final_status": "200", "canonical": f"{BASE}/about-us/"},
]  # fmt: skip


def write_gsc(tmp_path: Path) -> tuple[list[str], list[tuple[str, str]]]:
    perf = tmp_path / "performance.csv"
    perf.write_text(
        "Top pages,Clicks,Impressions,CTR,Position\n"
        f"{BASE}/articles/affirmations-that-feel-real,30,900,3.3%,8.1\n"
        f"{BASE}/articles/coping-with-depression,0,100,0%,40\n"
        f"https://www.thinkpositivealways.com/articles/unfinished-draft/,2,40,5%,20\n"
        f"{BASE}/lifestyle/,1,50,2%,30\n"
    )
    links = tmp_path / "links.csv"
    links.write_text(f"Target page,Incoming links,Linking sites\n{BASE}/about-us/,4,2\n")
    crawled = tmp_path / "crawled-not-indexed.csv"
    crawled.write_text(
        f"URL,Last crawled\n{BASE}/50-kindness-quotes-to-brighten-your-day,2026-10-01\n"
        f'{BASE}/quotes/,"Oct 3, 2026"\n'
    )
    indexed = tmp_path / "indexed.csv"
    indexed.write_text(f"URL,Last crawled\n{BASE}/articles/coping-with-depression,2026-10-20\n")
    gone = tmp_path / "not-found.csv"
    gone.write_text(f"URL,Last crawled\n{BASE}/old-gone-page,2026-09-01\n")
    inspection = tmp_path / "inspection.csv"
    inspection.write_text(
        "URL,Google-selected canonical,User-declared canonical\n"
        f"{BASE}/articles/conflicted,{BASE}/articles/other-page,{BASE}/articles/conflicted\n"
    )
    return [str(perf), str(links), str(inspection)], [
        ("Crawled – currently not indexed", str(crawled)),
        ("Submitted and indexed", str(indexed)),
        ("Not found (404)", str(gone)),
    ]


def run(tmp_path, **kwargs):
    files, reports = write_gsc(tmp_path)
    evidence = gsc.load(files, reports, base_url=BASE)
    kwargs.setdefault("inventory_rows", INVENTORY)
    return reconcile.reconcile(
        export_rows(), gsc=evidence, base_url=BASE, today="2026-11-03", **kwargs
    )


def by(rows, key):
    return {r[key]: r for r in rows}


# ---- Search Console parsing --------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Crawled – currently not indexed", "CRAWLED_NOT_INDEXED"),
        ("Crawled - currently not indexed", "CRAWLED_NOT_INDEXED"),
        ("Discovered – currently not indexed", "DISCOVERED_NOT_INDEXED"),
        ("Submitted and indexed", "INDEXED"),
        ("Indexed, not submitted in sitemap", "INDEXED"),
        ("Not found (404)", "NOT_FOUND_404"),
        ("Page with redirect", "PAGE_WITH_REDIRECT"),
        (
            "Duplicate, Google chose different canonical than user",
            "GOOGLE_CHOSE_DIFFERENT_CANONICAL",
        ),
        ("Excluded by ‘noindex’ tag", "NOINDEX"),
        ("Some new not indexed reason", "OTHER"),
    ],
)
def test_index_statuses_are_normalised_and_not_indexed_is_never_indexed(text, expected):
    assert gsc.normalise_index_status(text) == expected


def test_search_console_exports_become_evidence(tmp_path):
    files, reports = write_gsc(tmp_path)
    ev = gsc.load(files, reports, base_url=BASE)
    kindness = ev[f"{BASE}/50-kindness-quotes-to-brighten-your-day"]
    assert kindness["gsc_index_status"] == "CRAWLED_NOT_INDEXED"
    assert kindness["gsc_last_crawled"] == "2026-10-01"
    assert ev[f"{BASE}/quotes/"]["gsc_last_crawled"] == "2026-10-03"
    assert ev[f"{BASE}/articles/affirmations-that-feel-real"]["gsc_clicks"] == "30"
    assert ev[f"{BASE}/about-us/"]["gsc_backlinks"] == "4"
    assert (
        ev[f"{BASE}/articles/conflicted"]["gsc_google_canonical"] == f"{BASE}/articles/other-page"
    )


def test_zip_exports_read_the_issue_from_metadata_and_latest_crawl_wins(tmp_path):
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("Table.csv", f"URL,Last crawled\n{BASE}/articles/a,2026-10-05\n")
        z.writestr("Chart.csv", "Date,Not indexed\n2026-10-05,3\n")
        z.writestr("Metadata.csv", "Property,Value\nIssue,Discovered - currently not indexed\n")
    later = tmp_path / "later.csv"
    later.write_text(f"URL,Last crawled\n{BASE}/articles/a,2026-10-20\n")
    ev = gsc.load([str(archive)], [("Indexed", str(later))], base_url=BASE)[f"{BASE}/articles/a"]
    assert (ev["gsc_index_status"], ev["gsc_last_crawled"]) == ("INDEXED", "2026-10-20")
    older_last = gsc.load([], [("Indexed", str(later))], base_url=BASE)
    both = gsc.load([str(archive)], [], base_url=BASE) | older_last
    assert both[f"{BASE}/articles/a"]["gsc_index_status"] == "INDEXED"


# ---- master inventory ----------------------------------------------------------------------


def test_master_inventory_records_every_url_with_evidence(tmp_path):
    result = run(tmp_path)
    master = by(result["master"], "url_key")
    expected = {
        "/articles/affirmations-that-feel-real", "/50-kindness-quotes-to-brighten-your-day",
        "/articles/coping-with-depression", "/articles/quiet-article", "/articles/conflicted",
        "/articles/unfinished-draft", "/lifestyle", "/quotes", "/about-us", "/old-gone-page",
    }  # fmt: skip
    assert expected <= set(master)
    assert all("editorial_decision" in r for r in master.values())  # a decision field for every URL
    kindness = master["/50-kindness-quotes-to-brighten-your-day"]
    assert kindness["gsc_index_status"] == "CRAWLED_NOT_INDEXED"  # evidence, not "indexed"
    assert kindness["gsc_last_crawled"] == "2026-10-01"
    assert kindness["cms_id"] == "2" and kindness["cms_link"] == "found_by_slug"
    # www and trailing-slash variants of one URL are one row.
    draft_url = master["/articles/unfinished-draft"]
    assert draft_url["gsc_clicks"] == "2" and draft_url["cms_status"] == "draft"
    assert master["/lifestyle"]["url_type"] == "category"
    assert master["/quotes"]["url_type"] == "category"


def test_nothing_is_retired_or_selected_automatically(tmp_path):
    result = run(tmp_path)
    master = by(result["master"], "url_key")
    assert not any(r["suggested_decision"] == "RETIRE_410" for r in result["master"])
    assert not any(r["suggested_decision"] == "RETIRE_410" for r in result["register"])
    assert master["/old-gone-page"]["suggested_decision"] == "REVIEW"
    assert master["/old-gone-page"]["gsc_index_status"] == "NOT_FOUND_404"
    # Suggestions only: no article is selected and no URL decided until an editor decides.
    assert not any(r["selected"] for r in result["register"])
    assert {r["editorial_decision"] for r in result["master"]} == {"", "EXCLUDE_DRAFT"}
    register = by(result["register"], "legacy_id")
    assert register["1"]["suggested_decision"] == "REWRITE"  # clicks and impressions
    assert register["3"]["suggested_decision"] == "EXPERT_REVIEW"  # specialist topic
    assert register["2"]["suggested_decision"] == "REVIEW"  # crawled, not indexed: no value proven
    assert "not a reason to retire" in register["2"]["suggestion_reason"]
    assert result["readiness"]["production_ready"] is False


def test_historical_urls_are_kept_with_their_decisions(tmp_path):
    previous = [{"url_key": "/2019/05/old-campaign", "url": f"{BASE}/2019/05/old-campaign",
                 "url_type": "page", "editorial_decision": "RETIRE_410", "approved": "yes",
                 "decided_by": "Editor", "decision_notes": "Expired campaign, no links",
                 "first_recorded": "2026-10-01"}]  # fmt: skip
    master = by(run(tmp_path, previous_master=previous)["master"], "url_key")
    old = master["/2019/05/old-campaign"]
    assert old["still_present"] == "no" and old["editorial_decision"] == "RETIRE_410"
    assert old["first_recorded"] == "2026-10-01"
    assert master["/about-us"]["first_recorded"] == "2026-11-03"


# ---- drafts --------------------------------------------------------------------------------


def test_drafts_are_excluded_and_never_selectable(tmp_path):
    result = run(tmp_path)
    drafts = by(result["drafts"], "legacy_id")
    assert set(drafts) == {"6", "7"}
    assert {d["editorial_decision"] for d in drafts.values()} == {"EXCLUDE_DRAFT"}
    assert "search history" in drafts["6"]["note"]  # its old URL still needs a 301/410 decision
    assert not {"6", "7"} & {r["legacy_id"] for r in result["register"]}
    row = by(result["master"], "url_key")["/articles/unfinished-draft"]
    assert (row["editorial_decision"], row["decision_source"]) == ("EXCLUDE_DRAFT", "rule")
    selected_draft = [{"url_key": "/articles/unfinished-draft", "editorial_decision": "REWRITE"}]
    issues = run(tmp_path, previous_master=selected_draft)["readiness"]["issues"]
    codes = {(i["key"], i["code"], i["severity"]) for i in issues}
    assert ("/articles/unfinished-draft", "draft_selected", "blocking") in codes
    assert ("/articles/unfinished-draft", "rewrite_without_published_record", "blocking") in codes


# ---- taxonomy -----------------------------------------------------------------------------


def test_legacy_taxonomy_is_registered_but_never_recreated(tmp_path):
    result = run(tmp_path)
    tax = {(r["legacy_type"], r["legacy_slug"]): r for r in result["taxonomy"]}
    lifestyle = tax[("category", "lifestyle")]
    assert (lifestyle["published_articles"], lifestyle["draft_articles"]) == (3, 1)
    assert lifestyle["register_decision"] == "REVIEW" and lifestyle["new_section"] == ""
    assert lifestyle["legacy_urls"] == f"{BASE}/lifestyle/"
    assert ("section", "life") in tax and ("category", "quotes") in tax
    assert by(result["master"], "url_key")["/lifestyle"]["suggested_decision"] == "REVIEW"
    assert by(result["register"], "legacy_id")["1"]["proposed_section"] == ""


def test_categories_can_change_without_touching_article_urls(tmp_path):
    decisions = [
        {"legacy_category": "Lifestyle", "decision": "REPLACE", "new_section": "everyday-calm", "approved": "yes"},
        {"legacy_category": "Quotes", "decision": "RETIRE", "approved": "yes", "note": "Folded into articles"},
        {"legacy_category": "Wellbeing", "decision": "REPLACE", "new_section": "mind", "approved": ""},
    ]  # fmt: skip
    before = run(tmp_path)
    after = run(tmp_path, taxonomy=rewrite.Taxonomy(decisions))
    tax = {(r["legacy_type"], r["legacy_slug"]): r for r in after["taxonomy"]}
    assert (
        tax[("category", "lifestyle")]["register_decision"],
        tax[("category", "lifestyle")]["new_section"],
    ) == ("REPLACE", "everyday-calm")
    assert tax[("category", "quotes")]["register_decision"] == "RETIRE"
    assert tax[("category", "wellbeing")]["register_decision"] == "REVIEW"  # unapproved
    master = by(after["master"], "url_key")
    assert (master["/lifestyle"]["suggested_decision"], master["/lifestyle"]["suggested_destination"]) == (
        "REDIRECT_301", "/topics/everyday-calm")  # fmt: skip
    assert master["/lifestyle"]["editorial_decision"] == ""  # still needs an approved decision
    assert master["/quotes"]["suggested_decision"] == "REVIEW"  # retired: never an automatic 410
    assert by(after["register"], "legacy_id")["1"]["proposed_section"] == "everyday-calm"
    for field in ("original_slug", "original_url", "original_canonical_url", "proposed_new_path",
                  "canonical_preserved"):  # fmt: skip
        assert [r[field] for r in before["register"]] == [r[field] for r in after["register"]], (
            field
        )
    assert [r["proposed_new_path"] for r in before["canonical"]] == [
        r["proposed_new_path"] for r in after["canonical"]
    ]


# ---- decisions and the production gate --------------------------------------------------


def blocking(result):
    return {
        (i["key"], i["code"]) for i in result["readiness"]["issues"] if i["severity"] == "blocking"
    }


def test_redirects_need_an_approved_relevant_live_destination(tmp_path):
    def issues_for(row, new_site=None):
        result = run(
            tmp_path, previous_master=[{"url_key": "/about-us", **row}], new_site_paths=new_site
        )
        return {i["code"] for i in result["readiness"]["issues"] if i["key"] == "/about-us"}

    assert "redirect_without_destination" in issues_for({"editorial_decision": "REDIRECT_301"})
    assert "homepage_destination" in issues_for(
        {"editorial_decision": "REDIRECT_301", "destination": "/", "approved": "yes", "decided_by": "Ed"})  # fmt: skip
    assert "redirect_not_approved" in issues_for(
        {"editorial_decision": "REDIRECT_301", "destination": "/about"}
    )
    assert "destination_not_live" in issues_for(
        {"editorial_decision": "REDIRECT_301", "destination": "/about", "approved": "yes", "decided_by": "Ed"},
        new_site={"/"})  # fmt: skip
    assert issues_for(
        {"editorial_decision": "REDIRECT_301", "destination": "/about", "approved": "yes", "decided_by": "Ed"},
        new_site={"/", "/about"}) == set()  # fmt: skip
    assert "retire_without_justification" in issues_for(
        {"editorial_decision": "RETIRE_410", "approved": "yes", "decided_by": "Ed"})  # fmt: skip
    assert "preserved_page_missing" in issues_for(
        {"editorial_decision": "PRESERVE_PAGE"}, new_site={"/"}
    )
    assert "invalid_decision" in issues_for({"editorial_decision": "DELETE"})


def decided_register(**overrides):
    rows = {
        "1": {"editorial_decision": "REWRITE", "rewrite_status": "READY"},
        "2": {"editorial_decision": "REWRITE", "rewrite_status": "READY"},
        "3": {"editorial_decision": "EXPERT_REVIEW", "rewrite_status": "READY"},
        "4": {"editorial_decision": "RETIRE_410", "approved": "yes", "decided_by": "Editor",
              "decision_notes": "Thin, off-topic, no clicks or links"},
        "5": {"editorial_decision": "REWRITE", "rewrite_status": "READY"},
    }  # fmt: skip
    for key, extra in overrides.items():
        rows[key] = {**rows[key], **extra}
    return [{"legacy_id": k, **v} for k, v in rows.items()]


def test_production_is_blocked_until_selected_articles_are_resolved(tmp_path):
    result = run(tmp_path, previous_register=decided_register())
    blocked = blocking(result)
    assert ("1", "canonical_unverified") not in blocked  # live page confirms its canonical
    assert ("2", "canonical_unverified") in blocked  # app shell: needs a manual confirmation
    assert ("3", "expert_review_pending") in blocked
    assert ("3", "canonical_unverified") in blocked  # "indexed" doesn't prove the canonical
    assert ("5", "canonical_conflict") in blocked  # Google chose another canonical
    assert not any(k == "4" for k, _ in blocked)  # approved, justified retirement
    assert result["readiness"]["production_ready"] is False
    canonical = by(result["canonical"], "legacy_id")
    assert (
        canonical["1"]["outcome"] == "PRESERVED"
        and canonical["1"]["canonical_verification"] == "VERIFIED"
    )
    assert canonical["2"]["outcome"] == "UNRESOLVED"
    assert canonical["4"]["outcome"] == "NOT_SELECTED"

    resolved = run(tmp_path, previous_register=decided_register(
        **{"2": {"canonical_confirmed_by": "Editor via URL Inspection"},
           "3": {"suitability_decided_by": "Dr A. Reviewer (clinical psychologist)",
                 # Indexed in Search Console, but no live page confirms the canonical.
                 "canonical_confirmed_by": "Editor via URL Inspection"},
           "5": {"canonical_confirmed_by": "Editor: keep own canonical"}}))  # fmt: skip
    assert blocking(resolved) == set(), blocking(resolved)
    assert resolved["readiness"]["production_ready"] is True
    assert (
        resolved["readiness"]["warnings"] > 0
    )  # undecided categories/pages are listed, not blocking
    canonical = by(resolved["canonical"], "legacy_id")
    assert canonical["2"]["outcome"] == "REDIRECTED"
    assert (
        canonical["2"]["proposed_new_path"] == "/articles/50-kindness-quotes-to-brighten-your-day"
    )
    assert canonical["2"]["redirect_from"] == "/50-kindness-quotes-to-brighten-your-day"
    assert canonical["2"]["canonical_source"] == "unverified_app_shell"


def test_content_and_selection_rules_block_production(tmp_path):
    result = run(tmp_path, previous_register=decided_register(
        **{"1": {"rewrite_status": "DRAFTING"}, "4": {"editorial_decision": "REVIEW"},
           "5": {"editorial_decision": "PRESERVE_PAGE"}}))  # fmt: skip
    blocked = blocking(result)
    assert ("1", "content_not_ready") in blocked
    assert ("4", "article_undecided") in blocked
    assert ("5", "article_not_preserved") in blocked


def test_command_line_reconcile_and_gate(tmp_path):
    from legacy_migration.__main__ import main

    export = tmp_path / "export.csv"
    write_csv(export, ("id", "slug", "status", "title", "author", "published_at", "category", "section",
                       "url", "canonical_url"), export_rows())  # fmt: skip
    inventory = tmp_path / "inventory.csv"
    write_csv(inventory, ("url", "path", "kind", "page_class", "final_status", "redirect_hops",
                          "canonical", "title"), INVENTORY)  # fmt: skip
    files, reports = write_gsc(tmp_path)
    args = ["reconcile", "--export", str(export), "--inventory", str(inventory), "--base-url", BASE,
            "--out", str(tmp_path / "out")]  # fmt: skip
    for f in files:
        args += ["--gsc", f]
    for label, f in reports:
        args += ["--gsc-index", label, f]
    assert main(args) == 0
    assert main([*args, "--gate"]) == 1
    assert main([*args, "--expect-published", "45"]) == 1
    out = tmp_path / "out"
    produced = {p.name for p in out.iterdir()}
    assert {"master-url-inventory.csv", "rewrite-register.csv", "draft-exclusion-register.csv",
            "taxonomy-register.csv", "canonical-preservation-report.csv", "readiness-report.md",
            "readiness-report.json", "readiness-issues.csv"} <= produced  # fmt: skip
    assert "BLOCKED" in (out / "readiness-report.md").read_text()
    # Edited files are fed back in: decisions survive the next run.
    register = read_csv(out / "rewrite-register.csv")
    for row in register:
        row["editorial_decision"] = "REWRITE" if row["legacy_id"] == "1" else "RETIRE_410"
        row.update(
            approved="yes", decided_by="Ed", decision_notes="Not selected", rewrite_status="READY"
        )
    write_csv(out / "edited-register.csv", reconcile.REGISTER_FIELDS, register)
    assert main([*args, "--previous-register", str(out / "edited-register.csv"), "--gate"]) == 0
    again = by(read_csv(out / "rewrite-register.csv"), "legacy_id")
    assert again["1"]["editorial_decision"] == "REWRITE" and again["1"]["selected"] == "yes"


def test_documentation_lists_every_column():
    doc = (Path(__file__).resolve().parents[2] / "docs" / "legacy-migration.md").read_text()
    for field in (*reconcile.MASTER_FIELDS, *reconcile.REGISTER_EXTRA, *reconcile.DRAFT_REGISTER_FIELDS,
                  *reconcile.TAXONOMY_REGISTER_FIELDS, *reconcile.CANONICAL_FIELDS,
                  *reconcile.DECISIONS, *gsc.INDEX_STATUSES):  # fmt: skip
        assert f"`{field}`" in doc, field
