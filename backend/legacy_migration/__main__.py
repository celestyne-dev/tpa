"""Command line: ``python -m legacy_migration <step> --help`` (run from backend/)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from . import inventory as inv
from . import mapping, report, rewrite, verify
from .core import read_csv, write_csv
from .fetch import Fetcher


def _hosts(base: str, extra: list[str]) -> list[str]:
    host = urlsplit(base).netloc
    return [host, *extra]


def cmd_inventory(a) -> int:
    settings = inv.Settings(
        base_url=a.base_url.rstrip("/"),
        hosts=_hosts(a.base_url, a.host),
        starts=a.start,
        sitemaps=a.sitemap,
        seed_files=a.seeds,
        article_csvs=a.articles_csv,
        article_apis=a.articles_api,
        max_pages=a.max_pages,
        follow_links=not a.no_follow,
        respect_robots=not a.ignore_robots,
        check_media=not a.skip_media,
    )
    fetcher = Fetcher(settings.hosts, delay=a.delay, timeout=a.timeout)
    summary = inv.run(settings, fetcher, a.out)
    print(json.dumps(summary, indent=2))
    return 0


def cmd_map(a) -> int:
    entries = mapping.load_inventories(a.inventory)
    site = mapping.NewSite.load(a.new_site)
    articles = [r for path in a.articles for r in read_csv(path)]
    overrides = [r for path in a.overrides for r in read_csv(path)]
    mapper = mapping.Mapper(
        entries,
        site,
        articles=articles,
        overrides=overrides,
        aliases=mapping.load_aliases(a.aliases),
        retire_min_observations=a.retire_min_observations,
        retire_min_days=a.retire_min_days,
        taxonomy=rewrite.load_taxonomy(a.taxonomy),
    )
    rows, excluded = mapper.rows()
    out = Path(a.out)
    mapping.write_mapping(out / "url-mapping.csv", rows)
    work = mapper.worklist(rows)
    mapping.write_worklist(out / "content-worklist.csv", work)
    write_csv(out / "excluded-urls.csv", ("legacy_path", "kind"), excluded)
    problems = mapping.validate([dict(r) for r in rows], site)
    write_csv(
        out / "mapping-problems.csv", ("legacy_path", "severity", "code", "message"), problems
    )
    inventory_rows = read_csv(a.inventory[0])
    rep = report.build(
        rows, inventory=inventory_rows, worklist=work, problems=problems, excluded=len(excluded)
    )
    (out / "migration-report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    (out / "migration-report.md").write_text(report.markdown(rep), encoding="utf-8")
    print(report.markdown(rep))
    return 0


def cmd_rewrite_plan(a) -> int:
    exports = [r for path in a.export for r in read_csv(path)]
    plan = rewrite.build_plan(
        exports,
        inventory_rows=read_csv(a.inventory) if a.inventory else None,
        taxonomy=rewrite.load_taxonomy(a.taxonomy),
        previous=read_csv(a.previous) if a.previous else None,
        base_url=a.base_url,
    )
    out = Path(a.out)
    rewrite.write(out, plan)
    problems = rewrite.validate_plan(plan["rewrite"])
    write_csv(out / "rewrite-problems.csv", ("legacy_id", "severity", "code", "message"), problems)
    summary = {**plan["summary"], "problems": dict(Counter(p["code"] for p in problems))}
    (out / "rewrite-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    failed = False
    for label, expected in (("published", a.expect_published), ("draft", a.expect_draft)):
        if expected is not None and summary[label] != expected:
            print(f"Expected {expected} {label} records, found {summary[label]}.", file=sys.stderr)
            failed = True
    errors = sum(1 for p in problems if p["severity"] == "error")
    return 1 if failed or errors else 0


def cmd_reconcile(a) -> int:
    from . import gsc, reconcile

    base = a.base_url.rstrip("/")
    evidence = gsc.load(a.gsc, [(label, path) for label, path in a.gsc_index], base_url=base)
    new_site = set(mapping.NewSite.load(a.new_site).paths) if a.new_site else None
    result = reconcile.reconcile(
        [r for path in a.export for r in read_csv(path)],
        inventory_rows=[r for path in a.inventory for r in read_csv(path)],
        gsc=evidence,
        taxonomy=rewrite.load_taxonomy(a.taxonomy),
        previous_master=read_csv(a.previous_master) if a.previous_master else None,
        previous_register=read_csv(a.previous_register) if a.previous_register else None,
        new_site_paths=new_site,
        base_url=base,
    )
    reconcile.write(a.out, result)
    report = result["readiness"]
    print(reconcile.markdown({**report, "issues": []}))
    if a.expect_published is not None and report["published_articles"] != a.expect_published:
        print(f"Expected {a.expect_published} published articles, found "
              f"{report['published_articles']}.", file=sys.stderr)  # fmt: skip
        return 1
    return 1 if a.gate and not report["production_ready"] else 0


def cmd_cleanup(a) -> int:
    from . import cleanup

    base = a.base_url.rstrip("/")
    files = [("", f) for f in a.coverage] + [(label, f) for label, f in a.coverage_report]
    coverage, counts = cleanup.load_coverage(files, base)
    if a.expect_urls is not None and counts["distinct_urls"] != a.expect_urls:
        print(f"Expected {a.expect_urls} distinct URLs, found {counts['distinct_urls']}.",
              file=sys.stderr)  # fmt: skip
        return 1
    routes = set()
    for path in a.routes:
        routes |= {line.strip() for line in Path(path).read_text().splitlines()
                   if line.strip().startswith("/")}  # fmt: skip
    ctx = cleanup.Context(
        [r for path in a.export for r in read_csv(path)],
        inventory_rows=[r for path in a.inventory for r in read_csv(path)],
        new_site_paths=set(mapping.NewSite.load(a.new_site).paths) if a.new_site else set(),
        taxonomy=rewrite.load_taxonomy(a.taxonomy),
        extra_routes=routes,
        base_url=base,
    )
    result = cleanup.cleanup(coverage, ctx, previous=read_csv(a.previous) if a.previous else None)
    summary = cleanup.write(a.out, result, ctx, counts)
    print(cleanup.markdown(summary))
    if a.expect_published is not None and len(ctx.plan) != a.expect_published:
        print(f"Expected {a.expect_published} published articles, found {len(ctx.plan)}.",
              file=sys.stderr)  # fmt: skip
        return 1
    return 1 if summary["errors"] or (a.gate and not summary["ready_for_staging"]) else 0


def cmd_verify_status(a) -> int:
    from . import status_check

    rows = [r for path in a.urls for r in read_csv(path)]
    summary = status_check.run(
        rows,
        a.base,
        a.out,
        expect=a.expect,
        timeout=a.timeout,
        delay=a.delay,
        max_seconds=a.max_seconds,
        limit=a.limit,
        progress_every=a.progress_every,
        recheck_failed=a.recheck_failed,
        site_hosts=a.site_host,
    )
    print(json.dumps(summary, indent=2))
    return 1 if summary["fail"] or summary["error"] else 0


def cmd_validate_rewrite(a) -> int:
    problems = rewrite.validate_plan(read_csv(a.worklist))
    for p in problems:
        print(f"{p['severity']:7} {p['code']:28} {p['legacy_id']}  {p['message']}")
    errors = sum(1 for p in problems if p["severity"] == "error")
    print(f"{errors} error(s), {len(problems) - errors} warning(s)")
    return 1 if errors else 0


def cmd_validate(a) -> int:
    rows = read_csv(a.mapping)
    site = mapping.NewSite.load(a.new_site) if a.new_site else None
    problems = mapping.validate(rows, site)
    for p in problems:
        print(f"{p['severity']:7} {p['code']:26} {p['legacy_path']}  {p['message']}")
    errors = sum(1 for p in problems if p["severity"] == "error")
    print(f"{len(rows)} rows, {errors} error(s), {len(problems) - errors} warning(s)")
    return 1 if errors else 0


def cmd_gone_conf(a) -> int:
    rows = read_csv(a.mapping)
    errors = [p for p in mapping.validate(rows) if p["severity"] == "error"]
    if errors:
        print(f"Refusing: the mapping has {len(errors)} error(s); run validate.", file=sys.stderr)
        return 1
    text = mapping.nginx_gone_rules(rows)
    Path(a.out).write_text(text, encoding="utf-8")
    print(f"Wrote {text.count('return 410') // 2} retired path(s) to {a.out}")
    return 0


def cmd_compare(a) -> int:
    rows = read_csv(a.mapping)
    fetcher = Fetcher(_hosts(a.new_base, a.host), delay=a.delay, timeout=a.timeout)
    results = verify.compare(
        rows,
        a.new_base,
        fetcher,
        canonical_base=a.canonical_base,
        strict_unresolved=not a.allow_unresolved,
    )
    verify.write_compare(a.out, results)
    counts = {
        k: sum(1 for r in results if r["result"] == k)
        for k in ("pass", "warn", "fail", "unresolved")
    }
    print(json.dumps(counts))
    return 1 if counts["fail"] else 0


def cmd_sitemap_check(a) -> int:
    rows = read_csv(a.mapping) if a.mapping else []
    fetch_base = a.fetch_base or ""
    hosts = _hosts(a.sitemap_url, a.host) + ([urlsplit(fetch_base).netloc] if fetch_base else [])
    fetcher = Fetcher(hosts, delay=a.delay, timeout=a.timeout)
    results = verify.sitemap_check(
        a.sitemap_url,
        rows,
        fetcher,
        fetch_base=fetch_base,
        canonical_base=a.canonical_base,
        check_pages=not a.no_fetch,
    )
    verify.write_sitemap(a.out, results)
    counts = {k: sum(1 for r in results if r["result"] == k) for k in ("pass", "warn", "fail")}
    print(json.dumps(counts))
    return 1 if counts["fail"] else 0


def cmd_report(a) -> int:
    rows = read_csv(a.mapping)
    rep = report.build(
        rows,
        inventory=read_csv(a.inventory) if a.inventory else None,
        worklist=read_csv(a.worklist) if a.worklist else None,
        problems=mapping.validate([dict(r) for r in rows]),
        compare=read_csv(a.compare) if a.compare else None,
        sitemap=read_csv(a.sitemap) if a.sitemap else None,
    )
    text = report.markdown(rep)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        Path(a.out).with_suffix(".json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(text)
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m legacy_migration", description=__doc__)
    sub = p.add_subparsers(dest="step", required=True)

    def net(sp):
        sp.add_argument("--host", action="append", default=[], help="extra allowed host (www)")
        sp.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
        sp.add_argument("--timeout", type=float, default=20.0)

    s = sub.add_parser("inventory", help="crawl the legacy site (GET only)")
    s.add_argument("--base-url", required=True)
    s.add_argument("--start", action="append", default=[], help="archive/category/landing page")
    s.add_argument("--sitemap", action="append", default=[], help="extra sitemap URL")
    s.add_argument("--seeds", action="append", default=[], help="URL list or Search Console CSV")
    s.add_argument("--articles-csv", action="append", default=[], help="legacy DB article export")
    s.add_argument("--articles-api", action="append", default=[], help="JSON article list URL")
    s.add_argument("--max-pages", type=int, default=5000)
    s.add_argument("--no-follow", action="store_true", help="don't follow internal links")
    s.add_argument("--ignore-robots", action="store_true")
    s.add_argument("--skip-media", action="store_true", help="don't request images/files")
    s.add_argument("--out", required=True, help="output directory (one per run)")
    net(s)
    s.set_defaults(func=cmd_inventory)

    s = sub.add_parser("rewrite-plan", help="published-only rewrite worklist from the CMS export")
    s.add_argument("--export", action="append", required=True, help="legacy CMS export CSV")
    s.add_argument("--inventory", help="inventory.csv (URL and canonical evidence)")
    s.add_argument("--taxonomy", help="approved editorial taxonomy decisions (CSV)")
    s.add_argument("--previous", help="earlier rewrite-worklist.csv (editor fields are kept)")
    s.add_argument(
        "--base-url", default="", help="legacy origin, e.g. https://thinkpositivealways.com"
    )
    s.add_argument("--expect-published", type=int, help="fail unless this many published")
    s.add_argument("--expect-draft", type=int, help="fail unless this many drafts")
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_rewrite_plan)

    s = sub.add_parser(
        "reconcile", help="CMS export + inventory + Search Console -> decisions and readiness"
    )
    s.add_argument("--export", action="append", required=True, help="legacy CMS export CSV")
    s.add_argument("--inventory", action="append", default=[], help="inventory.csv, latest first")
    s.add_argument("--gsc", action="append", default=[], help="Search Console CSV/zip/folder")
    s.add_argument(
        "--gsc-index", nargs=2, action="append", default=[], metavar=("ISSUE", "FILE"),
        help='Pages report drill-down, e.g. "Crawled - currently not indexed" file.csv',
    )  # fmt: skip
    s.add_argument("--taxonomy", help="approved taxonomy decisions (CSV)")
    s.add_argument("--previous-master", help="edited master-url-inventory.csv (decisions kept)")
    s.add_argument("--previous-register", help="edited rewrite-register.csv (decisions kept)")
    s.add_argument("--new-site", help="CSV from `flask legacy export-cms`")
    s.add_argument("--base-url", default="https://thinkpositivealways.com")
    s.add_argument("--expect-published", type=int)
    s.add_argument("--gate", action="store_true", help="exit 1 unless production-ready")
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_reconcile)

    s = sub.add_parser("cleanup", help="historical Search Console URLs -> cleanup decisions")
    s.add_argument("--coverage", action="append", default=[], help="coverage export (csv/zip/dir)")
    s.add_argument(
        "--coverage-report", nargs=2, action="append", default=[], metavar=("REPORT", "FILE"),
        help="coverage export with its report name, e.g. 'Not found (404)' file.csv",
    )  # fmt: skip
    s.add_argument("--export", action="append", default=[], help="legacy CMS export CSV")
    s.add_argument("--inventory", action="append", default=[], help="inventory.csv, latest first")
    s.add_argument("--new-site", help="CSV from `flask legacy export-cms`")
    s.add_argument("--routes", action="append", default=[], help="extra approved new-site paths")
    s.add_argument("--taxonomy", help="approved taxonomy decisions (CSV)")
    s.add_argument("--previous", help="edited cleanup-decisions.csv (decisions are kept)")
    s.add_argument("--base-url", default="https://thinkpositivealways.com")
    s.add_argument("--expect-urls", type=int, help="fail unless this many distinct URLs")
    s.add_argument("--expect-published", type=int)
    s.add_argument("--gate", action="store_true", help="exit 1 unless ready for staging")
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_cleanup)

    s = sub.add_parser("verify-status", help="read-only, resumable HTTP status checks")
    s.add_argument("urls", nargs="+", help="cleanup-decisions.csv (or any CSV with a url column)")
    s.add_argument(
        "--base", required=True, help="site to request, e.g. https://staging.example.com"
    )
    s.add_argument("--site-host", action="append", default=["thinkpositivealways.com"],
                   help="host(s) of the historical URLs, tested by path on --base")  # fmt: skip
    s.add_argument("--expect", action="store_true", help="check each URL against its decision")
    s.add_argument("--timeout", type=float, default=10.0, help="seconds per request")
    s.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    s.add_argument("--max-seconds", type=float, default=0, help="stop (resumable) after this")
    s.add_argument("--limit", type=int, default=0, help="check at most this many now")
    s.add_argument("--progress-every", type=int, default=25)
    s.add_argument("--recheck-failed", action="store_true")
    s.add_argument("--out", required=True, help="results CSV (appended; resumes)")
    s.set_defaults(func=cmd_verify_status)

    s = sub.add_parser("validate-rewrite", help="check an edited rewrite-worklist.csv")
    s.add_argument("worklist")
    s.set_defaults(func=cmd_validate_rewrite)

    s = sub.add_parser("map", help="propose the legacy-to-new URL mapping")
    s.add_argument(
        "--inventory",
        action="append",
        required=True,
        help="inventory.csv (latest first is fine; repeat for older runs)",
    )
    s.add_argument("--new-site", help="CSV from `flask legacy export-cms`")
    s.add_argument("--articles", action="append", default=[], help="legacy-articles.csv")
    s.add_argument(
        "--overrides", action="append", default=[], help="reviewed mapping (approved rows win)"
    )
    s.add_argument("--aliases", help="CSV legacy_path,target_path of renamed pages")
    s.add_argument("--taxonomy", help="approved editorial taxonomy decisions (CSV)")
    s.add_argument("--retire-min-observations", type=int, default=mapping.RETIRE_MIN_OBSERVATIONS)
    s.add_argument("--retire-min-days", type=int, default=mapping.RETIRE_MIN_DAYS)
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_map)

    s = sub.add_parser("validate", help="check a reviewed url-mapping.csv")
    s.add_argument("mapping")
    s.add_argument("--new-site")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("gone-conf", help="Nginx 410 rules for approved RETIRE_410 rows")
    s.add_argument("mapping")
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_gone_conf)

    s = sub.add_parser("compare", help="prelaunch: legacy URLs on the new site")
    s.add_argument("mapping")
    s.add_argument("--new-base", required=True, help="e.g. https://staging.example.com")
    s.add_argument("--canonical-base", default="", help="production origin used in canonicals")
    s.add_argument("--allow-unresolved", action="store_true")
    s.add_argument("--out", required=True)
    net(s)
    s.set_defaults(func=cmd_compare)

    s = sub.add_parser("sitemap-check", help="new sitemap lists only canonical indexable URLs")
    s.add_argument("sitemap_url")
    s.add_argument("--mapping")
    s.add_argument("--fetch-base", default="", help="request pages here (e.g. staging)")
    s.add_argument("--canonical-base", default="")
    s.add_argument("--no-fetch", action="store_true", help="only check the URL list")
    s.add_argument("--out", required=True)
    net(s)
    s.set_defaults(func=cmd_sitemap_check)

    s = sub.add_parser("report", help="migration totals (markdown + JSON)")
    s.add_argument("mapping")
    s.add_argument("--inventory")
    s.add_argument("--worklist")
    s.add_argument("--compare")
    s.add_argument("--sitemap")
    s.add_argument("--out")
    s.set_defaults(func=cmd_report)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
