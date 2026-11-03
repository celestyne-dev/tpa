"""Google Search Console exports as evidence (never as migration instructions).

Accepted inputs, each a ``.csv``, a downloaded ``.zip`` or an unzipped folder (the
``Table.csv`` inside is read, and ``Metadata.csv`` for the report's issue name):
- Performance -> Pages (``Top pages``, ``Clicks``, ``Impressions``, ``CTR``, ``Position``)
- Links -> Top linked pages (``Target page`` / ``Top linked pages``, ``Incoming links``)
- Pages (indexing) drill-downs (``URL``, ``Last crawled``), one export per issue. Give the
  issue with ``--gsc-index "<issue as shown>" FILE`` when the file doesn't name it.
- URL Inspection results with ``Google-selected canonical`` / ``User-declared canonical``.

Index statuses are normalised. Only ``INDEXED`` means indexed: "Crawled - currently not
indexed" and "Discovered - currently not indexed" are **not** indexed, and nothing here
retires or keeps a URL by itself.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime
from pathlib import Path

from .core import as_int, clean_url

INDEX_STATUSES = (
    "INDEXED", "CRAWLED_NOT_INDEXED", "DISCOVERED_NOT_INDEXED", "NOT_FOUND_404", "SOFT_404",
    "PAGE_WITH_REDIRECT", "REDIRECT_ERROR", "ALTERNATE_CANONICAL",
    "GOOGLE_CHOSE_DIFFERENT_CANONICAL", "DUPLICATE_NO_CANONICAL", "NOINDEX",
    "BLOCKED_ROBOTS", "BLOCKED_ACCESS", "SERVER_ERROR", "OTHER",
)  # fmt: skip
# Most specific first: "not indexed" phrases must win over the plain word "indexed".
_PATTERNS = (
    ("crawled currently not indexed", "CRAWLED_NOT_INDEXED"),
    ("discovered currently not indexed", "DISCOVERED_NOT_INDEXED"),
    ("google chose different canonical", "GOOGLE_CHOSE_DIFFERENT_CANONICAL"),
    ("duplicate without user selected canonical", "DUPLICATE_NO_CANONICAL"),
    ("alternate page with proper canonical", "ALTERNATE_CANONICAL"),
    ("indexed though blocked by robots", "INDEXED"),
    ("blocked by robots", "BLOCKED_ROBOTS"),
    ("soft 404", "SOFT_404"),
    ("not found 404", "NOT_FOUND_404"),
    ("not found", "NOT_FOUND_404"),
    ("page with redirect", "PAGE_WITH_REDIRECT"),
    ("redirect error", "REDIRECT_ERROR"),
    ("noindex", "NOINDEX"),
    ("server error", "SERVER_ERROR"),
    ("5xx", "SERVER_ERROR"),
    ("unauthorized", "BLOCKED_ACCESS"),
    ("forbidden", "BLOCKED_ACCESS"),
    ("4xx", "BLOCKED_ACCESS"),
)
URL_HEADERS = (
    "top pages", "page", "pages", "url", "address", "landing page", "target page",
    "top linked pages", "inspected url",
)  # fmt: skip
STATUS_HEADERS = ("status", "coverage", "reason", "issue", "indexing state", "page indexing")
EVIDENCE_FIELDS = (
    "gsc_index_status", "gsc_index_reason", "gsc_last_crawled", "gsc_clicks",
    "gsc_impressions", "gsc_ctr", "gsc_position", "gsc_backlinks", "gsc_google_canonical",
    "gsc_user_canonical", "gsc_sources",
)  # fmt: skip


def normalise_index_status(text: str) -> str:
    raw = (text or "").lower()
    t = re.sub(r"[‐-―\-–—_:(),']+", " ", raw)
    t = " ".join(t.split())
    if not t:
        return ""
    for needle, status in _PATTERNS:
        if needle in t:
            return status
    if "not indexed" in t or "unindexed" in t or "not on google" in t:
        return "OTHER"  # an unrecognised "not indexed" reason is still not indexed
    if "indexed" in t.split() or "url is on google" in t:
        return "INDEXED"  # "Indexed", "Submitted and indexed", "Indexed, not submitted..."
    return "OTHER"


def _date(value: str) -> str:
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%d %b %Y", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).date().isoformat()
        except ValueError:
            continue
    return value


def _tables(path: str | Path) -> list[tuple[str, list[dict], dict]]:
    """[(name, rows, metadata)] from a CSV file, a zip export or a folder."""
    path = Path(path)
    texts: dict[str, str] = {}
    if path.is_dir():
        texts = {p.name: p.read_text(encoding="utf-8-sig") for p in path.glob("*.csv")}
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.lower().endswith(".csv") and "/" not in name.strip("/"):
                    texts[name] = z.read(name).decode("utf-8-sig", errors="replace")
    else:
        texts = {path.name: path.read_text(encoding="utf-8-sig")}
    metadata = {}
    for name, text in texts.items():
        if name.lower().startswith("metadata"):
            for row in csv.reader(io.StringIO(text)):
                if len(row) >= 2:
                    metadata[row[0].strip().lower()] = row[1].strip()
    out = []
    for name, text in texts.items():
        low = name.lower()
        if low.startswith(("metadata", "chart")):
            continue
        reader = csv.DictReader(io.StringIO(text))
        rows = [  # extra unnamed cells (a stray comma) are ignored, not fatal
            {k.strip().lower(): (v or "").strip() for k, v in r.items() if isinstance(k, str)}
            for r in reader
        ]
        out.append((name, rows, metadata))
    return out


def load(
    files: list[str] | None = None,
    index_reports: list[tuple[str, str]] | None = None,
    base_url: str = "",
) -> dict[str, dict]:
    """URL -> evidence. ``index_reports`` pairs (issue label, file) for drill-down exports."""
    evidence: dict[str, dict] = {}
    jobs = [("", f) for f in files or []] + [(label, f) for label, f in index_reports or []]
    for label, file in jobs:
        for _name, rows, metadata in _tables(file):
            report_issue = label or next(
                (
                    metadata[k]
                    for k in ("issue", "reason", "status", "page indexing")
                    if metadata.get(k)
                ),
                "",
            )
            if not rows:
                continue
            headers = set(rows[0])
            url_col = next((h for h in URL_HEADERS if h in headers), None)
            if url_col is None:
                continue
            status_col = next((h for h in STATUS_HEADERS if h in headers), None)
            is_perf = bool({"clicks", "impressions"} & headers)
            is_links = bool({"incoming links", "linking sites", "links"} & headers)
            is_index = bool(report_issue or status_col or "last crawled" in headers)
            for row in rows:
                url = clean_url(row.get(url_col, ""), base_url or None)
                if not url:
                    continue
                e = evidence.setdefault(url, {k: "" for k in EVIDENCE_FIELDS})
                sources = set(filter(None, e["gsc_sources"].split(";")))
                if is_perf:
                    e["gsc_clicks"] = str(as_int(e["gsc_clicks"]) + as_int(row.get("clicks")))
                    e["gsc_impressions"] = str(
                        as_int(e["gsc_impressions"]) + as_int(row.get("impressions"))
                    )
                    e["gsc_ctr"] = row.get("ctr", e["gsc_ctr"])
                    e["gsc_position"] = row.get("position", e["gsc_position"])
                    sources.add("gsc_performance")
                if is_links:
                    links = (
                        row.get("incoming links") or row.get("links") or row.get("linking sites")
                    )
                    e["gsc_backlinks"] = str(as_int(e["gsc_backlinks"]) + as_int(links))
                    sources.add("gsc_links")
                if is_index:
                    reason = (row.get(status_col) if status_col else "") or report_issue
                    crawled = _date(row.get("last crawled", ""))
                    status = normalise_index_status(reason)
                    # Several reports may list one URL: the most recent crawl wins.
                    if status and (not e["gsc_index_status"] or crawled >= e["gsc_last_crawled"]):
                        e["gsc_index_status"], e["gsc_index_reason"] = status, reason
                    if crawled > e["gsc_last_crawled"]:
                        e["gsc_last_crawled"] = crawled
                    sources.add("gsc_index")
                for key, col in (
                    ("gsc_google_canonical", "google-selected canonical"),
                    ("gsc_user_canonical", "user-declared canonical"),
                ):
                    if row.get(col):
                        e[key] = clean_url(row[col], base_url or None) or row[col]
                e["gsc_sources"] = ";".join(sorted(sources))
    return evidence
