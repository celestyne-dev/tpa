"""Reconcile the legacy CMS export, the site inventory and Search Console exports.

Outputs (all CSVs keep every URL ever recorded; nothing is dropped):
- ``master-url-inventory.csv``: every discovered URL with its evidence and one editorial
  decision: REWRITE, EXPERT_REVIEW, PRESERVE_PAGE, REDIRECT_301, RETIRE_410,
  EXCLUDE_DRAFT or REVIEW.
- ``rewrite-register.csv``: published articles (the rewrite plan) with their decision.
  Only REWRITE / EXPERT_REVIEW articles are *selected* for the new site.
- ``draft-exclusion-register.csv``: drafts, excluded by rule.
- ``taxonomy-register.csv``: legacy categories and sections with their editorial
  replacement or retirement decision (never recreated automatically).
- ``canonical-preservation-report.csv``: what happens to each published article's
  established canonical URL.
- ``readiness-report.md`` / ``.json``: unresolved decisions. Production migration is
  blocked while any blocking item remains (``reconcile --gate`` exits 1).

The tool only *suggests* (``suggested_decision``). It never selects an article, retires
a URL, recreates a category or treats "not indexed" as a reason to drop a page.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from .core import (
    HOME_ALIASES,
    as_int,
    classify_path,
    clean_url,
    last_segment,
    path_key,
    path_of,
    publication_status,
    same_site,
    truthy,
    write_csv,
)
from .gsc import EVIDENCE_FIELDS
from .inventory import _article
from .rewrite import REWRITE_FIELDS, Taxonomy, _norm, build_plan, validate_plan

DECISIONS = (
    "REWRITE", "EXPERT_REVIEW", "PRESERVE_PAGE", "REDIRECT_301", "RETIRE_410",
    "EXCLUDE_DRAFT", "REVIEW",
)  # fmt: skip
SELECTED = ("REWRITE", "EXPERT_REVIEW")
READY_CONTENT = ("READY", "PUBLISHED_NEW")

MASTER_FIELDS = (
    "url_key", "url", "variants", "url_type", "sources", "still_present", "first_recorded",
    "last_seen", "cms_id", "cms_status", "cms_link", "title", "live_status", "live_class",
    "live_canonical", "redirects_to", *[f for f in EVIDENCE_FIELDS if f != "gsc_sources"],
    "suitability_flags", "suggested_decision", "suggested_destination", "suggestion_reason",
    "editorial_decision", "decision_source", "destination", "approved", "decided_by",
    "decision_notes", "readiness",
)  # fmt: skip
MASTER_EDITOR_FIELDS = (
    "editorial_decision",
    "destination",
    "approved",
    "decided_by",
    "decision_notes",
)
REGISTER_EXTRA = (
    "selected", "editorial_decision", "destination", "approved", "decided_by",
    "decision_notes", "canonical_verification", "canonical_confirmed_by", "gsc_index_status",
    "gsc_last_crawled", "gsc_clicks", "gsc_impressions", "gsc_backlinks",
    "suggested_decision", "suggestion_reason", "blocking_issues",
)  # fmt: skip
REGISTER_FIELDS = (*REWRITE_FIELDS, *REGISTER_EXTRA)
REGISTER_EDITOR_FIELDS = (
    "editorial_decision", "destination", "approved", "decided_by", "decision_notes",
    "canonical_confirmed_by",
)  # fmt: skip
DRAFT_REGISTER_FIELDS = (
    "legacy_id", "title", "original_slug", "status", "legacy_category", "legacy_section",
    "known_urls", "gsc_clicks", "gsc_impressions", "editorial_decision", "note",
)  # fmt: skip
TAXONOMY_REGISTER_FIELDS = (
    "legacy_type", "legacy_slug", "legacy_name", "published_articles", "draft_articles",
    "legacy_urls", "gsc_clicks", "gsc_impressions", "register_decision", "new_section",
    "approved", "note", "url_decisions",
)  # fmt: skip
CANONICAL_FIELDS = (
    "legacy_id", "title", "selected", "editorial_decision", "original_url",
    "established_canonical", "canonical_source", "canonical_verification",
    "canonical_confirmed_by", "gsc_index_status", "proposed_new_path", "canonical_preserved",
    "redirect_from", "outcome",
)  # fmt: skip


class Keys:
    """URL keys: the path for the legacy site (www/apex, http/https, slash merged)."""

    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.hosts = [urlsplit(base_url).netloc] if base_url else []

    def url(self, value: str) -> str:
        return clean_url(value, self.base or None) or ""

    def key(self, value: str) -> str:
        url = self.url(value) if "://" in value or self.base else value
        if not url:
            return path_key(value)
        if not self.hosts or same_site(url, self.hosts):
            return path_key(path_of(url))
        parts = urlsplit(url)
        return f"{parts.hostname}{path_key(parts.path or '/')}"


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _issue(scope, key, code, message, blocking=True):
    return {
        "scope": scope,
        "key": key,
        "code": code,
        "message": message,
        "severity": "blocking" if blocking else "warning",
    }


def reconcile(
    exports: list[dict],
    *,
    inventory_rows: list[dict] | None = None,
    gsc: dict[str, dict] | None = None,
    taxonomy: Taxonomy | None = None,
    previous_master: list[dict] | None = None,
    previous_register: list[dict] | None = None,
    new_site_paths: set[str] | None = None,
    base_url: str = "",
    today: str | None = None,
) -> dict:
    today = today or _today()
    keys = Keys(base_url)
    taxonomy = taxonomy or Taxonomy()
    inventory_rows = inventory_rows or []
    gsc = gsc or {}
    plan = build_plan(
        exports,
        inventory_rows=inventory_rows,
        taxonomy=taxonomy,
        previous=previous_register,
        base_url=base_url,
    )
    records = [_article(r, "export") for r in exports]
    for rec in records:
        rec["publication_status"] = publication_status(rec)

    # ---- every URL from every source -----------------------------------------------
    master: dict[str, dict] = {}

    def touch(url: str, source: str) -> dict | None:
        url = keys.url(url) if url else ""
        if not url:
            return None
        key = keys.key(url)
        row = master.setdefault(
            key,
            {f: "" for f in MASTER_FIELDS}
            | {
                "url_key": key,
                "url": url,
                "_variants": set(),
                "_sources": set(),
            },
        )
        row["_variants"].add(url)
        row["_sources"].add(source)
        return row

    for rec in records:
        for field in ("url", "canonical_url"):
            if rec.get(field):
                touch(rec[field], "cms")
    for p in plan["rewrite"]:
        for field in ("original_url", "original_canonical_url"):
            if p.get(field):
                touch(p[field], "cms")
    inv_by_key: dict[str, dict] = {}
    for inv in inventory_rows:
        row = touch(inv.get("url", ""), "inventory")
        if row is not None:
            inv_by_key.setdefault(row["url_key"], inv)
    gsc_by_key: dict[str, dict] = {}
    for url, evidence in gsc.items():
        row = touch(url, "gsc")
        if row is not None:
            merged = gsc_by_key.setdefault(row["url_key"], {})
            for k, v in evidence.items():
                if k in ("gsc_clicks", "gsc_impressions", "gsc_backlinks"):
                    merged[k] = str(as_int(merged.get(k)) + as_int(v))
                elif v and (not merged.get(k) or k == "gsc_index_status"):
                    merged[k] = v
    previous = {r.get("url_key"): r for r in previous_master or [] if r.get("url_key")}
    for key, old in previous.items():
        if key not in master:  # historical record: kept even when no longer discovered
            row = master[key] = {f: old.get(f, "") for f in MASTER_FIELDS}
            row["_variants"] = set(filter(None, old.get("variants", "").split(" ")))
            row["_sources"] = set(filter(None, old.get("sources", "").split(";")))
            row["still_present"] = "no"
            row["_historical"] = True

    # ---- link URLs to CMS records (exact URL, exact slug or /article/<id>) ----------
    by_slug = {r["slug"]: r for r in records if r["slug"]}
    by_id = {r["id"]: r for r in records if r["id"]}
    by_url: dict[str, tuple[dict, str]] = {}  # key -> (record, how the URL was established)
    for rec in records:
        for field in ("url", "canonical_url"):
            if rec.get(field):
                by_url[keys.key(rec[field])] = (rec, "export")
    for p in plan["rewrite"]:
        for field in ("original_url", "original_canonical_url"):
            if p.get(field) and p["legacy_id"] in by_id:
                how = "page_canonical" if field == "original_canonical_url" else "found_by_slug"
                by_url.setdefault(keys.key(p[field]), (by_id[p["legacy_id"]], how))
    taxonomy_slugs = {("category", _norm(r["category"])) for r in records if r["category"]} | {
        ("section", _norm(r["section"])) for r in records if r["section"]
    }

    for key, row in master.items():
        if row.get("_historical"):
            continue
        rec, link = by_url.get(key, (None, ""))
        segment = last_segment(key)
        kind = classify_path(key)
        if rec is None and kind in ("article", "page") and segment in by_slug:
            rec, link = by_slug[segment], "slug"
        if rec is None and kind == "article" and segment.isdigit() and segment in by_id:
            rec, link = by_id[segment], "id"
        inv = inv_by_key.get(key, {})
        if rec is not None:
            url_type = "article"
        elif (
            kind in ("page", "category")
            and key.count("/") == 1
            and (("category", _norm(segment)) in taxonomy_slugs)
        ):
            url_type = "category"
        elif (
            kind in ("page", "category")
            and key.count("/") == 1
            and (("section", _norm(segment)) in taxonomy_slugs)
        ):
            url_type = "section"
        else:
            url_type = inv.get("kind") or kind
        ev = gsc_by_key.get(key, {})
        row.update(
            variants=" ".join(sorted(row["_variants"])),
            url_type=url_type,
            sources=";".join(sorted(row["_sources"])),
            still_present="yes",
            first_recorded=previous.get(key, {}).get("first_recorded") or today,
            last_seen=today,
            cms_id=rec["id"] if rec else "",
            cms_status=rec["publication_status"] if rec else "",
            cms_link=link,
            title=(rec or {}).get("title") or inv.get("title", ""),
            live_status=inv.get("final_status", ""),
            live_class=inv.get("page_class", ""),
            live_canonical=inv.get("canonical", ""),
            redirects_to=inv.get("final_url", ""),
            **{f: ev.get(f, "") for f in EVIDENCE_FIELDS if f != "gsc_sources"},
        )

    # ---- published articles: decisions live in the rewrite register ----------------
    prev_register = {r.get("legacy_id"): r for r in previous_register or [] if r.get("legacy_id")}
    register = []
    article_canonical_key: dict[str, str] = {}
    for p in plan["rewrite"]:
        row = {f: p.get(f, "") for f in REWRITE_FIELDS}
        old = prev_register.get(p["legacy_id"], {})
        for field in REGISTER_EDITOR_FIELDS:
            row[field] = old.get(field, "")
        established = p["original_canonical_url"] or p["original_url"]
        ckey = keys.key(established) if established else ""
        article_canonical_key[p["legacy_id"]] = ckey
        ev = gsc_by_key.get(ckey, {})
        row.update(
            gsc_index_status=ev.get("gsc_index_status", ""),
            gsc_last_crawled=ev.get("gsc_last_crawled", ""),
            gsc_clicks=ev.get("gsc_clicks", ""),
            gsc_impressions=ev.get("gsc_impressions", ""),
            gsc_backlinks=ev.get("gsc_backlinks", ""),
            canonical_verification=_verify_canonical(p, ckey, keys, inv_by_key, ev),
        )
        decision, reason = _suggest_article(row)
        row["suggested_decision"], row["suggestion_reason"] = decision, reason
        row["editorial_decision"] = (row["editorial_decision"] or "").upper()
        row["selected"] = "yes" if row["editorial_decision"] in SELECTED else ""
        register.append(row)
    register_by_id = {r["legacy_id"]: r for r in register}

    # ---- suggestions and decisions for every URL ------------------------------------
    for key, row in master.items():
        if row.get("_historical"):
            continue
        old = previous.get(key, {})
        rec_status = row["cms_status"]
        article = register_by_id.get(row["cms_id"]) if rec_status == "published" else None
        is_canonical_row = article is not None and article_canonical_key.get(row["cms_id"]) == key
        decision, destination, reason = _suggest_url(
            row, article, is_canonical_row, taxonomy, new_site_paths, keys
        )
        row["suggested_decision"], row["suggested_destination"] = decision, destination
        row["suggestion_reason"] = reason
        row["suitability_flags"] = article.get("suitability_flags", "") if article else ""
        if is_canonical_row:
            # The article's decision is made once, in the register.
            row["editorial_decision"] = article["editorial_decision"]
            row["destination"] = article.get("destination", "")
            row["approved"], row["decided_by"] = (
                article.get("approved", ""),
                article.get("decided_by", ""),
            )
            row["decision_notes"] = article.get("decision_notes", "")
            row["decision_source"] = "rewrite-register"
        elif rec_status == "draft" and not old.get("editorial_decision"):
            row["editorial_decision"], row["decision_source"] = "EXCLUDE_DRAFT", "rule"
            row["decided_by"] = "rule: drafts are never rewritten or imported"
        else:
            for field in MASTER_EDITOR_FIELDS:
                row[field] = old.get(field, "")
            row["editorial_decision"] = row["editorial_decision"].upper()
            row["decision_source"] = "editor" if row["editorial_decision"] else ""
    for row in master.values():
        if row.get("_historical"):
            row["decision_source"] = row.get("decision_source") or "editor"

    readiness = _readiness(master, register, new_site_paths, keys)
    for row in master.values():
        row["readiness"] = ";".join(
            i["code"] for i in readiness["by_key"].get(("url", row["url_key"]), [])
        )
    for row in register:
        row["blocking_issues"] = ";".join(
            i["code"]
            for i in readiness["by_key"].get(("article", row["legacy_id"]), [])
            if i["severity"] == "blocking"
        )

    drafts = _draft_register(plan["drafts"], master, records)
    taxonomy_register = _taxonomy_register(records, master, taxonomy)
    canonical = _canonical_report(register, master, keys)
    rows = sorted(
        ({k: v for k, v in r.items() if not k.startswith("_")} for r in master.values()),
        key=lambda r: r["url_key"],
    )
    return {
        "master": rows,
        "register": register,
        "drafts": drafts,
        "other_status": plan["other_status"],
        "taxonomy": taxonomy_register,
        "canonical": canonical,
        "readiness": readiness["report"],
    }


def _verify_canonical(p: dict, ckey: str, keys: Keys, inv_by_key: dict, ev: dict) -> str:
    """VERIFIED, UNVERIFIED, CONFLICT, AMBIGUOUS or MISSING (evidence only)."""
    if p["url_status"] == "AMBIGUOUS":
        return "AMBIGUOUS"
    if not ckey:
        return "MISSING"
    if ev.get("gsc_index_status") == "GOOGLE_CHOSE_DIFFERENT_CANONICAL":
        return "CONFLICT"
    google = ev.get("gsc_google_canonical")
    if google and keys.key(google) != ckey:
        return "CONFLICT"
    page = inv_by_key.get(keys.key(p["original_url"])) if p.get("original_url") else None
    if (
        page
        and page.get("page_class") == "ok"
        and page.get("canonical")
        and p.get("canonical_source") == "export"
        and keys.key(page["canonical"]) != ckey
    ):
        return "CONFLICT"
    target = inv_by_key.get(ckey)
    if (
        target
        and target.get("page_class") == "ok"
        and not as_int(target.get("redirect_hops"))
        and target.get("canonical")
        and keys.key(target["canonical"]) == ckey
    ):
        return "VERIFIED"
    if google and keys.key(google) == ckey:
        return "VERIFIED"
    return "UNVERIFIED"


def _has_search_value(row: dict) -> bool:
    return (
        as_int(row.get("gsc_clicks")) > 0
        or as_int(row.get("gsc_impressions")) > 0
        or as_int(row.get("gsc_backlinks")) > 0
        or row.get("gsc_index_status") == "INDEXED"
    )


def _suggest_article(row: dict) -> tuple[str, str]:
    flagged = bool(row.get("suitability_flags"))
    status = row.get("gsc_index_status") or "no index data"
    if _has_search_value(row):
        why = (
            f"Search evidence: {as_int(row.get('gsc_clicks'))} clicks, "
            f"{as_int(row.get('gsc_impressions'))} impressions, "
            f"{as_int(row.get('gsc_backlinks'))} backlinks, index status {status}."
        )
        if flagged:
            return "EXPERT_REVIEW", why + " Specialist topic: needs a qualified reviewer."
        return "REWRITE", why
    return "REVIEW", (
        f"No clicks, impressions or backlinks (index status: {status}). Not being indexed is "
        "not a reason to retire it: decide whether it belongs on the new site."
    )


def _suggest_url(row, article, is_canonical_row, taxonomy, new_site, keys) -> tuple[str, str, str]:
    key, url_type = row["url_key"], row["url_type"]
    if row["cms_status"] == "draft":
        return "EXCLUDE_DRAFT", "", "Draft in the legacy CMS: never rewritten or imported."
    if article is not None:
        if is_canonical_row:
            return article["suggested_decision"], "", article["suggestion_reason"]
        if article.get("selected") and article.get("proposed_new_path"):
            return (
                "REDIRECT_301",
                article["proposed_new_path"],
                ("Another URL of a selected article: redirect to its new path."),
            )
        return "REVIEW", "", "Another URL of a published article: decide with the article."
    if url_type == "home" or key in HOME_ALIASES:
        return "PRESERVE_PAGE", "", "Homepage."
    if url_type in ("category", "section"):
        decision = taxonomy.decision_for(url_type, last_segment(key))
        if decision.get("decision") == "REPLACE":
            target = f"/topics/{decision['new_section']}"
            return (
                "REDIRECT_301",
                target,
                (f"Approved taxonomy decision: replaced by {target} (approve the redirect)."),
            )
        if decision.get("decision") == "RETIRE":
            return (
                "REVIEW",
                "",
                ("Taxonomy retired. Choose a relevant 301 destination or a justified 410."),
            )
        return "REVIEW", "", "Legacy taxonomy is not recreated: decide in taxonomy-register.csv."
    if url_type in ("system", "asset", "sitemap", "search", "feed"):
        return "REVIEW", "", f"{url_type} URL: not public content, record only."
    if url_type == "article":
        return "REVIEW", "", "Looks like an article but isn't a published CMS record."
    if new_site is not None and key in new_site:
        return "PRESERVE_PAGE", "", "The same path exists on the new site."
    gone = row.get("live_class") == "gone" or row.get("gsc_index_status") == "NOT_FOUND_404"
    if gone:
        return "REVIEW", "", "Reported gone: confirm before any 410 (never automatic)."
    return "REVIEW", "", "No matching page on the new site."


def _decision_problems(
    row,
    *,
    scope,
    ident,
    url_type,
    cms_status,
    new_path,
    selected,
    new_site,
    redirect_sources,
    retired,
    keys,
) -> list[dict]:
    out = []
    decision = (row.get("editorial_decision") or "").upper()
    if decision and decision not in DECISIONS:
        out.append(_issue(scope, ident, "invalid_decision", f"Use one of {', '.join(DECISIONS)}."))
        return out
    if decision == "EXCLUDE_DRAFT" and cms_status != "draft":
        out.append(
            _issue(scope, ident, "exclude_draft_not_draft", "Only drafts are EXCLUDE_DRAFT.")
        )
    if cms_status == "draft" and decision in ("REWRITE", "EXPERT_REVIEW", "PRESERVE_PAGE"):
        out.append(
            _issue(scope, ident, "draft_selected", "Drafts are never rewritten or imported.")
        )
    if decision in SELECTED and cms_status != "published":
        out.append(
            _issue(
                scope,
                ident,
                "rewrite_without_published_record",
                "Only published CMS articles can be rewritten.",
            )
        )
    if decision == "PRESERVE_PAGE":
        if url_type == "article":
            out.append(
                _issue(
                    scope,
                    ident,
                    "article_not_preserved",
                    "Articles are rewritten, not preserved as they are.",
                )
            )
        elif new_site is None:
            out.append(
                _issue(
                    scope,
                    ident,
                    "preserved_page_unverified",
                    "Pass --new-site to verify the page exists.",
                    blocking=False,
                )
            )
        elif row.get("url_key", ident) not in new_site:
            out.append(_issue(scope, ident, "preserved_page_missing", "Not live on the new site."))
    if decision == "REDIRECT_301":
        dest = (row.get("destination") or "").strip()
        dkey = keys.key(dest) if dest else ""
        source_key = row.get("url_key") or ident
        if not dest:
            out.append(
                _issue(
                    scope,
                    ident,
                    "redirect_without_destination",
                    "A 301 needs an approved, relevant destination.",
                )
            )
        elif not dest.startswith("/") or dest.startswith("//"):
            out.append(_issue(scope, ident, "external_destination", "Use a path on the new site."))
        else:
            if dkey == "/" and source_key not in HOME_ALIASES:
                out.append(
                    _issue(
                        scope,
                        ident,
                        "homepage_destination",
                        "No homepage redirects: choose a relevant page.",
                    )
                )
            if dkey == source_key:
                out.append(_issue(scope, ident, "self_redirect", "Redirects to itself."))
            if dkey in redirect_sources:
                out.append(_issue(scope, ident, "redirect_chain", f"{dkey} redirects again."))
            if dkey in retired:
                out.append(_issue(scope, ident, "redirect_to_retired", f"{dkey} is retired."))
            if new_path and selected and dkey != path_key(new_path):
                out.append(
                    _issue(
                        scope,
                        ident,
                        "destination_not_article_path",
                        f"Selected article lives at {new_path}.",
                    )
                )
            if new_site is not None and dkey not in new_site and dkey != path_key(new_path or ""):
                out.append(
                    _issue(scope, ident, "destination_not_live", f"{dkey} is not on the new site.")
                )
        if not truthy(row.get("approved")) or not row.get("decided_by"):
            out.append(
                _issue(
                    scope,
                    ident,
                    "redirect_not_approved",
                    "A 301 needs approved=yes and decided_by.",
                )
            )
    if decision == "RETIRE_410":
        if not truthy(row.get("approved")) or not row.get("decided_by"):
            out.append(
                _issue(
                    scope, ident, "retire_not_approved", "A 410 needs approved=yes and decided_by."
                )
            )
        if not (row.get("decision_notes") or "").strip():
            out.append(
                _issue(
                    scope,
                    ident,
                    "retire_without_justification",
                    "Explain why (not being indexed alone is not a reason).",
                )
            )
    return out


def _readiness(master: dict, register: list[dict], new_site, keys: Keys) -> dict:
    issues: list[dict] = []
    redirect_sources = {
        k for k, r in master.items() if r.get("editorial_decision") == "REDIRECT_301"
    }
    retired = {k for k, r in master.items() if r.get("editorial_decision") == "RETIRE_410"}
    for r in register:
        if r.get("editorial_decision") == "REDIRECT_301" and r.get("original_url"):
            redirect_sources.add(keys.key(r.get("original_canonical_url") or r["original_url"]))
    selected_ids = {r["legacy_id"] for r in register if r.get("selected")}
    new_paths = {r["legacy_id"]: r.get("proposed_new_path", "") for r in register}

    # Published articles: every one needs a decision; selected ones a settled canonical
    # and finished content.
    plan_problems = {
        (p["legacy_id"], p["code"]): p for p in validate_plan(register) if p["severity"] == "error"
    }
    for r in register:
        ident, decision = r["legacy_id"], r.get("editorial_decision", "")
        if not decision or decision == "REVIEW":
            issues.append(
                _issue(
                    "article",
                    ident,
                    "article_undecided",
                    f"'{r['title']}' needs a decision: {r['suggestion_reason']}",
                )
            )
        established_key = keys.key(r.get("original_canonical_url") or r.get("original_url") or "")
        issues += _decision_problems(
            {**r, "url_key": established_key},
            scope="article",
            ident=ident,
            url_type="article",
            cms_status="published",
            new_path=r.get("proposed_new_path"),
            selected=False,
            new_site=new_site,
            redirect_sources=redirect_sources - {established_key},
            retired=retired,
            keys=keys,
        )
        if decision not in SELECTED:
            continue
        verification = r.get("canonical_verification")
        confirmed = bool(r.get("canonical_confirmed_by"))
        if verification in ("MISSING", "AMBIGUOUS"):
            issues.append(
                _issue(
                    "article",
                    ident,
                    "canonical_unresolved",
                    r.get("url_note") or "No established URL.",
                )
            )
        elif verification == "CONFLICT" and not confirmed:
            issues.append(
                _issue(
                    "article",
                    ident,
                    "canonical_conflict",
                    "Canonical evidence disagrees: confirm in URL Inspection.",
                )
            )
        elif verification == "UNVERIFIED" and not confirmed:
            issues.append(
                _issue(
                    "article",
                    ident,
                    "canonical_unverified",
                    "Verify the canonical (URL Inspection) and set canonical_confirmed_by.",
                )
            )
        if not r.get("proposed_new_path") and verification not in ("MISSING", "AMBIGUOUS"):
            issues.append(_issue("article", ident, "new_path_missing", r.get("url_note", "")))
        if (decision == "EXPERT_REVIEW" or r.get("suitability_flags")) and not r.get(
            "suitability_decided_by"
        ):
            issues.append(
                _issue(
                    "article",
                    ident,
                    "expert_review_pending",
                    "Record the qualified reviewer in suitability_decided_by.",
                )
            )
        if r.get("editorial_suitability") == "EXCLUDE":
            issues.append(
                _issue(
                    "article",
                    ident,
                    "suitability_excluded",
                    "Marked EXCLUDE but selected for rewriting.",
                )
            )
        if r.get("rewrite_status") not in READY_CONTENT:
            issues.append(
                _issue(
                    "article",
                    ident,
                    "content_not_ready",
                    f"Rewrite status is {r.get('rewrite_status') or 'blank'}.",
                )
            )
        for (pid, code), p in plan_problems.items():
            if pid == ident and code not in (
                "specialist_topic_unreviewed",
                "expert_review_pending",
            ):
                issues.append(_issue("article", ident, code, p["message"]))

    # Every URL: valid decisions; undecided URLs of selected articles block.
    for key, row in master.items():
        if row.get("decision_source") == "rewrite-register":
            continue  # checked once, above
        selected = row.get("cms_id") in selected_ids and row.get("cms_status") == "published"
        decision = row.get("editorial_decision", "")
        if not decision or decision == "REVIEW":
            issues.append(
                _issue(
                    "url",
                    key,
                    "url_undecided",
                    row.get("suggestion_reason") or "Needs a decision.",
                    blocking=selected,
                )
            )
        issues += _decision_problems(
            row,
            scope="url",
            ident=key,
            url_type=row.get("url_type"),
            cms_status=row.get("cms_status"),
            new_path=new_paths.get(row.get("cms_id"), ""),
            selected=selected,
            new_site=new_site,
            redirect_sources=redirect_sources - {key},
            retired=retired,
            keys=keys,
        )

    by_key = defaultdict(list)
    for i in issues:
        by_key[(i["scope"], i["key"])].append(i)
    blocking = [i for i in issues if i["severity"] == "blocking"]
    report = {
        "production_ready": not blocking,
        "blocking": len(blocking),
        "warnings": len(issues) - len(blocking),
        "blocking_by_code": dict(Counter(i["code"] for i in blocking)),
        "warnings_by_code": dict(Counter(i["code"] for i in issues if i["severity"] != "blocking")),
        "master_decisions": dict(
            Counter(r.get("editorial_decision") or "-" for r in master.values())
        ),
        "master_url_types": dict(Counter(r.get("url_type") or "-" for r in master.values())),
        "published_articles": len(register),
        "selected_articles": len(selected_ids),
        "article_decisions": dict(Counter(r.get("editorial_decision") or "-" for r in register)),
        "issues": issues,
    }
    return {"report": report, "by_key": by_key}


def _draft_register(drafts: list[dict], master: dict, records: list[dict]) -> list[dict]:
    urls = defaultdict(list)
    for row in master.values():
        if row.get("cms_status") == "draft" and row.get("cms_id"):
            urls[row["cms_id"]].append(row)
    out = []
    for d in drafts:
        linked = urls.get(d["legacy_id"], [])
        clicks = sum(as_int(r.get("gsc_clicks")) for r in linked)
        impressions = sum(as_int(r.get("gsc_impressions")) for r in linked)
        note = "Excluded: drafts are never rewritten, published or imported."
        if clicks or impressions:
            note += " Its URL has search history: give the URL a 301 or 410 decision."
        out.append(
            {
                **{
                    k: d.get(k, "")
                    for k in (
                        "legacy_id",
                        "title",
                        "original_slug",
                        "status",
                        "legacy_category",
                        "legacy_section",
                    )
                },
                "known_urls": " ".join(r["url"] for r in linked),
                "gsc_clicks": clicks or "",
                "gsc_impressions": impressions or "",
                "editorial_decision": "EXCLUDE_DRAFT",
                "note": note,
            }
        )
    return out


def _taxonomy_register(records: list[dict], master: dict, taxonomy: Taxonomy) -> list[dict]:
    terms: dict[tuple[str, str], dict] = {}
    for rec in records:
        for kind in ("category", "section"):
            name = rec.get(kind)
            if not name:
                continue
            entry = terms.setdefault(
                (kind, _norm(name)), {"name": name, "published": 0, "draft": 0}
            )
            if rec["publication_status"] == "published":
                entry["published"] += 1
            elif rec["publication_status"] == "draft":
                entry["draft"] += 1
    for row in master.values():
        if row.get("url_type") in ("category", "section"):
            terms.setdefault(
                (row["url_type"], _norm(last_segment(row["url_key"]))),
                {"name": last_segment(row["url_key"]), "published": 0, "draft": 0},
            )
    out = []
    for (kind, slug), entry in sorted(terms.items()):
        urls = [
            r
            for r in master.values()
            if r.get("url_type") == kind and _norm(last_segment(r["url_key"])) == slug
        ]
        decision = taxonomy.decision_for(kind, slug)
        out.append(
            {
                "legacy_type": kind,
                "legacy_slug": slug,
                "legacy_name": entry["name"],
                "published_articles": entry["published"],
                "draft_articles": entry["draft"],
                "legacy_urls": " ".join(sorted(r["url"] for r in urls)),
                "gsc_clicks": sum(as_int(r.get("gsc_clicks")) for r in urls) or "",
                "gsc_impressions": sum(as_int(r.get("gsc_impressions")) for r in urls) or "",
                "register_decision": decision.get("decision") or "REVIEW",
                "new_section": decision.get("new_section", ""),
                "approved": "yes" if decision else "",
                "note": decision.get("note")
                or (
                    "Not recreated automatically: decide REPLACE "
                    "(new_section) or RETIRE in taxonomy-decisions.csv."
                ),
                "url_decisions": ";".join(
                    f"{r['url_key']}={r.get('editorial_decision') or '-'}" for r in urls
                ),
            }
        )
    return out


def _canonical_report(register: list[dict], master: dict, keys: Keys) -> list[dict]:
    others = defaultdict(list)
    for row in master.values():
        if row.get("cms_id") and row.get("decision_source") != "rewrite-register":
            others[row["cms_id"]].append(row["url_key"])
    out = []
    for r in register:
        established = r.get("original_canonical_url") or r.get("original_url")
        old_key = keys.key(established) if established else ""
        new_path = r.get("proposed_new_path", "")
        redirect_from = sorted(set(others.get(r["legacy_id"], [])))
        if old_key and new_path and old_key != path_key(new_path):
            redirect_from = [old_key, *[k for k in redirect_from if k != old_key]]
        if not r.get("selected"):
            outcome = "NOT_SELECTED"
        elif r.get("blocking_issues"):
            outcome = "UNRESOLVED"
        elif r.get("canonical_preserved") == "yes":
            outcome = "PRESERVED"
        else:
            outcome = "REDIRECTED"
        out.append(
            {
                "legacy_id": r["legacy_id"],
                "title": r["title"],
                "selected": r.get("selected", ""),
                "editorial_decision": r.get("editorial_decision", ""),
                "original_url": r.get("original_url", ""),
                "established_canonical": established or "",
                "canonical_source": r.get("canonical_source", ""),
                "canonical_verification": r.get("canonical_verification", ""),
                "canonical_confirmed_by": r.get("canonical_confirmed_by", ""),
                "gsc_index_status": r.get("gsc_index_status", ""),
                "proposed_new_path": new_path,
                "canonical_preserved": r.get("canonical_preserved", ""),
                "redirect_from": " ".join(redirect_from),
                "outcome": outcome,
            }
        )
    return out


def markdown(report: dict) -> str:
    state = "READY" if report["production_ready"] else "BLOCKED"
    lines = [
        "# Migration readiness",
        "",
        f"**Production migration: {state}**: {report['blocking']} blocking item(s), "
        f"{report['warnings']} warning(s).",
        "",
        f"Published articles: {report['published_articles']}, selected for rewriting: "
        f"{report['selected_articles']}.",
        "",
    ]
    for title, data in (
        ("Blocking items by type", report["blocking_by_code"]),
        ("Warnings by type", report["warnings_by_code"]),
        ("Article decisions", report["article_decisions"]),
        ("URL decisions (master inventory)", report["master_decisions"]),
        ("URL types", report["master_url_types"]),
    ):
        if data:
            lines += [f"## {title}", "", *[f"- {k}: {v}" for k, v in sorted(data.items())], ""]
    blocking = [i for i in report["issues"] if i["severity"] == "blocking"]
    if blocking:
        lines += [
            "## Unresolved blocking decisions",
            "",
            "| Scope | Key | Issue | Detail |",
            "|---|---|---|---|",
        ]
        for i in blocking:
            detail = i["message"].replace("|", "/")
            lines.append(f"| {i['scope']} | {i['key']} | {i['code']} | {detail} |")
        lines.append("")
    return "\n".join(lines)


def write(out_dir: str | Path, result: dict) -> None:
    from .rewrite import DRAFT_FIELDS

    out = Path(out_dir)
    write_csv(out / "master-url-inventory.csv", MASTER_FIELDS, result["master"])
    write_csv(out / "rewrite-register.csv", REGISTER_FIELDS, result["register"])
    write_csv(out / "draft-exclusion-register.csv", DRAFT_REGISTER_FIELDS, result["drafts"])
    write_csv(out / "other-status-articles.csv", DRAFT_FIELDS, result["other_status"])
    write_csv(out / "taxonomy-register.csv", TAXONOMY_REGISTER_FIELDS, result["taxonomy"])
    write_csv(out / "canonical-preservation-report.csv", CANONICAL_FIELDS, result["canonical"])
    write_csv(
        out / "readiness-issues.csv",
        ("severity", "scope", "key", "code", "message"),
        result["readiness"]["issues"],
    )
    summary = {k: v for k, v in result["readiness"].items() if k != "issues"}
    (out / "readiness-report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "readiness-report.md").write_text(markdown(result["readiness"]), encoding="utf-8")
