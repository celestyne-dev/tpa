"""Read-only HTTP status verification for historical URLs: bounded and resumable.

Every URL is requested once with GET on ``--base`` (the legacy site to record what it does
today, or staging to check the cleanup decisions). Results are appended to the output CSV
row by row, so an interrupted run (time budget, limit, Ctrl-C) resumes where it stopped.
Each request has a timeout, redirects are followed at most 10 hops on the same host, and a
whole run can be capped with ``--max-seconds``.

With ``--expect`` each URL is checked against its decision:
  KEEP_200      200 without redirects, and not the soft-404/app shell answered to unknown URLs
  REDIRECT_301  one 301/308 straight to the approved target, which answers 200
  RETIRE_410    410
  ALLOW_404     a genuine 404 (or 410), never a 200 shell or homepage
"""

from __future__ import annotations

import csv
import secrets
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .core import clean_url, path_key, path_of, same_site
from .fetch import Fetcher, fingerprint

RESULT_FIELDS = (
    "url", "tested_url", "expected", "expected_target", "status", "location", "redirect_hops",
    "final_status", "final_url", "matches_unknown_url_response", "elapsed_ms", "error",
    "result", "problem", "checked_at",
)  # fmt: skip
PERMANENT = (301, 308)


def _done(out: Path, recheck_failed: bool) -> set[str]:
    if not out.exists():
        return set()
    with out.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {
        r["url"]
        for r in rows
        if r.get("url") and not (recheck_failed and r.get("result") in ("fail", "error"))
    }


def _expected(row: dict) -> tuple[str, str]:
    cls = row.get("effective_class") or {"KEEP": "KEEP_200"}.get(
        row.get("action", ""), row.get("action", "")
    )
    target = row.get("effective_target") or row.get("target_path") or ""
    return cls, target


def _judge(cls: str, target: str, res, shell: bool) -> tuple[str, str]:
    first = res.hops[0] if res.hops else None
    if res.error and not res.final_status:
        return "error", res.error
    if cls == "KEEP_200":
        if res.redirect_count:
            return "fail", f"redirects ({res.chain_text()})"
        if res.status != 200:
            return "fail", f"status {res.status}"
        if shell:
            return "fail", "same response as an unknown URL (soft 404 / app shell)"
        return "pass", ""
    if cls == "REDIRECT_301":
        if res.status not in PERMANENT:
            return "fail", f"expected 301, got {res.status}"
        location = clean_url(first.location, res.url) if first and first.location else ""
        if path_key(path_of(location or "")) != path_key(target):
            return "fail", f"redirects to {location or '?'} instead of {target}"
        if res.redirect_count > 1:
            return "fail", f"redirect chain ({res.chain_text()})"
        if res.final_status != 200:
            return "fail", f"target answers {res.final_status}"
        return "pass", ""
    if cls == "RETIRE_410":
        return (
            ("pass", "")
            if res.status == 410 and not res.redirect_count
            else ("fail", f"expected 410, got {res.status}")
        )
    if cls == "ALLOW_404":
        if res.status in (404, 410) and not res.redirect_count:
            return "pass", ""
        if res.status == 200:
            return "fail", "answers 200 (unknown URLs must be a genuine 404)"
        return "fail", f"expected 404, got {res.status}" + (
            f" ({res.chain_text()})" if res.redirect_count else ""
        )
    return "info", ""


def run(
    rows: list[dict],
    base: str,
    out_path: str | Path,
    *,
    expect: bool = False,
    timeout: float = 10.0,
    delay: float = 0.5,
    max_seconds: float = 0,
    limit: int = 0,
    progress_every: int = 25,
    recheck_failed: bool = False,
    site_hosts: list[str] | None = None,
    fetcher: Fetcher | None = None,
    log=sys.stderr,
) -> dict:
    base = base.rstrip("/")
    b = urlsplit(base)
    fetcher = fetcher or Fetcher([b.netloc], delay=delay, timeout=timeout)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = _done(out, recheck_failed)
    todo = []
    seen = set()
    for row in rows:
        url = row.get("url") or row.get("legacy_url") or ""
        if url and url not in done and url not in seen:
            seen.add(url)
            todo.append(row)
    total = len(todo)
    probe = fetcher.get(f"{base}/__tpa-status-probe-{secrets.token_hex(5)}")
    probe_print = fingerprint(probe) if probe.final_status == 200 else ""
    started = time.monotonic()
    counts = {"pass": 0, "fail": 0, "error": 0, "info": 0, "skipped": 0}
    new_file = not out.exists() or out.stat().st_size == 0
    checked = 0
    with out.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_FIELDS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        for row in todo:
            if limit and checked >= limit:
                break
            if max_seconds and time.monotonic() - started > max_seconds:
                break
            url = row.get("url") or row.get("legacy_url")
            parts = urlsplit(url)
            cls, target = _expected(row) if expect else ("", "")
            result = {
                "url": url,
                "expected": cls,
                "expected_target": target,
                "checked_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            if parts.netloc and not same_site(url, [b.netloc, *(site_hosts or [])]):
                result.update(result="skipped", problem="other host")
            else:
                tested = urlunsplit((b.scheme, b.netloc, parts.path or "/", parts.query, ""))
                res = fetcher.get(tested)
                first = res.hops[0] if res.hops else None
                shell = (
                    bool(probe_print)
                    and res.final_status == 200
                    and (fingerprint(res) == probe_print)
                )
                verdict, problem = (
                    _judge(cls, target, res, shell)
                    if expect
                    else (
                        ("error", res.error) if res.error and not res.final_status else ("info", "")
                    )
                )
                result.update(
                    tested_url=tested,
                    status=res.status,
                    location=first.location if first else "",
                    redirect_hops=res.redirect_count,
                    final_status=res.final_status,
                    final_url=res.final_url if res.final_url != tested else "",
                    matches_unknown_url_response="yes" if shell else "",
                    elapsed_ms=res.elapsed_ms,
                    error=res.error,
                    result=verdict,
                    problem=problem,
                )
            writer.writerow(result)
            fh.flush()  # resumable: every finished URL is on disk
            counts[result["result"]] += 1
            checked += 1
            if progress_every and (checked % progress_every == 0 or checked == total):
                print(
                    f"[{checked}/{total}] pass={counts['pass']} fail={counts['fail']} "
                    f"error={counts['error']} info={counts['info']} "
                    f"({time.monotonic() - started:.0f}s) {url}",
                    file=log,
                    flush=True,
                )
    remaining = total - checked
    summary = {
        "already_done": len(done),
        "checked": checked,
        "remaining": remaining,
        "complete": remaining == 0,
        "probe_status": probe.final_status,
        "unknown_urls_answer_200": probe.final_status == 200,
        **counts,
    }
    if remaining:
        print(f"Stopped with {remaining} URL(s) left: run again to resume.", file=log, flush=True)
    return summary
