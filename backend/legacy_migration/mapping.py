"""Legacy-to-new URL mapping: proposals, validation, 410 rules and the content worklist.

Rules, in order (the first that applies wins):
 1. An approved decision from --overrides (a reviewed mapping file) is kept as is.
 2. The same path exists on the new site                      -> KEEP
 3. The legacy URL already redirected to a page we can place   -> REDIRECT_301 (flattened)
 4. A CMS record names this URL or slug as its original        -> REDIRECT_301
 5. A new article has the same slug (never invented)           -> REDIRECT_301
    (article URLs never depend on categories or sections)
 6. An approved taxonomy decision for a category URL, or an
    alias rule (e.g. /about-us -> /about), with a live target  -> REDIRECT_301
    (legacy categories are never matched to new topics automatically)
 7. Gone (404/410) in >= 2 inventories >= 7 days apart, no
    traffic, backlinks or article evidence                     -> RETIRE_410
 8. Everything else                                            -> REVIEW (with the reason)

Nothing is ever redirected to the homepage except homepage aliases (/index.html, /home),
one 404 never retires a URL, and every proposal needs ``approved=yes`` before it is
applied (CMS redirects, Nginx 410 rules).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .core import (
    ACTIONS,
    HOME_ALIASES,
    as_int,
    last_segment,
    path_key,
    path_of,
    publication_status,
    read_csv,
    truthy,
    write_csv,
)

MAPPING_FIELDS = (
    "legacy_url", "legacy_path", "kind", "variants", "legacy_status", "legacy_class",
    "observations", "last_checked", "title", "author", "published_time", "in_sitemap",
    "seed_clicks", "seed_impressions", "seed_backlinks", "priority", "action", "target_path",
    "confidence", "reason", "content_action", "approved", "approved_by", "note",
)  # fmt: skip
WORKLIST_FIELDS = (
    "priority", "content_action", "legacy_url", "keep_slug", "new_path", "title", "author",
    "published_time", "modified_time", "category", "word_count", "legacy_class", "source",
    "notes",
)  # fmt: skip
EXCLUDED_KINDS = ("system", "asset", "sitemap", "search")

# Renamed built-in pages between the legacy site and the new one. Applied only when the
# target is live on the new site, and still subject to approval like every proposal.
DEFAULT_ALIASES = {
    "/about-us": "/about",
    "/terms-of-service": "/terms",
    "/privacy": "/privacy-policy",
    "/contact-us": "/contact",
}
RETIRE_MIN_OBSERVATIONS = 2
RETIRE_MIN_DAYS = 7
SAFE_PATH = re.compile(r"^/[A-Za-z0-9/_\-.~%]*$")


@dataclass
class Observation:
    checked_at: str
    final_status: int
    page_class: str


@dataclass
class Entry:
    key: str
    rows: list[dict] = field(default_factory=list)  # latest run first
    observations: list[Observation] = field(default_factory=list)
    variants: set[str] = field(default_factory=set)

    @property
    def row(self) -> dict:
        return self.rows[0]

    @property
    def traffic(self) -> int:
        return sum(
            as_int(self.row.get(k)) for k in ("seed_clicks", "seed_impressions", "seed_backlinks")
        )


@dataclass
class NewSite:
    paths: dict[str, dict]  # path key -> record (live, public pages only)
    by_original_url: dict[str, str]
    by_original_slug: dict[str, str]
    article_slugs: dict[str, str]
    topic_slugs: dict[str, str]

    @classmethod
    def load(cls, path: str | Path | None) -> NewSite:
        site = cls({}, {}, {}, {}, {})
        if not path:
            return site
        for row in read_csv(path):
            if row.get("status", "live") not in ("live", "published", "active", ""):
                continue
            key = path_key(row.get("path", ""))
            site.paths[key] = row
            kind = row.get("kind", "")
            slug = row.get("slug") or last_segment(key)
            if kind == "article":
                site.article_slugs[slug] = key
            elif kind == "topic":
                site.topic_slugs[slug] = key
            if row.get("original_url"):
                site.by_original_url[path_key(path_of(row["original_url"]))] = key
            if row.get("original_slug"):
                site.by_original_slug[row["original_slug"]] = key
        return site


@dataclass
class Decision:
    action: str
    target: str = ""
    confidence: str = ""
    reason: str = ""


def load_inventories(paths: list[str | Path]) -> dict[str, Entry]:
    """Merge inventory runs by path key (www/apex, trailing slash and http(s) variants)."""
    entries: dict[str, Entry] = {}
    runs = []
    for path in paths:
        rows = read_csv(path)
        stamp = max((r.get("checked_at", "") for r in rows), default="")
        runs.append((stamp, rows))
    for _, rows in sorted(runs, key=lambda r: r[0], reverse=True):
        for row in rows:
            key = path_key(row.get("path") or path_of(row.get("url", "")))
            entry = entries.setdefault(key, Entry(key))
            entry.rows.append(row)
            entry.variants.add(row.get("url", ""))
            if row.get("checked_at") and row.get("page_class") not in ("", "not_checked"):
                entry.observations.append(
                    Observation(
                        row["checked_at"], as_int(row.get("final_status")), row["page_class"]
                    )
                )
    for entry in entries.values():
        # Representative row: the latest checked one, preferring the sitemap's spelling.
        checked = [r for r in entry.rows if r.get("checked_at")] or entry.rows
        latest = max(r.get("checked_at", "") for r in checked)
        current = [r for r in checked if r.get("checked_at", "") == latest]
        current.sort(key=lambda r: (not truthy(r.get("in_sitemap")), len(r.get("url", ""))))
        entry.rows.sort(key=lambda r: r is not current[0])
    return entries


def _gone_evidence(entry: Entry) -> tuple[int, int]:
    """(distinct gone observations, days between first and last of them)."""
    days = sorted({o.checked_at[:10] for o in entry.observations if o.final_status in (404, 410)})
    if not days:
        return 0, 0
    try:
        span = (datetime.fromisoformat(days[-1]) - datetime.fromisoformat(days[0])).days
    except ValueError:
        span = 0
    return len(days), span


class Mapper:
    def __init__(
        self,
        entries: dict[str, Entry],
        site: NewSite,
        *,
        articles: list[dict] | None = None,
        overrides: list[dict] | None = None,
        aliases: dict[str, str] | None = None,
        retire_min_observations: int = RETIRE_MIN_OBSERVATIONS,
        retire_min_days: int = RETIRE_MIN_DAYS,
        taxonomy=None,
    ):
        self.entries = entries
        self.site = site
        self.taxonomy = taxonomy  # rewrite.Taxonomy: approved editorial decisions only
        self.articles = articles or []
        self.aliases = {path_key(k): path_key(v) for k, v in (aliases or DEFAULT_ALIASES).items()}
        self.min_obs = retire_min_observations
        self.min_days = retire_min_days
        self.slug_by_id = {
            a["id"]: a["slug"] for a in self.articles if a.get("id") and a.get("slug")
        }
        self.article_paths = {
            path_key(path_of(a["matched_url"])) for a in self.articles if a.get("matched_url")
        }
        self.record_status = {
            path_key(path_of(a["matched_url"])): publication_status(a)
            for a in self.articles
            if a.get("matched_url")
        }
        self.overrides = {}
        for row in overrides or []:
            key = path_key(row.get("legacy_path") or path_of(row.get("legacy_url", "")))
            if row.get("action") and truthy(row.get("approved")):
                self.overrides[key] = row

    # ---- rules -----------------------------------------------------------------------

    def _place(self, key: str, kind: str) -> Decision | None:
        """Where a legacy path lives on the new site, without inventing anything."""
        site = self.site
        if key in site.paths:
            return Decision("KEEP", key, "exact", "Same path exists on the new site.")
        if key in site.by_original_url:
            return Decision(
                "REDIRECT_301", site.by_original_url[key], "cms_original_url",
                "A CMS record lists this URL as its original URL.",
            )  # fmt: skip
        slug = last_segment(key)
        if kind == "article" and slug.isdigit() and slug in self.slug_by_id:
            slug = self.slug_by_id[slug]  # /article/<id> -> the article's own slug
        if kind in ("article", "page") and slug in site.by_original_slug:
            return Decision(
                "REDIRECT_301", site.by_original_slug[slug], "cms_original_slug",
                f"A CMS article keeps the original slug '{slug}'.",
            )  # fmt: skip
        if kind in ("article", "page") and slug in site.article_slugs:
            return Decision(
                "REDIRECT_301", site.article_slugs[slug], "slug",
                f"New article with the same slug '{slug}'.",
            )  # fmt: skip
        # Legacy taxonomy is never reused automatically: a category/section URL moves
        # only by an approved editorial taxonomy decision (--taxonomy).
        if kind in ("category", "page") and self.taxonomy is not None:
            topic = self.taxonomy.topic_path_for(key)
            if topic and topic in site.paths:
                return Decision(
                    "REDIRECT_301", topic, "taxonomy",
                    f"Approved taxonomy decision: {key} -> {topic}.",
                )  # fmt: skip
        alias = self.aliases.get(key)
        if alias and alias in site.paths:
            return Decision("REDIRECT_301", alias, "rule", f"Renamed page ({key} -> {alias}).")
        return None

    def decide(self, entry: Entry) -> Decision:
        row = entry.row
        kind = row.get("kind", "page")
        if entry.key in self.overrides:
            o = self.overrides[entry.key]
            return Decision(
                o["action"].upper(), path_key(o["target_path"]) if o.get("target_path") else "",
                "manual", o.get("reason") or "Approved decision.",
            )  # fmt: skip
        placed = self._place(entry.key, kind)
        if placed and placed.action == "KEEP":
            return placed
        final_url = row.get("final_url", "")
        page_class = row.get("page_class", "")
        if final_url and page_class == "ok":
            final_key = path_key(path_of(final_url))
            if final_key != entry.key:
                if final_key == "/" and entry.key not in HOME_ALIASES:
                    return Decision(
                        "REVIEW", "", "",
                        "The legacy site redirects this URL to the homepage: choose the "
                        "matching page or retire it (no homepage redirects).",
                    )  # fmt: skip
                final_kind = self.entries.get(final_key, Entry(final_key, [{}])).row.get(
                    "kind", kind
                )
                target = self._place(final_key, final_kind)
                if target:
                    return Decision(
                        "REDIRECT_301", target.target, target.confidence,
                        f"Legacy site redirected to {final_key}; {target.reason}",
                    )  # fmt: skip
        if placed:
            return placed
        if entry.key in HOME_ALIASES and "/" in self.site.paths:
            return Decision("REDIRECT_301", "/", "rule", "Homepage alias.")
        if page_class == "gone":
            count, span = _gone_evidence(entry)
            evidence = (
                entry.traffic or kind == "article" or entry.key in self.article_paths
                or truthy(row.get("in_sitemap")) or as_int(row.get("inlinks"))
            )  # fmt: skip
            if count >= self.min_obs and span >= self.min_days and not evidence:
                return Decision(
                    "RETIRE_410", "", "observed_gone",
                    f"Gone in {count} inventories over {span} days; no traffic or links.",
                )  # fmt: skip
            why = (
                "Search traffic, backlinks, links or article evidence"
                if evidence
                else f"Gone in {count} inventory(ies) over {span} days (needs "
                f"{self.min_obs} over {self.min_days}+ days)"
            )
            return Decision("REVIEW", "", "", f"{why}: confirm before retiring.")
        reasons = {
            "shell_only": "Page HTML is the app shell; confirm the content from an export.",
            "soft_404": "Legacy page looks like a 'not found' page with status 200.",
            "server_error": "Legacy server error; check again.",
            "error": "Legacy URL could not be fetched; check again.",
            "redirect_error": "Legacy redirect loop or broken redirect.",
            "not_checked": "Not checked in the inventory.",
        }
        if page_class in reasons:
            return Decision("REVIEW", "", "", reasons[page_class])
        if kind == "article":
            return Decision(
                "REVIEW", "", "",
                f"Not in the new CMS yet: import keeping the slug '{last_segment(entry.key)}'.",
            )  # fmt: skip
        if kind == "media":
            return Decision("REVIEW", "", "", "Image/file not in the new media library.")
        return Decision("REVIEW", "", "", "No matching page on the new site.")

    def content_action(self, entry: Entry, decision: Decision) -> str:
        row = entry.row
        kind = row.get("kind", "")
        if decision.action != "REVIEW" or kind not in ("article", "media", "category", "page"):
            return "NONE"
        if kind == "media":
            return "IMPORT_MEDIA"
        if kind == "article":
            # Published articles are rewritten from scratch (rewrite-plan); legacy text is
            # never copied. A draft record is neither rewritten nor imported.
            if self.record_status.get(entry.key) == "draft":
                return "DRAFT_NO_ACTION"
            return "REWRITE" if row.get("page_class") in ("ok", "shell_only") else "REVIEW"
        if row.get("page_class") not in ("ok", "shell_only"):
            return "REVIEW"
        return "CREATE_OR_REDIRECT"

    def priority(self, entry: Entry) -> str:
        row = entry.row
        if entry.traffic or truthy(row.get("in_sitemap")) or row.get("kind") in (
            "home", "article", "category",
        ) or entry.key in self.article_paths:  # fmt: skip
            return "high"
        return "normal"

    def rows(self) -> tuple[list[dict], list[dict]]:
        mapping, excluded = [], []
        for key, entry in sorted(self.entries.items()):
            row = entry.row
            if row.get("kind") in EXCLUDED_KINDS:
                excluded.append({"legacy_path": key, "kind": row.get("kind")})
                continue
            decision = self.decide(entry)
            override = self.overrides.get(key, {})
            mapping.append(
                {
                    "legacy_url": row.get("url", ""),
                    "legacy_path": key,
                    "kind": row.get("kind", ""),
                    "variants": len(entry.variants),
                    "legacy_status": row.get("final_status", ""),
                    "legacy_class": row.get("page_class", ""),
                    "observations": ";".join(
                        f"{o.checked_at[:10]}={o.final_status or o.page_class}"
                        for o in entry.observations
                    ),
                    "last_checked": row.get("checked_at", ""),
                    "title": row.get("title", ""),
                    "author": row.get("author", ""),
                    "published_time": row.get("published_time", ""),
                    "in_sitemap": row.get("in_sitemap", ""),
                    "seed_clicks": row.get("seed_clicks", ""),
                    "seed_impressions": row.get("seed_impressions", ""),
                    "seed_backlinks": row.get("seed_backlinks", ""),
                    "priority": self.priority(entry),
                    "action": decision.action,
                    "target_path": decision.target,
                    "confidence": decision.confidence,
                    "reason": decision.reason,
                    "content_action": self.content_action(entry, decision),
                    "approved": "yes" if override else ("yes" if decision.action == "KEEP" else ""),
                    "approved_by": override.get("approved_by", ""),
                    "note": override.get("note", ""),
                }
            )
        return mapping, excluded

    def worklist(self, mapping: list[dict]) -> list[dict]:
        """Content to import or rewrite in the new CMS (slugs kept, never regenerated)."""
        records = defaultdict(dict)
        for a in self.articles:
            if a.get("matched_url"):
                records[path_key(path_of(a["matched_url"]))] = a
        out = []
        for m in mapping:
            if m["content_action"] in ("NONE", "", "DRAFT_NO_ACTION"):
                continue
            entry = self.entries[m["legacy_path"]]
            record = records.get(m["legacy_path"], {})
            slug = last_segment(m["legacy_path"])
            if slug.isdigit() and record.get("slug"):
                slug = record["slug"]
            new_path = f"/articles/{slug}" if m["kind"] == "article" else ""
            out.append(
                {
                    "priority": m["priority"],
                    "content_action": m["content_action"],
                    "legacy_url": m["legacy_url"],
                    "keep_slug": slug if m["kind"] == "article" else "",
                    "new_path": new_path,
                    "title": m["title"] or record.get("title", ""),
                    "author": m["author"] or record.get("author", ""),
                    "published_time": m["published_time"] or record.get("published_at", ""),
                    "modified_time": entry.row.get("modified_time")
                    or record.get("modified_at", ""),
                    "category": entry.row.get("section") or record.get("category", ""),
                    "word_count": entry.row.get("word_count", ""),
                    "legacy_class": m["legacy_class"],
                    "source": "inventory",
                    "notes": m["reason"],
                }
            )
        for a in self.articles:  # published records with no URL found: never invent one
            if truthy(a.get("no_public_url")) and publication_status(a) == "published":
                out.append(
                    {
                        "priority": "high",
                        "content_action": "FIND_URL",
                        "legacy_url": "",  # unknown: found in Search Console, never guessed
                        "keep_slug": a.get("slug", ""),
                        "new_path": "",
                        "title": a.get("title", ""),
                        "author": a.get("author", ""),
                        "published_time": a.get("published_at", ""),
                        "modified_time": a.get("modified_at", ""),
                        "category": a.get("category") or a.get("section", ""),
                        "source": a.get("source", ""),
                        "notes": "Published article with no public URL found: look it up in "
                        "Search Console or backups before importing.",
                    }
                )
        return out


# ---- validation ------------------------------------------------------------------------


def validate(rows: list[dict], site: NewSite | None = None) -> list[dict]:
    """Problems that block applying a mapping file (``error``) or need a look (``warning``)."""
    problems = []

    def add(row, code, message, severity="error"):
        problems.append(
            {"legacy_path": row.get("legacy_path", ""), "code": code, "message": message,
             "severity": severity}
        )  # fmt: skip

    sources: dict[str, str] = {}
    redirects: dict[str, str] = {}
    for row in rows:
        key = path_key(row.get("legacy_path") or path_of(row.get("legacy_url", "")))
        row["legacy_path"] = key
        action = (row.get("action") or "").upper()
        target = row.get("target_path", "").strip()
        if action not in ACTIONS:
            add(row, "invalid_action", f"Action must be one of {', '.join(ACTIONS)}.")
            continue
        if key in sources:
            add(row, "duplicate_source", f"{key} is mapped twice.")
        sources[key] = action
        if not SAFE_PATH.match(key):
            add(row, "unsafe_path", "Legacy path contains characters that can't be served.")
        if action == "KEEP":
            if target and path_key(target) != key:
                add(row, "keep_with_other_target", "KEEP means the same path; use REDIRECT_301.")
            if site is not None and site.paths and key not in site.paths:
                add(row, "keep_missing_on_new_site", "Path is not live on the new site.")
        elif action == "REDIRECT_301":
            if not target:
                add(row, "missing_target", "REDIRECT_301 needs a target_path.")
                continue
            if not target.startswith("/") or target.startswith("//"):
                add(row, "external_target", "Targets must be paths on the new site.")
                continue
            tkey = path_key(target)
            if tkey == key:
                add(row, "self_redirect", "A path cannot redirect to itself.")
            if tkey == "/" and key not in HOME_ALIASES:
                add(row, "homepage_redirect", "No homepage redirects: map to a matching page.")
            redirects[key] = tkey
            if site is not None and site.paths and tkey not in site.paths:
                add(row, "target_missing", f"Target {tkey} is not live on the new site.")
        elif action == "RETIRE_410":
            if target:
                add(row, "retire_with_target", "RETIRE_410 must not have a target.")
            gone_days = {
                o.split("=", 1)[0]
                for o in (row.get("observations") or "").split(";")
                if o.endswith(("=404", "=410"))
            }
            if not truthy(row.get("approved")) and len(gone_days) < RETIRE_MIN_OBSERVATIONS:
                add(
                    row,
                    "retire_without_evidence",
                    "Retire only after repeated 404/410 observations or an approved decision.",
                )
        elif action == "REVIEW":
            add(row, "unresolved", row.get("reason") or "Needs a decision.", "warning")
    for source, target in redirects.items():
        seen, hop = {source}, target
        while hop in redirects:
            if hop in seen:
                add({"legacy_path": source}, "redirect_loop", f"{source} loops back via {hop}.")
                break
            seen.add(hop)
            hop = redirects[hop]
        else:
            if target in redirects:
                add({"legacy_path": source}, "redirect_chain",
                    f"{target} redirects again: point straight to {hop}.")  # fmt: skip
            if sources.get(target) == "RETIRE_410":
                add({"legacy_path": source}, "redirect_to_retired", f"{target} is retired (410).")
    return problems


def nginx_gone_rules(rows: list[dict]) -> str:
    """``location = /path { return 410; }`` for approved RETIRE_410 rows (both slash forms)."""
    lines = [
        "# Generated by `python -m legacy_migration gone-conf` from approved RETIRE_410 rows.",
        "# Include inside the server block: include /etc/nginx/snippets/tpa-legacy-gone.conf;",
    ]
    for row in sorted(rows, key=lambda r: r.get("legacy_path", "")):
        if (row.get("action") or "").upper() != "RETIRE_410" or not truthy(row.get("approved")):
            continue
        key = path_key(row.get("legacy_path") or "")
        if key in HOME_ALIASES or not SAFE_PATH.match(key):
            continue
        lines.append(f"location = {key} {{ return 410; }}")
        lines.append(f"location = {key}/ {{ return 410; }}")
    return "\n".join(lines) + "\n"


def write_mapping(path, rows):
    return write_csv(path, MAPPING_FIELDS, rows)


def write_worklist(path, rows):
    return write_csv(path, WORKLIST_FIELDS, rows)


def load_aliases(path: str | None) -> dict[str, str]:
    aliases = dict(DEFAULT_ALIASES)
    if path:
        for row in read_csv(path):
            if row.get("legacy_path") and row.get("target_path"):
                aliases[row["legacy_path"]] = row["target_path"]
    return aliases
