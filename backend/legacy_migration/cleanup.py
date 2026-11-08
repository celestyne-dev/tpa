"""Historical URL cleanup: resolve obsolete URLs from earlier versions of the website.

Imports Search Console coverage-report exports, deduplicates the URLs, reconciles each one
against the legacy CMS (published articles, drafts, canonical URLs) and the new site's
approved routes, and classifies it:

  KEEP_200      the URL is (or will be) a live page on the new site
  REDIRECT_301  one direct permanent redirect to an approved, live destination
  RETIRE_410    explicitly gone (exact-path Nginx rule, approved)
  ALLOW_404     nothing to do: the new site answers with a genuine 404
  REVIEW        a person decides

Protection rules (validation errors, never warnings):
- A published article's URLs can only be KEEP_200 (canonical path preserved) or a
  REDIRECT_301 to its new path. A URL whose last segment is a published article's slug is
  never retired or left to 404. Search Console status never overrides this.
- Draft URLs can't be KEEP_200 (drafts are never published).
- Essential routes of the new site are KEEP_200 only; app areas (``/api``, ``/media``,
  ``/admin``, customer pages...) never get redirects or 410 rules.

Nothing is applied: 301s are exported for ``flask legacy import-redirects`` (dry run by
default) and 410s as an Nginx snippet, both only from approved, validated rows.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from .core import HOME_ALIASES, clean_url, last_segment, path_key, same_site, truthy, write_csv
from .gsc import _date, _tables, normalise_index_status
from .inventory import _article
from .mapping import DEFAULT_ALIASES
from .rewrite import Taxonomy, build_plan

CLASSES = ("KEEP_200", "REDIRECT_301", "RETIRE_410", "ALLOW_404", "REVIEW")

# The new site's own pages (mirrors seo_service.STATIC_PATHS and frontend routes; a test
# keeps them in sync).
ESSENTIAL_PATHS = frozenset(
    {
        "/", "/articles", "/authors", "/topics", "/shop", "/free-resources", "/resources",
        "/courses",
        "/membership", "/newsletter", "/partner-with-us", "/advertise", "/about", "/contact",
        "/privacy-policy", "/terms", "/affiliate-disclosure", "/login", "/register",
        "/verify-email", "/forgot-password", "/reset-password", "/sitemap.xml", "/robots.txt",
        "/404.html", "/manifest.webmanifest", "/favicon.ico", "/icon.svg",
        "/newsletter/confirm", "/newsletter/preferences", "/newsletter/unsubscribe",
        "/resources/access", "/search", "/feed.xml",
    }
)  # fmt: skip
# Client-rendered shells: any path below answers 200 with its own noindex app shell.
APP_SHELL_PREFIXES = ("/admin", "/learn", "/certificates")
# Application areas: no 301 or 410 rule may ever be placed here (a 404 is fine).
NO_RULE_PREFIXES = (
    "/api", "/media", "/assets", "/images", "/icons", "/static", "/og", "/_redirect",
    "/_protected_downloads", "/.well-known", "/cart", "/checkout", "/account", "/purchases",
    "/authors", *APP_SHELL_PREFIXES,
)  # fmt: skip
# Listing pages the prerender generates (/articles/page/2, /topics/<slug>/page/2, ...): an
# exact-path 410 or 301 rule there would shadow a real page, so none may be placed.
GENERATED_PAGINATION = re.compile(r"^/(?:articles|topics/[^/]+|authors/[^/]+)/page/[0-9]+/?$")
FORUM_PREFIXES = ("/forums", "/forum", "/community", "/discussions", "/discussion")
LEGACY_SHOP_PREFIXES = ("/shop", "/store", "/product", "/products", "/cart", "/checkout")
PREVIOUS_ARTICLE_ROUTES = (
    re.compile(r"^/article/(?P<id>\d+)$"),  # the April 2026 app: /article/<id>
    re.compile(r"^/(?:19|20)\d\d/\d\d(?:/\d\d)?/(?P<slug>[^/]+)$"),
    re.compile(r"^/(?:blog|post|posts|story|stories)/(?P<slug>[^/]+)$"),
)
FILTER_PARAMS = {
    "category", "categories", "tag", "tags", "sort", "order", "orderby", "filter", "page",
    "p", "paged", "q", "s", "search", "query", "section", "author", "type", "view", "limit",
}  # fmt: skip
TRACKING_PARAMS = re.compile(r"^(utm_\w+|fbclid|gclid|msclkid|ref|source|mc_\w+)$")
NGINX_SAFE = re.compile(r"^/[A-Za-z0-9/_\-.~]*$")  # exact paths only, no quoting needed

DECISION_FIELDS = (
    "url", "path", "path_key", "query", "variants", "reports", "index_statuses",
    "last_crawled", "family", "cms_id", "cms_status", "protected", "new_site_live",
    "proposed_class", "proposed_target", "reason", "decision", "target", "approved",
    "approved_by", "notes", "effective_class", "effective_target", "problems",
)  # fmt: skip
EDITOR_FIELDS = ("decision", "target", "approved", "approved_by", "notes")


def _starts(path: str, prefixes) -> bool:
    return any(path == p or path.startswith(p + "/") for p in prefixes)


def _app_area(path: str) -> bool:
    """Where no 301 or 410 rule may ever be placed: application areas and the listing
    pages the new site generates."""
    return _starts(path, NO_RULE_PREFIXES) or bool(GENERATED_PAGINATION.match(path))


# ---- import ---------------------------------------------------------------------------


def load_coverage(files: list[tuple[str, str]], base_url: str) -> tuple[dict[str, dict], dict]:
    """Coverage-report exports -> {normalised URL: evidence}, plus import counts.

    ``files`` pairs (label, path); an empty label is taken from the export's
    Metadata.csv or the file name. http/https and www/apex spellings are one URL.
    """
    base = urlsplit(base_url)
    hosts = [base.netloc] if base.netloc else []
    urls: dict[str, dict] = {}
    raw = 0
    for label, file in files:
        for name, rows, metadata in _tables(file):
            report = label or next(
                (metadata[k] for k in ("issue", "reason", "status") if metadata.get(k)),
                Path(file).stem if name == Path(file).name else f"{Path(file).stem}/{name}",
            )
            for row in rows:
                value = next(
                    (
                        row[c]
                        for c in ("url", "page", "top pages", "address", "inspected url")
                        if row.get(c)
                    ),
                    "",
                )
                url = clean_url(value, base_url or None)
                if not url:
                    continue
                raw += 1
                parts = urlsplit(url)
                if hosts and same_site(url, hosts):  # one spelling per legacy URL
                    url = f"{base.scheme}://{base.netloc}{parts.path or '/'}" + (
                        f"?{parts.query}" if parts.query else ""
                    )
                entry = urls.setdefault(
                    url, {"reports": set(), "statuses": set(), "last_crawled": "", "seen": 0}
                )
                entry["seen"] += 1
                entry["reports"].add(report)
                reason = row.get("status") or row.get("reason") or row.get("issue") or report
                status = normalise_index_status(reason)
                if status:
                    entry["statuses"].add(status)
                crawled = row.get("last crawled", "")
                crawled = _date(crawled)
                if crawled > entry["last_crawled"]:
                    entry["last_crawled"] = crawled
    counts = {
        "rows": raw,
        "distinct_urls": len(urls),
        "distinct_paths": len({path_key(urlsplit(u).path or "/") for u in urls}),
        "query_variants": sum(1 for u in urls if urlsplit(u).query),
        "reports": sorted({r for e in urls.values() for r in e["reports"]}),
    }
    return urls, counts


# ---- context: what must be protected ----------------------------------------------------


class Context:
    def __init__(
        self,
        exports,
        *,
        inventory_rows=None,
        new_site_paths=None,
        taxonomy=None,
        extra_routes=None,
        base_url="",
    ):
        self.base_url = base_url
        self.hosts = [urlsplit(base_url).netloc] if base_url else []
        self.taxonomy = taxonomy or Taxonomy()
        self.new_site = set(new_site_paths or ()) | set(extra_routes or ())
        self.records = [_article(r, "export") for r in exports]
        plan = build_plan(
            exports, inventory_rows=inventory_rows, taxonomy=taxonomy, base_url=base_url
        )
        self.plan = plan["rewrite"]
        self.published_by_slug = {
            r["slug"]: r
            for r in self.records
            if r["publication_status"] == "published" and r["slug"]
        }
        self.draft_by_slug = {
            r["slug"]: r for r in self.records if r["publication_status"] == "draft" and r["slug"]
        }
        self.by_id = {r["id"]: r for r in self.records if r["id"]}
        # path key -> (allowed classes, required redirect target, reason, cms id)
        self.protected: dict[str, tuple[tuple[str, ...], str, str, str]] = {}
        self.new_path_by_id: dict[str, str] = {}
        self.planned_paths: set[str] = set()
        for p in self.plan:
            new_path = p.get("proposed_new_path", "")
            if new_path:
                self.new_path_by_id[p["legacy_id"]] = new_path
                self.planned_paths.add(new_path)
                self.protected[new_path] = (
                    ("KEEP_200",),
                    "",
                    "New path of a published article.",
                    p["legacy_id"],
                )
            for field in ("original_canonical_url", "original_url"):
                url = p.get(field)
                if not url:
                    continue
                key = self.key(url)
                if new_path and key == new_path:
                    self.protected[key] = (
                        ("KEEP_200",),
                        "",
                        "Published article: canonical path preserved.",
                        p["legacy_id"],
                    )
                elif new_path:
                    self.protected.setdefault(
                        key,
                        (
                            ("REDIRECT_301",),
                            new_path,
                            f"Published article moves to {new_path}.",
                            p["legacy_id"],
                        ),
                    )
                else:
                    self.protected.setdefault(
                        key,
                        (
                            ("KEEP_200", "REDIRECT_301", "REVIEW"),
                            "",
                            "Published article (new path undecided).",
                            p["legacy_id"],
                        ),
                    )
        for rec in self.records:
            if rec["publication_status"] == "draft":
                for field in ("url", "canonical_url"):
                    if rec.get(field):
                        self.protected.setdefault(
                            self.key(rec[field]),
                            (
                                ("ALLOW_404", "REDIRECT_301", "RETIRE_410", "REVIEW"),
                                "",
                                "Draft: never published on the new site.",
                                rec["id"],
                            ),
                        )

    def key(self, url: str) -> str:
        url = clean_url(url, self.base_url or None) or url
        if "://" in url and self.hosts and not same_site(url, self.hosts):
            parts = urlsplit(url)
            return f"{parts.hostname}{path_key(parts.path or '/')}"
        return path_key(unquote(urlsplit(url).path or "/"))

    def live(self, key: str) -> bool:
        return key in self.new_site or key in ESSENTIAL_PATHS or key in self.planned_paths


# ---- classification ---------------------------------------------------------------------


def family(key: str, query: str, ctx: Context) -> str:
    """What kind of historical URL this is (path rules, then CMS evidence)."""
    low = key.lower()
    segment = last_segment(key)
    protected = ctx.protected.get(key)
    if protected:
        rec = ctx.by_id.get(protected[3], {})
        return "draft" if rec.get("publication_status") == "draft" else "current_article"
    if not _app_area(low):
        if segment in ctx.published_by_slug:
            return "current_article"
        if segment in ctx.draft_by_slug:
            return "draft"
    if key == "/" or low in HOME_ALIASES:
        return "home"
    if any(p.match(key) for p in PREVIOUS_ARTICLE_ROUTES):
        return "previous_article_route"
    if _starts(low, FORUM_PREFIXES) or low.startswith(("/topic/", "/thread")):
        return "forum"
    if _starts(low, ("/api",)):
        return "api"
    if _starts(low, APP_SHELL_PREFIXES):
        return "app_shell"
    if _starts(low, ("/media", "/assets", "/images", "/icons", "/static", "/uploads", "/og")) or (
        re.search(r"\.(jpe?g|png|gif|webp|avif|svg|ico|pdf|js|css|map|woff2?)$", low)
    ):
        return "asset"
    if low.startswith(("/wp-", "/xmlrpc", "/.env", "/cgi-bin")) or low.endswith(".php"):
        return "probe"
    if _starts(low, LEGACY_SHOP_PREFIXES) or _starts(low, ("/account", "/purchases")):
        return "shop_account"
    if low in ("/search", "/feed", "/rss", "/rss.xml", "/atom.xml"):
        return "search_feed"
    first = low.strip("/").split("/")[0]
    if re.match(r"^/(category|categories|tag|tags|section|sections|topics?)/[^/]+$", low) or (
        low.count("/") == 1
        and (
            ctx.taxonomy.decision_for("category", first)
            or ctx.taxonomy.decision_for("section", first)
            or _is_taxonomy(first, ctx)
        )
    ):
        return "category"
    if low.count("/") == 1:
        return "page"
    return "unknown"


def is_filter(query: str) -> bool:
    """Listing filters/pagination (tracking parameters alone don't make a filter)."""
    params = {k.lower() for k, _ in parse_qsl(query, keep_blank_values=True)}
    params = {p for p in params if not TRACKING_PARAMS.match(p)}
    return bool(params) and params <= FILTER_PARAMS


def _is_taxonomy(slug: str, ctx: Context) -> bool:
    from .rewrite import _norm

    return any(
        _norm(r.get("category", "")) == slug or _norm(r.get("section", "")) == slug
        for r in ctx.records
    )


def propose(key: str, query: str, fam: str, evidence: dict, ctx: Context) -> tuple[str, str, str]:
    """(class, target, reason). Suggestions only; 301/410 need approval to take effect."""
    segment = last_segment(key)
    statuses = evidence.get("statuses", set())
    if key in ctx.protected:
        allowed, target, reason, _ = ctx.protected[key]
        if allowed == ("REDIRECT_301",):
            return "REDIRECT_301", target, reason
        if allowed == ("KEEP_200",):
            return "KEEP_200", "", reason
        if fam == "draft":
            return "ALLOW_404", "", reason + " The new site answers 404."
        return "REVIEW", "", reason
    if ctx.live(key):
        return "KEEP_200", "", "Live route on the new site."
    if fam == "current_article":
        rec = ctx.published_by_slug.get(segment)
        new_path = ctx.new_path_by_id.get(rec["id"], "") if rec else ""
        if new_path:
            return "REDIRECT_301", new_path, f"Same slug as published article {rec['id']}."
        return "REVIEW", "", "Same slug as a published article: protect it, find its URL."
    if fam == "draft":
        return "ALLOW_404", "", "Draft article: excluded from publishing; the new site answers 404."
    if fam == "previous_article_route":
        for pattern in PREVIOUS_ARTICLE_ROUTES:
            m = pattern.match(key)
            if not m:
                continue
            rec = (
                ctx.by_id.get(m.groupdict().get("id") or "")
                or ctx.published_by_slug.get(m.groupdict().get("slug") or "")
                or ctx.draft_by_slug.get(m.groupdict().get("slug") or "")
            )
            if (
                rec
                and rec["publication_status"] == "published"
                and ctx.new_path_by_id.get(rec["id"])
            ):
                return (
                    "REDIRECT_301",
                    ctx.new_path_by_id[rec["id"]],
                    (f"Previous article route of published article {rec['id']}."),
                )
            if rec and rec["publication_status"] == "published":
                return "REVIEW", "", "Previous route of a published article without a new path."
            if rec:
                return "ALLOW_404", "", "Previous route of a draft: never published."
            return "ALLOW_404", "", "Previous article route with no matching CMS record."
    if fam == "forum":
        return "RETIRE_410", "", "Obsolete forums (removed feature)."
    if fam == "shop_account":
        product = f"/shop/{segment}"
        if key.startswith("/shop/") and product in ctx.new_site and product != key:
            return "REDIRECT_301", product, "Same product slug on the new shop."
        if _app_area(key):
            return "ALLOW_404", "", "Old customer/cart path: the new app answers 404."
        return "RETIRE_410", "", "Obsolete shop path not in the new shop."
    if fam == "category":
        decision = ctx.taxonomy.decision_for("category", segment) or ctx.taxonomy.decision_for(
            "section", segment
        )
        if decision.get("decision") == "REPLACE":
            target = f"/topics/{decision['new_section']}"
            if ctx.live(target):
                return "REDIRECT_301", target, f"Approved taxonomy replacement: {target}."
            return "REVIEW", "", f"Taxonomy replaced by {target}, which is not live yet."
        if decision.get("decision") == "RETIRE":
            return "RETIRE_410", "", "Approved taxonomy retirement (abandoned category)."
        return "REVIEW", "", "Legacy category or section without a taxonomy decision."
    if fam in ("api", "asset", "probe", "search_feed"):
        return "ALLOW_404", "", f"{fam.replace('_', ' ')} URL: a genuine 404 is correct."
    if fam == "app_shell":
        return "KEEP_200", "", "Answered by a noindex app shell on the new site."
    alias = DEFAULT_ALIASES.get(key)
    if alias and ctx.live(alias):
        return "REDIRECT_301", alias, f"Renamed page ({key} -> {alias})."
    gone_only = statuses and statuses <= {
        "NOT_FOUND_404",
        "SOFT_404",
        "SERVER_ERROR",
        "BLOCKED_ACCESS",
        "REDIRECT_ERROR",
    }
    if gone_only:
        return "ALLOW_404", "", "Already gone for Google; no CMS record: a 404 is correct."
    return (
        "REVIEW",
        "",
        (
            "Unknown historical URL. Search Console status alone doesn't decide: check content "
            "and backlinks."
        ),
    )


def cleanup(
    coverage: dict[str, dict],
    ctx: Context,
    *,
    previous: list[dict] | None = None,
) -> dict:
    """One row per distinct URL. Query-string variants follow their path: Nginx rules and
    CMS redirects match the path, so a path is decided once for all its query strings."""
    prior = {r.get("url"): r for r in previous or [] if r.get("url")}
    by_path: dict[str, list[str]] = defaultdict(list)
    for url in coverage:
        by_path[ctx.key(url)].append(url)
    path_evidence: dict[str, dict] = {}
    for key, urls in by_path.items():
        merged = {"reports": set(), "statuses": set(), "last_crawled": ""}
        for url in urls:
            merged["reports"] |= coverage[url]["reports"]
            merged["statuses"] |= coverage[url]["statuses"]
            merged["last_crawled"] = max(merged["last_crawled"], coverage[url]["last_crawled"])
        path_evidence[key] = merged
    rows = []
    for url, evidence in sorted(coverage.items()):
        parts = urlsplit(url)
        key, query = ctx.key(url), parts.query
        path_family = family(key, "", ctx)
        proposed = propose(key, "", path_family, path_evidence[key], ctx)
        fam = path_family
        if query:
            fam = (
                "filter"
                if is_filter(query) and path_family in ("page", "category", "unknown")
                else (path_family)
            )
            if proposed[0] == "KEEP_200":
                proposed = (
                    "KEEP_200",
                    "",
                    f"Query variant of a live page ({key}): the page is "
                    "canonical without the query string.",
                )
            else:
                proposed = (
                    proposed[0],
                    proposed[1],
                    f"Query variant of {key}: follows the path "
                    f"(rules can't target query strings). {proposed[2]}",
                )
        protected = ctx.protected.get(key)
        cms_id = protected[3] if protected else ""
        if not cms_id and path_family in ("current_article", "draft"):
            rec = ctx.published_by_slug.get(last_segment(key)) or ctx.draft_by_slug.get(
                last_segment(key)
            )
            cms_id = rec["id"] if rec else ""
        cms = ctx.by_id.get(cms_id, {})
        row = {
            "url": url,
            "path": parts.path + (f"?{query}" if query else ""),
            "path_key": key,
            "query": query,
            "variants": len(by_path[key]),
            "reports": ";".join(sorted(evidence["reports"])),
            "index_statuses": ";".join(sorted(evidence["statuses"])),
            "last_crawled": evidence["last_crawled"],
            "family": fam,
            "cms_id": cms_id,
            "cms_status": cms.get("publication_status", ""),
            "protected": protected[2]
            if protected
            else ("Essential route." if key in ESSENTIAL_PATHS else ""),
            "new_site_live": "yes" if ctx.live(key) else "",
            "proposed_class": proposed[0],
            "proposed_target": proposed[1],
            "reason": proposed[2],
        }
        old = prior.get(url, {})
        for field in EDITOR_FIELDS:
            row[field] = old.get(field, "")
        row["decision"] = row["decision"].upper()
        rows.append(row)
    for row in rows:
        row["effective_class"], row["effective_target"] = _effective(row)
    problems = validate(rows, ctx)
    by_url = defaultdict(list)
    for p in problems:
        by_url[p["url"]].append(p["code"])
    for row in rows:
        row["problems"] = ";".join(by_url.get(row["url"], []))
    return {"rows": rows, "problems": problems}


def _effective(row: dict) -> tuple[str, str]:
    """What will actually happen: 301/410 only when approved by a named person."""
    decision = row.get("decision") or ""
    if decision in ("REDIRECT_301", "RETIRE_410"):
        if truthy(row.get("approved")) and row.get("approved_by"):
            return decision, path_key(row.get("target") or row.get("proposed_target") or "") if (
                decision == "REDIRECT_301"
            ) else ""
        return "REVIEW", ""
    if decision in ("KEEP_200", "ALLOW_404", "REVIEW"):
        return decision, ""
    proposed = row.get("proposed_class")
    if proposed in ("KEEP_200", "ALLOW_404"):
        return proposed, ""
    return "REVIEW", ""  # proposed 301/410 waiting for approval, or undecided


# ---- validation -------------------------------------------------------------------------


def validate(rows: list[dict], ctx: Context) -> list[dict]:
    problems = []

    def add(row, code, message, severity="error"):
        problems.append(
            {
                "url": row["url"],
                "path_key": row["path_key"],
                "code": code,
                "message": message,
                "severity": severity,
            }
        )

    # The class each path will actually get, from its rows (bare path first).
    path_class: dict[str, str] = {}
    for row in sorted(rows, key=lambda r: bool(r["query"])):
        path_class.setdefault(row["path_key"], row["effective_class"])
    decided: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        decision = row.get("decision") or ""
        key = row["path_key"]
        if not decision:
            continue
        if decision not in CLASSES:
            add(row, "invalid_class", f"Use one of {', '.join(CLASSES)}.")
            continue
        decided[key].add(decision)
        target = path_key(row.get("target") or row.get("proposed_target") or "")
        protected = ctx.protected.get(key)
        if protected:
            allowed, required, reason, _ = protected
            if decision not in allowed:
                add(row, "protected_url", f"{reason} Allowed: {', '.join(allowed)}.")
            elif decision == "REDIRECT_301" and required and target != required:
                add(row, "protected_target", f"Must redirect straight to {required}.")
        elif decision in ("RETIRE_410", "ALLOW_404") and row["family"] == "current_article":
            add(
                row,
                "published_slug_protected",
                "Same slug as a published article: never retired or left to 404.",
            )
        if decision != "KEEP_200" and (key in ESSENTIAL_PATHS or key in ctx.new_site):
            add(row, "essential_route", "Live route on the new site: KEEP_200 only.")
        if decision in ("REDIRECT_301", "RETIRE_410") and _app_area(key):
            add(row, "app_area", "No redirects or 410 rules in application areas.")
        if decision == "KEEP_200" and row["cms_status"] == "draft":
            add(row, "draft_published", "Drafts are excluded from publishing.")
        elif decision == "KEEP_200" and not ctx.live(key) and not _starts(key, APP_SHELL_PREFIXES):
            add(row, "keep_not_live", "Not a live route on the new site.", "warning")
        if decision == "REDIRECT_301":
            raw = row.get("target") or row.get("proposed_target") or ""
            if not raw.startswith("/") or raw.startswith("//"):
                add(row, "redirect_target", "A 301 needs a path on the new site as target.")
            elif target == key:
                add(row, "self_redirect", "Redirects to itself.")
            elif target == "/" and key not in HOME_ALIASES:
                add(row, "homepage_redirect", "No homepage catch-all redirects.")
            elif path_class.get(target) in ("REDIRECT_301", "RETIRE_410", "ALLOW_404"):
                add(row, "redirect_chain", f"{target} is itself {path_class[target]}.")
            elif not ctx.live(target):
                add(row, "target_not_live", f"{target} is not a live new-site route.")
        if decision in ("REDIRECT_301", "RETIRE_410") and not (
            truthy(row.get("approved")) and row.get("approved_by")
        ):
            add(row, "awaiting_approval", "Needs approved=yes and approved_by.", "warning")
        if decision == "RETIRE_410" and not NGINX_SAFE.match(key):
            add(row, "unsafe_path", "Path can't be written as an exact Nginx rule: leave it 404.")
    for key, classes in decided.items():
        if len(classes) > 1 and classes & {"REDIRECT_301", "RETIRE_410"}:
            row = next(r for r in rows if r["path_key"] == key)
            add(
                row,
                "variant_conflict",
                f"Spellings or query variants of {key} disagree ({', '.join(sorted(classes))}): "
                "a rule applies to the path and every query string.",
            )
    return problems


# ---- outputs -----------------------------------------------------------------------------


def approved_rules(rows: list[dict], problems: list[dict]) -> tuple[list[dict], list[str]]:
    """(approved 301 rows in mapping format, approved 410 path keys) without errors."""
    bad = {p["path_key"] for p in problems if p["severity"] == "error"}
    redirects, gone = {}, set()
    # A path is decided by its bare URL; query-only paths by their (agreeing) variants.
    for row in sorted(rows, key=lambda r: bool(r["query"])):
        key = row["path_key"]
        if key in bad or key in redirects or key in gone:
            continue
        if row["effective_class"] == "REDIRECT_301":
            redirects[key] = {
                "legacy_path": key,
                "legacy_url": row["url"],
                "action": "REDIRECT_301",
                "target_path": row["effective_target"],
                "approved": "yes",
                "approved_by": row["approved_by"],
                "reason": row["reason"],
                "note": row.get("notes", ""),
            }
        elif row["effective_class"] == "RETIRE_410":
            gone.add(key)
    return sorted(redirects.values(), key=lambda r: r["legacy_path"]), sorted(gone)


def gone_snippet(paths: list[str]) -> str:
    body = "".join(
        f"location = {p} {{ return 410; }}\nlocation = {p}/ {{ return 410; }}\n" for p in paths
    )
    digest = hashlib.sha256(body.encode()).hexdigest()[:16]
    return (
        "# Generated by `python -m legacy_migration cleanup` from approved RETIRE_410 rows.\n"
        f"# {len(paths)} path(s), exact matches only (query strings share the path's rule).\n"
        f"# sha256:{digest}. Include in the server block, then run `nginx -t`.\n" + body
    )


def verify_snippet(text: str, ctx: Context, approved: list[str]) -> list[str]:
    """Static checks: exact rules only, approved paths only, nothing protected or live."""
    errors = []
    seen = set()
    rules = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    for line in rules:
        m = re.fullmatch(r"location = (\S+) \{ return 410; \}", line)
        if not m:
            errors.append(f"not an exact 410 rule: {line}")
            continue
        path = m.group(1)
        key = path_key(path)
        if path in seen:
            errors.append(f"duplicate rule: {path}")
        seen.add(path)
        if not NGINX_SAFE.match(path):
            errors.append(f"unsafe path: {path}")
        if key not in approved:
            errors.append(f"not approved: {path}")
        if key in ctx.protected or ctx.live(key) or key in HOME_ALIASES:
            errors.append(f"protected or live path: {path}")
        if _app_area(key):
            errors.append(f"application area: {path}")
    if len(rules) != 2 * len(approved):
        errors.append(f"expected {2 * len(approved)} rules, found {len(rules)}")
    return errors


def summary(
    rows: list[dict], problems: list[dict], counts: dict, snippet_errors: list[str]
) -> dict:
    effective = Counter(r["effective_class"] for r in rows)
    proposed = Counter(r["proposed_class"] for r in rows)
    pending = sum(
        1
        for r in rows
        if r["effective_class"] == "REVIEW"
        and r["proposed_class"] in ("REDIRECT_301", "RETIRE_410")
        and r.get("decision") in ("", "REDIRECT_301", "RETIRE_410")
    )
    errors = [p for p in problems if p["severity"] == "error"]
    return {
        "import": counts,
        "urls": len(rows),
        "preserved_200": effective["KEEP_200"],
        "redirected_301": effective["REDIRECT_301"],
        "retired_410": effective["RETIRE_410"],
        "left_404": effective["ALLOW_404"],
        "unresolved": effective["REVIEW"],
        "awaiting_approval": pending,
        "proposed": dict(proposed),
        "families": dict(Counter(r["family"] for r in rows)),
        "protected_urls": sum(1 for r in rows if r["protected"]),
        "errors": len(errors),
        "errors_by_code": dict(Counter(p["code"] for p in errors)),
        "warnings_by_code": dict(Counter(p["code"] for p in problems if p["severity"] != "error")),
        "nginx_snippet": "refused" if snippet_errors else "verified",
        "nginx_snippet_errors": snippet_errors,
        "ready_for_staging": not errors and not snippet_errors and effective["REVIEW"] == 0,
    }


def markdown(s: dict) -> str:
    lines = [
        "# Historical URL cleanup",
        "",
        f"Imported {s['import']['rows']} rows from {len(s['import']['reports'])} report(s): "
        f"{s['import']['distinct_urls']} distinct URLs, {s['import']['distinct_paths']} paths, "
        f"{s['import']['query_variants']} query-string variants.",
        "",
        "| Outcome | URLs |",
        "|---|---:|",
        f"| Preserved (200) | {s['preserved_200']} |",
        f"| Redirected (301, approved) | {s['redirected_301']} |",
        f"| Retired (410, approved) | {s['retired_410']} |",
        f"| Left as genuine 404 | {s['left_404']} |",
        f"| Unresolved (review or awaiting approval) | {s['unresolved']} |",
        "",
        f"Awaiting approval: {s['awaiting_approval']}. Protected URLs: {s['protected_urls']}. "
        f"Validation errors: {s['errors']}. Nginx 410 snippet: {s['nginx_snippet']}. "
        f"Ready for staging: {'yes' if s['ready_for_staging'] else 'no'}.",
        "",
    ]
    for title, data in (
        ("Families", s["families"]),
        ("Proposals", s["proposed"]),
        ("Errors", s["errors_by_code"]),
        ("Warnings", s["warnings_by_code"]),
    ):
        if data:
            lines += [f"## {title}", "", *[f"- {k}: {v}" for k, v in sorted(data.items())], ""]
    if s["nginx_snippet_errors"]:
        lines += [
            "## Nginx snippet refused",
            "",
            *[f"- {e}" for e in s["nginx_snippet_errors"]],
            "",
        ]
    return "\n".join(lines)


def write(out_dir: str | Path, result: dict, ctx: Context, counts: dict) -> dict:
    out = Path(out_dir)
    rows, problems = result["rows"], result["problems"]
    write_csv(out / "cleanup-decisions.csv", DECISION_FIELDS, rows)
    write_csv(
        out / "cleanup-problems.csv", ("severity", "code", "path_key", "url", "message"), problems
    )
    redirects, gone = approved_rules(rows, problems)
    write_csv(
        out / "approved-redirects.csv",
        (
            "legacy_path",
            "legacy_url",
            "action",
            "target_path",
            "approved",
            "approved_by",
            "reason",
            "note",
        ),
        redirects,
    )
    gone_errors = [
        p
        for p in problems
        if p["severity"] == "error"
        and (
            p["code"]
            in (
                "unsafe_path",
                "query_variant_only",
                "variant_conflict",
                "protected_url",
                "essential_route",
                "app_area",
                "published_slug_protected",
            )
        )
    ]
    text = gone_snippet(gone)
    snippet_errors = verify_snippet(text, ctx, gone)
    if gone_errors:
        snippet_errors = [f"{p['code']}: {p['path_key']}" for p in gone_errors] + snippet_errors
    target = out / "tpa-legacy-gone.conf"
    if snippet_errors:
        target.unlink(missing_ok=True)  # never leave an unverified snippet behind
    else:
        target.write_text(text, encoding="utf-8")
    # The same decisions in mapping format, for `compare` and `sitemap-check` on staging.
    mapping_rows = []
    for row in rows:
        if row["query"]:
            continue
        action = {"KEEP_200": "KEEP"}.get(row["effective_class"], row["effective_class"])
        mapping_rows.append(
            {
                "legacy_url": row["url"],
                "legacy_path": row["path_key"],
                "kind": row["family"],
                "action": action,
                "target_path": row["effective_target"],
                "approved": "yes" if action in ("REDIRECT_301", "RETIRE_410") else "",
                "priority": "high" if row["protected"] else "normal",
            }
        )
    write_csv(
        out / "cleanup-mapping.csv",
        ("legacy_url", "legacy_path", "kind", "action", "target_path", "approved", "priority"),
        mapping_rows,
    )
    s = summary(rows, problems, counts, snippet_errors)
    (out / "cleanup-summary.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    (out / "cleanup-summary.md").write_text(markdown(s), encoding="utf-8")
    return s
