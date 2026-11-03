"""Read-only inventory of the legacy website.

Sources (each URL records every source that found it):
- ``sitemap``: robots.txt Sitemap lines, /sitemap.xml, /sitemap_index.xml (nested, gzip)
- ``start``: the article archive, category and landing pages given with --start
- ``link``: internal links found on crawled pages (and canonical targets)
- ``seed:<name>``: URL lists from Search Console exports, backups, old sitemaps, logs
- ``articles:<name>``: article records from a database export or a JSON API (their URL
  is used only when the record itself contains one; nothing is guessed)

A random probe path is requested first. If the server answers it with 200 (a JavaScript
single-page app does), any page with the same HTML is marked ``shell_only``: its status
proves nothing and the content must be confirmed from the API, the database export or
Search Console instead.
"""

from __future__ import annotations

import json
import secrets
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from .core import (
    GONE_STATUSES,
    as_int,
    classify_path,
    clean_url,
    last_segment,
    path_key,
    path_of,
    read_csv,
    same_site,
    write_csv,
)
from .fetch import (
    REDIRECT_CODES,
    Fetcher,
    fingerprint,
    is_noindex,
    parse_page,
    parse_robots,
    parse_sitemap,
)

INVENTORY_FIELDS = (
    "url", "path", "kind", "discovered_via", "referrer", "in_sitemap", "sitemap_lastmod",
    "in_archive", "inlinks", "checked_at", "status", "final_status", "final_url",
    "redirect_hops", "redirect_chain", "page_class", "content_type", "title",
    "meta_description", "h1", "canonical", "canonical_status", "robots_meta", "x_robots_tag",
    "noindex", "og_type", "schema_type", "published_time", "modified_time", "author",
    "section", "word_count", "og_image", "seed_clicks", "seed_impressions", "seed_backlinks",
    "issues", "error",
)  # fmt: skip
LINK_FIELDS = ("source_url", "target_url", "anchor", "target_final_status", "broken")
ARTICLE_FIELDS = (
    "source", "id", "slug", "title", "author", "published_at", "modified_at", "status",
    "category", "section", "url", "matched_url", "match", "in_sitemap", "in_archive",
    "missing_from_archive", "no_public_url",
)  # fmt: skip

URL_COLUMNS = (
    "url", "page", "pages", "top pages", "address", "landing page", "target page", "loc",
    "legacy_url", "source_url",
)  # fmt: skip
PAGINATION_PARAMS = {"page", "p", "paged", "pg"}


@dataclass
class Item:
    url: str
    sources: set[str] = field(default_factory=set)
    referrer: str = ""
    in_sitemap: bool = False
    sitemap_lastmod: str = ""
    in_archive: bool = False
    inlinks: int = 0
    clicks: int = 0
    impressions: int = 0
    backlinks: int = 0
    row: dict = field(default_factory=dict)


@dataclass
class Settings:
    base_url: str
    hosts: list[str]
    starts: list[str] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    seed_files: list[str] = field(default_factory=list)
    article_csvs: list[str] = field(default_factory=list)
    article_apis: list[str] = field(default_factory=list)
    max_pages: int = 5000
    follow_links: bool = True
    respect_robots: bool = True
    check_media: bool = True


class Inventory:
    def __init__(self, settings: Settings, fetcher: Fetcher):
        self.s = settings
        self.fetch = fetcher
        self.items: dict[str, Item] = {}
        self.links: list[dict] = []
        self.articles: list[dict] = []
        self.queue: deque[str] = deque()
        self.robots = None
        self.probe: dict = {}
        self.notes: list[str] = []
        self.fetched = 0

    # ---- discovery -----------------------------------------------------------------

    def add(self, url: str | None, source: str, referrer: str = "") -> Item | None:
        url = clean_url(url or "", self.s.base_url)
        if not url or not same_site(url, self.s.hosts):
            return None
        query = dict(parse_qsl(urlsplit(url).query))
        if query and not set(query) <= PAGINATION_PARAMS:
            return None  # tracking/search parameters: one URL per page is enough
        item = self.items.get(url)
        if item is None:
            item = self.items[url] = Item(url=url, referrer=referrer)
            self.queue.append(url)
        item.sources.add(source)
        return item

    def run_probe(self) -> None:
        probe_url = f"{self.s.base_url.rstrip('/')}/__tpa-inventory-probe-{secrets.token_hex(6)}"
        res = self.fetch.get(probe_url)
        page = parse_page(res.text(), probe_url) if res.final_status == 200 else {}
        self.probe = {
            "url": probe_url,
            "status": res.final_status,
            "fingerprint": fingerprint(res) if res.final_status == 200 else "",
            "title": page.get("title", ""),
        }
        if res.final_status == 200:
            self.notes.append(
                "The site answers unknown URLs with 200 (single-page app or soft 404s): "
                "pages identical to the probe are marked shell_only."
            )

    def discover_sitemaps(self) -> None:
        base = self.s.base_url.rstrip("/")
        candidates = list(self.s.sitemaps)
        res = self.fetch.get(f"{base}/robots.txt")
        if res.final_status == 200:
            self.robots, listed = parse_robots(res.text(), f"{base}/robots.txt")
            candidates += listed
        candidates += [f"{base}/sitemap.xml", f"{base}/sitemap_index.xml"]
        seen: set[str] = set()
        pending = deque(dict.fromkeys(candidates))
        while pending and len(seen) < 100:
            sm = clean_url(pending.popleft())
            if not sm or sm in seen or not same_site(sm, self.s.hosts):
                continue
            seen.add(sm)
            res = self.fetch.get(sm)
            if res.final_status != 200:
                self.notes.append(f"Sitemap {sm}: HTTP {res.final_status or res.error}")
                continue
            urls, nested = parse_sitemap(res.body)
            pending.extend(nested)
            for loc, lastmod in urls:
                item = self.add(loc, "sitemap")
                if item:
                    item.in_sitemap, item.sitemap_lastmod = True, lastmod
            self.notes.append(f"Sitemap {sm}: {len(urls)} URLs, {len(nested)} nested sitemaps")

    def load_seeds(self) -> None:
        for path in self.s.seed_files:
            name = Path(path).stem
            rows = _seed_rows(path)
            for row in rows:
                url = next((row[c] for c in URL_COLUMNS if row.get(c)), "")
                item = self.add(url, f"seed:{row.get('source') or name}")
                if item:
                    item.clicks += as_int(row.get("clicks"))
                    item.impressions += as_int(row.get("impressions"))
                    item.backlinks += as_int(
                        row.get("backlinks") or row.get("links") or row.get("incoming links")
                    )
            self.notes.append(f"Seed {path}: {len(rows)} rows")
        for start in self.s.starts:
            self.add(start, "start")

    def load_articles(self) -> None:
        for path in self.s.article_csvs:
            for row in read_csv(path):
                self.articles.append(_article(row, f"db:{Path(path).stem}"))
        for api in self.s.article_apis:
            res = self.fetch.get(api)
            if res.final_status != 200:
                self.notes.append(f"Article API {api}: HTTP {res.final_status or res.error}")
                continue
            try:
                records = _records(json.loads(res.text()))
            except ValueError:
                self.notes.append(f"Article API {api}: not JSON")
                continue
            for row in records:
                self.articles.append(_article(row, f"api:{urlsplit(api).path}"))
            self.notes.append(f"Article API {api}: {len(records)} records")
        for record in self.articles:
            if record["url"]:  # only a URL the record itself states
                self.add(record["url"], f"articles:{record['source']}")

    # ---- crawling ------------------------------------------------------------------

    def crawl(self) -> None:
        start_keys = {path_key(path_of(clean_url(s, self.s.base_url) or "")) for s in self.s.starts}
        while self.queue and self.fetched < self.s.max_pages:
            url = self.queue.popleft()
            item = self.items[url]
            kind = classify_path(path_of(url))
            if kind in ("system", "asset", "sitemap"):
                item.row = {"page_class": "not_checked", "error": f"{kind} URL (not crawled)"}
                continue
            if (
                self.s.respect_robots
                and self.robots
                and not self.robots.can_fetch(self.fetch.user_agent, url)
            ):
                item.row = {"page_class": "not_checked", "error": "disallowed by robots.txt"}
                continue
            if kind == "media" and not self.s.check_media:
                item.row = {"page_class": "not_checked", "error": "media not checked"}
                continue
            self.fetched += 1
            res = self.fetch.get(url, read_body=kind != "media")
            item.row = self._describe(item, res)
            if (
                res.final_status == 200
                and res.content_type in ("text/html", "application/xhtml+xml", "")
                and same_site(res.final_url, self.s.hosts)
            ):
                page = item.row.pop("_page")
                # Archive and category pages, including their ?page=N pagination.
                from_archive = path_key(path_of(url)) in start_keys
                for target, anchor in page["links"]:
                    if not target:
                        continue
                    linked = (
                        self.add(target, "link", referrer=url)
                        if self.s.follow_links
                        else (self.items.get(target))
                    )
                    if linked is None:
                        continue
                    linked.inlinks += 1
                    linked.in_archive |= bool(from_archive)
                    self.links.append(
                        {"source_url": url, "target_url": linked.url, "anchor": anchor}
                    )
                for image in page["images"][:50]:
                    self.add(image, "image", referrer=url)
                if page["og_image"]:
                    self.add(page["og_image"], "image", referrer=url)
                if page["canonical"]:
                    self.add(page["canonical"], "canonical", referrer=url)
            else:
                item.row.pop("_page", None)
        if self.queue:
            self.notes.append(
                f"Stopped at --max-pages {self.s.max_pages}: {len(self.queue)} URLs not checked."
            )
            for url in self.queue:
                self.items[url].row = {"page_class": "not_checked", "error": "max pages reached"}

    def _describe(self, item: Item, res) -> dict:
        row = {
            "checked_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": res.status,
            "final_status": res.final_status,
            "final_url": res.final_url if res.final_url != item.url else "",
            "redirect_hops": res.redirect_count,
            "redirect_chain": res.chain_text() if res.redirect_count else "",
            "content_type": res.content_type,
            "x_robots_tag": res.headers.get("x-robots-tag", ""),
            "error": res.error,
            "_page": None,
        }
        is_html = res.content_type in ("text/html", "application/xhtml+xml") or (
            not res.content_type and res.body.lstrip()[:1] == b"<"
        )
        if res.final_status == 200 and is_html:
            page = parse_page(res.text(), res.final_url or item.url)
            row["_page"] = page
            row.update({k: page[k] for k in (
                "title", "meta_description", "h1", "canonical", "robots_meta", "og_type",
                "schema_type", "published_time", "modified_time", "author", "section",
                "word_count", "og_image",
            )})  # fmt: skip
            row["_canonical_count"] = page["canonical_count"]
            row["_fingerprint"] = fingerprint(res)
        return row

    # ---- results -------------------------------------------------------------------

    def finish(self) -> tuple[list[dict], list[dict], list[dict]]:
        rows = {}
        for url, item in self.items.items():
            rows[url] = self._row(item)
        broken_sources: dict[str, int] = defaultdict(int)
        for link in self.links:
            target = rows.get(link["target_url"], {})
            status = target.get("final_status", "")
            link["target_final_status"] = status
            link["broken"] = _broken(target)
            if link["broken"]:
                broken_sources[link["source_url"]] += 1
        self._match_articles(rows)
        for url, row in rows.items():
            issues = row["_issues"]
            if broken_sources.get(url):
                issues.append(f"broken_links:{broken_sources[url]}")
            if row["inlinks"] and _broken(row):
                issues.append("linked_but_broken")
            canonical = row.get("canonical")
            if canonical and canonical in rows and canonical != url:
                target = rows[canonical]
                if target.get("final_status") not in (200, "") or target.get("redirect_hops"):
                    issues.append("canonical_not_ok")
            row["issues"] = ";".join(dict.fromkeys(issues))
        return list(rows.values()), self.links, self.articles

    def _row(self, item: Item) -> dict:
        row = {k: "" for k in INVENTORY_FIELDS}
        row.update({k: v for k, v in item.row.items()})
        path = path_of(item.url)
        page_class = row.get("page_class") or _page_class(row, self.probe)
        kind = _kind(path, row)
        noindex = is_noindex(row.get("robots_meta", ""), row.get("x_robots_tag", ""))
        row.update(
            url=item.url,
            path=path,
            kind=kind,
            discovered_via=";".join(sorted(item.sources)),
            referrer=item.referrer,
            in_sitemap=item.in_sitemap,
            sitemap_lastmod=item.sitemap_lastmod,
            in_archive=item.in_archive,
            inlinks=item.inlinks,
            page_class=page_class,
            noindex=noindex,
            seed_clicks=item.clicks or "",
            seed_impressions=item.impressions or "",
            seed_backlinks=item.backlinks or "",
        )
        final_key = path_key(path_of(row.get("final_url") or item.url))
        canonical = row.get("canonical") or ""
        if page_class in ("ok", "shell_only"):
            if not canonical:
                row["canonical_status"] = "missing"
            elif not same_site(canonical, self.s.hosts):
                row["canonical_status"] = "cross_site"
            elif path_key(path_of(canonical)) == final_key:
                row["canonical_status"] = "self"
            else:
                row["canonical_status"] = "other"
        row["_issues"] = _issues(row, item, page_class, noindex)
        for key in [k for k in row if k.startswith("_") and k != "_issues"]:
            row.pop(key)
        return row

    def _match_articles(self, rows: dict[str, dict]) -> None:
        by_slug = defaultdict(list)
        by_path = {}
        for url, row in rows.items():
            if row["kind"] in ("media", "asset", "system", "feed", "sitemap"):
                continue
            by_slug[last_segment(row["path"])].append(url)
            by_path[path_key(row["path"])] = url
        for record in self.articles:
            matched, how = "", ""
            if record["url"]:
                matched = by_path.get(
                    path_key(path_of(clean_url(record["url"], self.s.base_url) or "")), ""
                )
                how = "url" if matched else ""
            if not matched and record["slug"]:
                candidates = by_slug.get(record["slug"], [])
                ok = [u for u in candidates if not _broken(rows[u])] or candidates
                matched, how = (ok[0], "slug") if ok else ("", "")
            if not matched and record["id"]:
                for prefix in ("/article/", "/articles/"):
                    url = by_path.get(f"{prefix}{record['id']}")
                    if url:
                        matched, how = url, "id"
                        break
            row = rows.get(matched, {})
            published = record["status"] in ("", "published", "publish", "live")
            record.update(
                matched_url=matched,
                match=how,
                in_sitemap=bool(row.get("in_sitemap")),
                in_archive=bool(row.get("in_archive")),
                missing_from_archive=published and not row.get("in_archive"),
                no_public_url=published and not matched,
            )
            if row:
                row["kind"] = "article"
                if published and not row.get("in_archive"):
                    row["_issues"].append("missing_from_archive")
                if not row.get("author") and record["author"]:
                    row["author"] = record["author"]
                if not row.get("published_time") and record["published_at"]:
                    row["published_time"] = record["published_at"]


def _kind(path: str, row: dict) -> str:
    kind = classify_path(path)
    ctype = row.get("content_type", "")
    if ctype.startswith(("image/", "video/", "audio/")) or ctype == "application/pdf":
        return "media"
    if kind in ("page", "home", "category") and (
        row.get("og_type") == "article"
        or row.get("schema_type") in ("Article", "BlogPosting", "NewsArticle")
    ):
        return "article" if kind != "home" else kind
    if kind == "page" and row.get("schema_type") == "CollectionPage":
        return "category"
    return kind


def _page_class(row: dict, probe: dict) -> str:
    final = as_int(row.get("final_status"))
    if row.get("error") and not final:
        return "error"
    if row.get("error") in ("redirect loop", "too many redirects", "unusable Location header"):
        return "redirect_error"
    if final in GONE_STATUSES:
        return "gone"
    if 400 <= final < 500:
        return "client_error"
    if final >= 500:
        return "server_error"
    if final in REDIRECT_CODES or (row.get("error") and final != 200):
        return "redirect_error"
    title = (row.get("title") or "").lower()
    if final == 200 and ("page not found" in title or title.startswith("404")):
        return "soft_404"
    if (
        final == 200
        and probe.get("status") == 200
        and row.get("_fingerprint") == probe.get("fingerprint")
    ):
        return "shell_only"
    return "ok"


def _broken(row: dict) -> bool:
    return row.get("page_class") in ("gone", "client_error", "server_error", "error",
                                     "redirect_error", "soft_404")  # fmt: skip


def _issues(row: dict, item: Item, page_class: str, noindex: bool) -> list[str]:
    issues = []
    hops = as_int(row.get("redirect_hops"))
    if hops > 1:
        issues.append("redirect_chain")
    if hops and any(f"{c} " in row.get("redirect_chain", "") for c in (302, 303, 307)):
        issues.append("temporary_redirect")
    if row.get("error") == "redirect loop":
        issues.append("redirect_loop")
    elif row.get("error") == "redirects off-site (not requested)":
        issues.append("redirect_offsite")
    if page_class in ("soft_404", "shell_only", "server_error", "error", "redirect_error"):
        issues.append(page_class)
    if page_class == "ok":
        if not row.get("canonical"):
            issues.append("missing_canonical")
        elif row.get("canonical_status") in ("other", "cross_site"):
            issues.append("canonical_elsewhere")
        if as_int(row.get("_canonical_count")) > 1:
            issues.append("multiple_canonicals")
        if not row.get("title"):
            issues.append("missing_title")
        if not row.get("meta_description") and row.get("kind") != "media":
            issues.append("missing_description")
    if noindex:
        issues.append("noindex")
        if item.in_sitemap or item.clicks or item.backlinks or row.get("kind") in (
            "article", "home", "category"
        ) or row.get("canonical_status") == "self":  # fmt: skip
            issues.append("accidental_noindex")
    if item.in_sitemap and (page_class != "ok" or hops or noindex):
        issues.append("sitemap_lists_non_indexable")
    if row.get("kind") == "article" and not item.in_archive and not item.in_sitemap:
        issues.append("missing_from_archive")
    return issues


def _seed_rows(path: str) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8-sig")
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    if "," in first or "\t" in first:
        from .core import read_csv_text

        if "\t" in first and "," not in first:
            text = text.replace("\t", ",")
        rows = read_csv_text(text)
        if rows and any(c in rows[0] for c in URL_COLUMNS):
            return rows
    return [{"url": line.strip()} for line in text.splitlines() if line.strip().startswith("http")]


def _records(data) -> list[dict]:
    """Article lists from common API shapes: [...], {data: [...]}, {data: {articles: [...]}}."""
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ("data", "articles", "items", "results", "posts"):
            if key in data:
                found = _records(data[key])
                if found:
                    return found
    return []


def _article(row: dict, source: str) -> dict:
    def pick(*keys):
        for key in keys:
            value = row.get(key)
            if isinstance(value, dict):
                value = value.get("name") or value.get("slug") or value.get("title")
            if value not in (None, ""):
                return str(value).strip()
        return ""

    return {
        "source": source,
        "id": pick("id", "article_id"),
        "slug": pick("slug", "original_slug"),
        "title": pick("title", "name"),
        "author": pick("author", "author_name", "writer", "user"),
        "published_at": pick("published_at", "publishedAt", "date", "date_published"),
        "modified_at": pick("updated_at", "updatedAt", "modified", "date_modified"),
        "status": pick("status").lower(),
        "category": pick("category", "category_name", "category_slug"),
        "section": pick("section", "section_name", "section_slug"),
        "url": pick("url", "permalink", "link", "canonical_url", "original_url"),
    }


def run(settings: Settings, fetcher: Fetcher, out_dir: str | Path) -> dict:
    inv = Inventory(settings, fetcher)
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    inv.run_probe()
    inv.discover_sitemaps()
    inv.load_seeds()
    inv.load_articles()
    inv.add(settings.base_url, "start")
    inv.crawl()
    rows, links, articles = inv.finish()
    out = Path(out_dir)
    write_csv(out / "inventory.csv", INVENTORY_FIELDS, sorted(rows, key=lambda r: r["url"]))
    write_csv(out / "links.csv", LINK_FIELDS, links)
    write_csv(out / "legacy-articles.csv", ARTICLE_FIELDS, articles)
    summary = {
        "started_at": started,
        "finished_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_url": settings.base_url,
        "hosts": settings.hosts,
        "requests": fetcher.requests,
        "urls": len(rows),
        "checked": inv.fetched,
        "probe": inv.probe,
        "page_classes": _count(r["page_class"] for r in rows),
        "kinds": _count(r["kind"] for r in rows),
        "articles_records": len(articles),
        "articles_without_public_url": sum(1 for a in articles if a["no_public_url"]),
        "broken_links": sum(1 for link in links if link["broken"]),
        "notes": inv.notes,
    }
    (out / "run.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _count(values) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for v in values:
        out[str(v or "-")] += 1
    return dict(sorted(out.items()))
