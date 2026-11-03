"""Rewrite plan for the legacy CMS's published articles.

Editorial rules (2026-11-03):
- Only **published** records are rewrite candidates. Drafts are listed separately and are
  never rewritten, published, imported or reported as missing. Records with any other or
  blank status are listed for a person to check; they are not assumed published.
- Each published article keeps its **exact established URL**: the canonical URL (from the
  export, or the page itself) or else its public URL. Nothing is derived from a title.
- The new site serves articles at ``/articles/<slug>``. A canonical already of that form
  is preserved as is; any other path keeps its own last segment and gets one 301.
  The proposed path never depends on the old or the new section, so restructuring the
  taxonomy can't change a URL.
- Sections are **not** copied from the legacy taxonomy. ``proposed_section`` comes only
  from an approved editorial taxonomy decision (``--taxonomy``) or an editor's edit.
- Titles, slugs, categories and excerpts are scanned for medical, mental-health,
  legal and financial topics; flagged articles need qualified expert review or exclusion.
- Articles are rewritten from scratch later: this plan never copies legacy body text.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from .core import (
    clean_url,
    last_segment,
    path_key,
    path_of,
    publication_status,
    read_csv,
    same_site,
    truthy,
    write_csv,
)
from .inventory import _article

REWRITE_FIELDS = (
    "legacy_id", "title", "author", "original_published_at", "original_modified_at",
    "legacy_category", "legacy_section", "original_slug", "original_url",
    "original_canonical_url", "canonical_source", "url_status", "url_candidates",
    "proposed_new_path", "canonical_preserved", "url_note", "proposed_section",
    "section_status", "suitability_flags", "editorial_suitability", "suitability_decided_by",
    "rewrite_status", "rewrite_owner", "editor_notes",
)  # fmt: skip
DRAFT_FIELDS = (
    "legacy_id", "title", "original_slug", "status", "publication_status", "legacy_category",
    "legacy_section", "note",
)  # fmt: skip
TAXONOMY_FIELDS = (
    "legacy_category", "legacy_section", "legacy_path", "new_section", "approved", "note",
)  # fmt: skip
REWRITE_STATUSES = (
    "NOT_STARTED", "ASSIGNED", "DRAFTING", "EXPERT_REVIEW", "READY", "PUBLISHED_NEW",
    "EXCLUDED",
)  # fmt: skip
SUITABILITY = ("GENERAL", "EXPERT_REVIEW", "EXCLUDE")
# Fields an editor owns: carried over from --previous when re-running the plan.
EDITOR_FIELDS = (
    "proposed_section", "section_status", "editorial_suitability", "suitability_decided_by",
    "rewrite_status", "rewrite_owner", "editor_notes",
)  # fmt: skip

NEW_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")  # the new CMS's slug rule
NEW_ARTICLE_PATH = re.compile(r"^/articles/([^/]+)$")

# Word stems that mark specialist topics. Hints for editors, not decisions.
SPECIALIST_TERMS = {
    "medical": (
        "diagnos", "disease", "illness", "symptom", "medication", "medicine", "prescription",
        "dosage", "cancer", "diabet", "blood pressure", "cholesterol", "pregnan", "fertility",
        "vaccin", "supplement", "cure", "treatment", "adhd", "autism", "insomnia",
        "chronic pain", "weight loss", "diet", "nutrition", "detox", "hormone", "menopause",
        "covid", "doctor", "surgery",
    ),
    "mental_health": (
        "depress", "anxiety disorder", "panic attack", "ptsd", "trauma", "therapy",
        "therapist", "therapeutic", "counsel", "suicid", "self-harm", "self harm", "bipolar",
        "ocd", "mental illness", "mental health", "psychiatr", "eating disorder", "addiction",
    ),
    "legal": (
        "legal", "lawyer", "attorney", "lawsuit", "contract", "divorce", "custody", "visa",
        "immigration", "tenant", "copyright", "court", "law", "laws",
    ),
    "financial": (
        "investing", "investment", "investor", "stock market", "stocks", "crypto", "bitcoin",
        "trading", "loan", "mortgage", "debt", "credit score", "tax", "taxes", "retirement",
        "pension", "insurance", "forex",
    ),
}  # fmt: skip


def suitability_flags(*texts: str) -> list[str]:
    """``area:term`` for every specialist term found (case-insensitive). Terms of up to
    four letters must be whole words (``law`` is not ``lawn``); longer ones are stems."""
    text = " ".join(t for t in texts if t).lower().replace("-", " ").replace("_", " ")
    flags = []
    for area, terms in SPECIALIST_TERMS.items():
        for term in terms:
            word = re.escape(term.replace("-", " "))
            pattern = rf"\b{word}s?\b" if len(term) <= 4 else rf"\b{word}"
            if re.search(pattern, text):
                flags.append(f"{area}:{term}")
    return flags


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


class Taxonomy:
    """Approved editorial decisions: legacy category/section/path -> new section slug."""

    def __init__(self, rows: list[dict] | None = None):
        self.by_category: dict[str, str] = {}
        self.by_section: dict[str, str] = {}
        self.by_path: dict[str, str] = {}
        for row in rows or []:
            new = _norm(row.get("new_section", ""))
            if not new or not truthy(row.get("approved")):
                continue  # undecided or unapproved: never a proposal
            if row.get("legacy_category"):
                self.by_category[_norm(row["legacy_category"])] = new
            if row.get("legacy_section"):
                self.by_section[_norm(row["legacy_section"])] = new
            if row.get("legacy_path"):
                self.by_path[path_key(row["legacy_path"])] = new

    def section_for(self, category: str, section: str) -> str:
        return self.by_category.get(_norm(category)) or self.by_section.get(_norm(section)) or ""

    def topic_path_for(self, legacy_path: str) -> str:
        key = path_key(legacy_path)
        new = self.by_path.get(key) or self.by_category.get(_norm(last_segment(key)))
        return f"/topics/{new}" if new else ""


def proposed_path(established_url: str) -> tuple[str, str, str]:
    """(proposed new path, canonical_preserved yes/no, note) from an exact URL only."""
    if not established_url:
        return "", "", "No public or canonical URL found: find it before rewriting."
    path = path_key(path_of(established_url))
    match = NEW_ARTICLE_PATH.match(path)
    slug = match.group(1) if match else last_segment(path)
    if not NEW_SLUG.match(slug):
        return "", "no", f"'{slug}' is not a valid slug in the new CMS: needs a decision."
    if match:
        return path, "yes", "Canonical path preserved."
    return (
        f"/articles/{slug}",
        "no",
        f"The new site serves articles only at /articles/<slug>: {path} keeps its slug and "
        "gets one 301.",
    )


def _inventory_index(rows: list[dict]) -> tuple[dict, dict]:
    by_path, by_slug = {}, defaultdict(list)
    for row in rows:
        if row.get("kind") in ("media", "asset", "system", "feed", "sitemap"):
            continue
        key = path_key(row.get("path") or path_of(row.get("url", "")))
        by_path[key] = row
        by_slug[last_segment(key)].append(row)
    return by_path, by_slug


def _usable(row: dict) -> bool:
    return row.get("page_class") in ("ok", "shell_only")


def _urls(record: dict, base_url: str, hosts: list[str], by_path: dict, by_slug: dict) -> dict:
    """Exact public and canonical URL of one published record, with the evidence."""
    out = {"original_url": "", "original_canonical_url": "", "canonical_source": "",
           "url_status": "FIND_URL", "url_candidates": ""}  # fmt: skip
    export_url = clean_url(record.get("url", ""), base_url or None) if record.get("url") else ""
    export_canonical = (
        clean_url(record.get("canonical_url", ""), base_url or None)
        if record.get("canonical_url")
        else ""
    )
    page = None
    if export_url:
        out["original_url"] = export_url
        page = by_path.get(path_key(path_of(export_url)))
        out["url_status"] = "CONFIRMED" if page and _usable(page) else "EXPORT_ONLY"
    elif record.get("slug"):
        # Exact slug only. Spellings of one page (/x, /x/, a redirect to it) count once.
        candidates: dict[str, dict] = {}
        for r in by_slug.get(record["slug"], []):
            if _usable(r):
                final = r.get("final_url") or r.get("url", "")
                candidates.setdefault(path_key(path_of(final)), {**r, "_final": final})
        found = [
            c for c in candidates.values() if last_segment(path_of(c["_final"])) == record["slug"]
        ]
        if len(found) == 1:
            page = found[0]
            out["original_url"] = page["_final"]
            out["url_status"] = "FOUND_BY_SLUG"
        elif found:
            out["url_status"] = "AMBIGUOUS"
            out["url_candidates"] = " ".join(sorted(c["_final"] for c in found))
    if export_canonical:
        out["original_canonical_url"], out["canonical_source"] = export_canonical, "export"
    elif page and page.get("page_class") == "ok" and page.get("canonical"):
        canonical = page["canonical"]
        if not hosts or same_site(canonical, hosts):
            out["original_canonical_url"], out["canonical_source"] = canonical, "page"
    elif page and page.get("page_class") == "shell_only":
        out["canonical_source"] = "unverified_app_shell"
    return out


def build_plan(
    exports: list[dict],
    *,
    inventory_rows: list[dict] | None = None,
    taxonomy: Taxonomy | None = None,
    previous: list[dict] | None = None,
    base_url: str = "",
) -> dict:
    taxonomy = taxonomy or Taxonomy()
    hosts = [urlsplit(base_url).netloc] if base_url else []
    by_path, by_slug = _inventory_index(inventory_rows or [])
    prior = {}
    for row in previous or []:
        for key in (row.get("legacy_id"), row.get("original_slug")):
            if key:
                prior.setdefault(key, row)
    published, drafts, others = [], [], []
    for raw in exports:
        record = _article(raw, "export")
        status = record["publication_status"]
        if status == "draft":
            drafts.append(_side_row(record, "Draft: not rewritten, published or imported."))
            continue
        if status != "published":
            others.append(
                _side_row(record, f"Status '{record['status'] or 'blank'}': check before use.")
            )
            continue
        urls = _urls(record, base_url, hosts, by_path, by_slug)
        established = urls["original_canonical_url"] or urls["original_url"]
        new_path, preserved, note = proposed_path(established)
        if urls["url_status"] == "AMBIGUOUS":
            note = "Several live URLs end with this slug: choose the established one."
        section = taxonomy.section_for(record["category"], record["section"])
        flags = suitability_flags(
            record["title"], record["slug"], record["category"], record["section"],
            record.get("excerpt", ""),
        )  # fmt: skip
        row = {
            "legacy_id": record["id"],
            "title": record["title"],
            "author": record["author"],
            "original_published_at": record["published_at"],
            "original_modified_at": record["modified_at"],
            "legacy_category": record["category"],
            "legacy_section": record["section"],
            "original_slug": record["slug"],
            **urls,
            "proposed_new_path": new_path,
            "canonical_preserved": preserved,
            "url_note": note,
            "proposed_section": section,
            "section_status": "DECIDED" if section else "NEEDS_DECISION",
            "suitability_flags": ";".join(flags),
            "editorial_suitability": "EXPERT_REVIEW" if flags else "GENERAL",
            "suitability_decided_by": "",
            "rewrite_status": "NOT_STARTED",
            "rewrite_owner": "",
            "editor_notes": "",
        }
        old = prior.get(record["id"]) or prior.get(record["slug"])
        if old:
            for field in EDITOR_FIELDS:
                if old.get(field):
                    row[field] = old[field]
            if old.get("proposed_section") and not section:
                row["section_status"] = old.get("section_status") or "EDITOR"
        published.append(row)
    return {
        "rewrite": published,
        "drafts": drafts,
        "other_status": others,
        "summary": summary(published, drafts, others),
    }


def _side_row(record: dict, note: str) -> dict:
    return {
        "legacy_id": record["id"],
        "title": record["title"],
        "original_slug": record["slug"],
        "status": record["status"],
        "publication_status": record["publication_status"],
        "legacy_category": record["category"],
        "legacy_section": record["section"],
        "note": note,
    }


def summary(published: list[dict], drafts: list[dict], others: list[dict]) -> dict:
    return {
        "records": len(published) + len(drafts) + len(others),
        "published": len(published),
        "draft": len(drafts),
        "other_status": len(others),
        "url_status": dict(Counter(r["url_status"] for r in published)),
        "canonical_preserved": dict(Counter(r["canonical_preserved"] or "-" for r in published)),
        "editorial_suitability": dict(Counter(r["editorial_suitability"] for r in published)),
        "section_status": dict(Counter(r["section_status"] for r in published)),
        "rewrite_status": dict(Counter(r["rewrite_status"] for r in published)),
    }


def validate_plan(rows: list[dict]) -> list[dict]:
    """Errors block using the plan; warnings are work still to do."""
    problems = []

    def add(row, code, message, severity="error"):
        problems.append({"legacy_id": row.get("legacy_id", ""), "code": code,
                         "message": message, "severity": severity})  # fmt: skip

    paths: dict[str, str] = {}
    ids: set[str] = set()
    for row in rows:
        status = publication_status(row) if row.get("publication_status") else "published"
        if status != "published":
            add(row, "not_published", "Only published articles belong in the rewrite plan.")
        if row.get("legacy_id"):
            if row["legacy_id"] in ids:
                add(row, "duplicate_id", "Legacy article listed twice.")
            ids.add(row["legacy_id"])
        path = row.get("proposed_new_path", "")
        if path:
            match = NEW_ARTICLE_PATH.match(path)
            if not match or not NEW_SLUG.match(match.group(1)):
                add(row, "invalid_new_path", f"{path} is not /articles/<valid-slug>.")
            elif path in paths:
                add(row, "duplicate_new_path", f"{path} is also proposed for {paths[path]}.")
            paths.setdefault(path, row.get("legacy_id", ""))
            established = row.get("original_canonical_url") or row.get("original_url")
            if established:
                old_slug = last_segment(path_key(path_of(established)))
                if match and match.group(1) != old_slug:
                    add(row, "slug_changed", "The proposed slug differs from the established "
                        "URL's slug: URLs are preserved, never re-derived.")  # fmt: skip
        else:
            add(row, "url_missing", row.get("url_note") or "No URL yet.", "warning")
        if row.get("rewrite_status") and row["rewrite_status"] not in REWRITE_STATUSES:
            add(row, "invalid_rewrite_status", f"Use one of {', '.join(REWRITE_STATUSES)}.")
        if row.get("editorial_suitability") not in SUITABILITY:
            add(row, "invalid_suitability", f"Use one of {', '.join(SUITABILITY)}.")
        elif (
            row.get("suitability_flags")
            and row["editorial_suitability"] == "GENERAL"
            and not (row.get("suitability_decided_by"))
        ):
            add(row, "specialist_topic_unreviewed",
                "Flagged specialist topic marked GENERAL without a named reviewer.")  # fmt: skip
        if row.get("rewrite_status") in ("READY", "PUBLISHED_NEW") and (
            row.get("editorial_suitability") == "EXPERT_REVIEW"
            and not row.get("suitability_decided_by")
        ):
            add(row, "expert_review_pending", "Expert review must be recorded before release.")
        if row.get("section_status") == "NEEDS_DECISION":
            add(row, "section_undecided", "Choose the new section.", "warning")
    return problems


def write(out_dir: str | Path, plan: dict) -> None:
    out = Path(out_dir)
    write_csv(out / "rewrite-worklist.csv", REWRITE_FIELDS, plan["rewrite"])
    write_csv(out / "draft-articles.csv", DRAFT_FIELDS, plan["drafts"])
    write_csv(out / "other-status-articles.csv", DRAFT_FIELDS, plan["other_status"])


def load_taxonomy(path: str | None) -> Taxonomy:
    return Taxonomy(read_csv(path) if path else [])
