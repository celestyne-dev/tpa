"""Prelaunch checks against the new site (staging before DNS changes, production after).

``compare``: every mapped legacy URL, requested on the new site exactly as backlinks use
it, must give its decided result:
  KEEP          200, no redirect, indexable, canonical to itself
  REDIRECT_301  one permanent redirect (301/308) straight to the approved target,
                which answers 200, is indexable and canonical to itself
  RETIRE_410    410 (404 is reported as a warning)
  REVIEW        unresolved: blocks launch when the URL is high priority

``sitemap_check``: the new sitemap must list only canonical, indexable URLs that answer
200 without redirects, never a legacy redirect source or a retired path.
"""

from __future__ import annotations

from collections import deque
from urllib.parse import urlsplit, urlunsplit

from .core import clean_url, path_key, path_of, truthy, write_csv
from .fetch import Fetcher, Response, is_noindex, parse_page, parse_sitemap

COMPARE_FIELDS = (
    "legacy_path", "priority", "action", "target_path", "approved", "tested_url", "status",
    "location", "final_url", "final_status", "redirect_hops", "canonical", "noindex",
    "result", "problems",
)  # fmt: skip
SITEMAP_FIELDS = (
    "loc", "path", "final_status", "redirect_hops", "noindex", "canonical", "result", "problems",
)  # fmt: skip
PERMANENT = (301, 308)


def _on(base: str, path: str) -> str:
    b = urlsplit(base)
    p = urlsplit(path if path.startswith("/") else "/" + path)
    return urlunsplit((b.scheme, b.netloc, p.path, p.query, ""))


def _page_facts(res: Response, canonical_host: str, expected_key: str) -> tuple[str, bool, list]:
    problems = []
    page = parse_page(res.text(), res.final_url) if res.final_status == 200 else {}
    noindex = is_noindex(page.get("robots_meta", ""), res.headers.get("x-robots-tag", ""))
    canonical = page.get("canonical", "")
    if res.final_status == 200:
        title = page.get("title", "").lower()
        if "page not found" in title or title.startswith("404"):
            problems.append("soft_404")
        if noindex:
            problems.append("noindex")
        if not canonical:
            problems.append("missing_canonical")
        else:
            c = urlsplit(canonical)
            if canonical_host and (c.hostname or "").lower() != canonical_host:
                problems.append(f"canonical_host:{c.hostname}")
            if path_key(c.path or "/") != expected_key:
                problems.append(f"canonical_elsewhere:{path_key(c.path or '/')}")
    return canonical, noindex, problems


def compare(
    rows: list[dict],
    new_base: str,
    fetcher: Fetcher,
    *,
    canonical_base: str = "",
    strict_unresolved: bool = True,
) -> list[dict]:
    canonical_host = (urlsplit(canonical_base or new_base).hostname or "").lower()
    results = []
    for row in rows:
        action = (row.get("action") or "").upper()
        key = path_key(row.get("legacy_path") or path_of(row.get("legacy_url", "")))
        legacy_path = path_of(row["legacy_url"]) if row.get("legacy_url") else key
        out = {
            "legacy_path": key,
            "priority": row.get("priority", ""),
            "action": action,
            "target_path": row.get("target_path", ""),
            "approved": row.get("approved", ""),
            "tested_url": _on(new_base, legacy_path),
        }
        problems: list[str] = []
        if action == "REVIEW" or action not in ("KEEP", "REDIRECT_301", "RETIRE_410", "ALLOW_404"):
            high = row.get("priority") == "high"
            out["result"] = "fail" if (high and strict_unresolved) else "unresolved"
            out["problems"] = "unresolved" + (":high_priority" if high else "")
            results.append(out)
            continue
        res = fetcher.get(out["tested_url"])
        first = res.hops[0] if res.hops else None
        out.update(
            status=res.status,
            location=first.location if first else "",
            final_url=res.final_url,
            final_status=res.final_status,
            redirect_hops=res.redirect_count,
        )
        if res.error and not res.final_status:
            problems.append(f"error:{res.error}")
        elif action == "KEEP":
            if res.redirect_count:
                problems.append(f"redirects:{res.chain_text()}")
            if res.final_status != 200:
                problems.append(f"status:{res.final_status}")
            canonical, noindex, page_problems = _page_facts(res, canonical_host, key)
            out.update(canonical=canonical, noindex=noindex)
            problems += page_problems
        elif action == "REDIRECT_301":
            target = path_key(row.get("target_path", ""))
            if not truthy(row.get("approved")):
                problems.append("not_approved")
            if res.status not in PERMANENT:
                problems.append(f"expected_301_got:{res.status}")
            else:
                loc = clean_url(out["location"], out["tested_url"]) or ""
                if path_key(path_of(loc)) != target:
                    problems.append(f"wrong_target:{path_key(path_of(loc))}")
                if res.redirect_count > 1:
                    problems.append(f"redirect_chain:{res.chain_text()}")
                if res.final_status != 200:
                    problems.append(f"target_status:{res.final_status}")
                canonical, noindex, page_problems = _page_facts(res, canonical_host, target)
                out.update(canonical=canonical, noindex=noindex)
                problems += [f"target_{p}" for p in page_problems]
        elif action == "RETIRE_410":
            if not truthy(row.get("approved")):
                problems.append("not_approved")
            if res.status == 404 and not res.redirect_count:
                out["result"] = "warn"
                problems.append("404_not_410")
            elif res.status != 410:
                problems.append(f"expected_410_got:{res.status}")
        elif action == "ALLOW_404" and (res.redirect_count or res.status not in (404, 410)):
            # A genuine 404: never a 200 page, app shell or redirect to the homepage.
            problems.append(f"expected_404_got:{res.status}")
        out["problems"] = ";".join(problems)
        if "result" not in out:
            soft = problems == ["not_approved"]
            out["result"] = "pass" if not problems else ("warn" if soft else "fail")
        results.append(out)
    return results


def sitemap_check(
    sitemap_url: str,
    rows: list[dict],
    fetcher: Fetcher,
    *,
    fetch_base: str = "",
    canonical_base: str = "",
    check_pages: bool = True,
) -> list[dict]:
    """Every sitemap URL must be canonical and indexable; report mapped targets missing."""
    canonical_host = (urlsplit(canonical_base or sitemap_url).hostname or "").lower()
    locs: list[str] = []
    pending, seen = deque([sitemap_url]), set()
    while pending and len(seen) < 100:
        sm = pending.popleft()
        if sm in seen:
            continue
        seen.add(sm)
        res = fetcher.get(_on(fetch_base, path_of(sm)) if fetch_base else sm)
        if res.final_status != 200:
            locs.append(f"!sitemap:{sm}:{res.final_status or res.error}")
            continue
        urls, nested = parse_sitemap(res.body)
        locs += [u for u, _ in urls]
        pending.extend(nested)
    actions = {
        path_key(r.get("legacy_path") or path_of(r.get("legacy_url", ""))): (
            r.get("action") or ""
        ).upper()
        for r in rows
    }
    results, listed = [], set()
    for loc in locs:
        if loc.startswith("!sitemap:"):
            results.append({"loc": loc[9:], "result": "fail", "problems": "sitemap_unreachable"})
            continue
        key = path_key(urlsplit(loc).path or "/")
        problems = []
        if key in listed:
            problems.append("duplicate")
        listed.add(key)
        if (urlsplit(loc).hostname or "").lower() != canonical_host:
            problems.append(f"host:{urlsplit(loc).hostname}")
        if urlsplit(loc).query:
            problems.append("query_string")
        if actions.get(key) == "REDIRECT_301":
            problems.append("legacy_redirect_source")
        if actions.get(key) == "RETIRE_410":
            problems.append("retired_path")
        if actions.get(key) == "ALLOW_404":
            problems.append("allowed_404_path")
        out = {"loc": loc, "path": key}
        if check_pages:
            res = fetcher.get(_on(fetch_base, path_of(loc)) if fetch_base else loc)
            out.update(final_status=res.final_status, redirect_hops=res.redirect_count)
            if res.redirect_count:
                problems.append("redirects")
            if res.final_status != 200:
                problems.append(f"status:{res.final_status or res.error}")
            canonical, noindex, page_problems = _page_facts(res, canonical_host, key)
            out.update(canonical=canonical, noindex=noindex)
            problems += page_problems
        out["problems"] = ";".join(problems)
        out["result"] = "fail" if problems else "pass"
        results.append(out)
    expected = set()
    for r in rows:
        action = (r.get("action") or "").upper()
        if r.get("kind") not in ("article", "page", "category", "home"):
            continue
        if action == "KEEP":
            expected.add(path_key(r.get("legacy_path", "")))
        elif action == "REDIRECT_301" and r.get("target_path"):
            expected.add(path_key(r["target_path"]))
    for key in sorted(expected - listed):
        results.append(
            {"loc": "", "path": key, "result": "warn", "problems": "mapped_target_not_in_sitemap"}
        )
    return results


def write_compare(path, rows):
    return write_csv(path, COMPARE_FIELDS, rows)


def write_sitemap(path, rows):
    return write_csv(path, SITEMAP_FIELDS, rows)
