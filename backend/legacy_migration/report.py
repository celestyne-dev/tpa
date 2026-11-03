"""Migration report: totals for preserved, redirected, retired and unresolved URLs."""

from __future__ import annotations

from collections import Counter

from .core import truthy

ISSUE_LABELS = {
    "broken_links": "Pages with broken internal links",
    "linked_but_broken": "Broken URLs that are still linked internally",
    "redirect_chain": "Redirect chains (more than one hop)",
    "redirect_loop": "Redirect loops",
    "temporary_redirect": "Temporary (302/307) redirects",
    "missing_canonical": "Pages without a canonical URL",
    "canonical_elsewhere": "Pages canonicalised to another URL",
    "canonical_not_ok": "Canonicals pointing at a redirect or error",
    "noindex": "noindex pages",
    "accidental_noindex": "Likely accidental noindex",
    "sitemap_lists_non_indexable": "Sitemap URLs that are not indexable",
    "missing_from_archive": "Articles missing from the archive",
    "soft_404": "Soft 404s",
    "shell_only": "App-shell pages (content not in HTML)",
}


def build(
    mapping: list[dict],
    *,
    inventory: list[dict] | None = None,
    worklist: list[dict] | None = None,
    problems: list[dict] | None = None,
    compare: list[dict] | None = None,
    sitemap: list[dict] | None = None,
    excluded: int = 0,
) -> dict:
    actions = Counter((r.get("action") or "").upper() for r in mapping)
    approved = Counter(
        (r.get("action") or "").upper() for r in mapping if truthy(r.get("approved"))
    )
    high_review = sum(
        1
        for r in mapping
        if (r.get("action") or "").upper() == "REVIEW" and r.get("priority") == "high"
    )
    totals = {
        "legacy_urls_mapped": len(mapping),
        "preserved_keep": actions["KEEP"],
        "redirected_301": actions["REDIRECT_301"],
        "redirected_301_approved": approved["REDIRECT_301"],
        "retired_410": actions["RETIRE_410"],
        "retired_410_approved": approved["RETIRE_410"],
        "unresolved_review": actions["REVIEW"],
        "unresolved_high_priority": high_review,
        "excluded_system_urls": excluded,
    }
    out = {
        "totals": totals,
        "by_kind": _by(mapping, "kind"),
        "content_worklist": dict(Counter(w.get("content_action") for w in worklist or [])),
        "validation": dict(Counter(p["code"] for p in problems or [])),
    }
    if inventory is not None:
        issues = Counter()
        for row in inventory:
            for issue in filter(None, (row.get("issues") or "").split(";")):
                issues[issue.split(":", 1)[0]] += 1
        out["inventory"] = {
            "urls": len(inventory),
            "page_classes": dict(Counter(r.get("page_class") for r in inventory)),
            "issues": {ISSUE_LABELS.get(k, k): v for k, v in sorted(issues.items())},
        }
    if compare is not None:
        out["prelaunch_compare"] = dict(Counter(r.get("result") for r in compare))
    if sitemap is not None:
        out["sitemap_check"] = dict(Counter(r.get("result") for r in sitemap))
    return out


def _by(rows, field):
    table: dict[str, Counter] = {}
    for r in rows:
        table.setdefault(r.get(field) or "-", Counter())[(r.get("action") or "").upper()] += 1
    return {k: dict(v) for k, v in sorted(table.items())}


def markdown(report: dict, title: str = "Legacy URL migration report") -> str:
    t = report["totals"]
    lines = [
        f"# {title}",
        "",
        "| Outcome | URLs | Approved |",
        "|---|---:|---:|",
        f"| Preserved (KEEP) | {t['preserved_keep']} | {t['preserved_keep']} |",
        f"| Redirected (301) | {t['redirected_301']} | {t['redirected_301_approved']} |",
        f"| Retired (410) | {t['retired_410']} | {t['retired_410_approved']} |",
        f"| Unresolved (REVIEW) | {t['unresolved_review']} | – |",
        f"| **Total mapped** | **{t['legacy_urls_mapped']}** | |",
        "",
        f"High-priority unresolved: **{t['unresolved_high_priority']}**. "
        f"System URLs excluded from mapping: {t['excluded_system_urls']}.",
        "",
    ]
    sections = [
        ("By kind", report.get("by_kind")),
        ("Content to import or rewrite", report.get("content_worklist")),
        ("Mapping validation", report.get("validation")),
        ("Prelaunch comparison", report.get("prelaunch_compare")),
        ("Sitemap check", report.get("sitemap_check")),
    ]
    inv = report.get("inventory")
    if inv:
        sections.insert(0, ("Inventory page classes", inv["page_classes"]))
        sections.insert(1, ("Inventory issues", inv["issues"]))
    for heading, data in sections:
        if not data:
            continue
        lines += [f"## {heading}", ""]
        for key, value in data.items():
            if isinstance(value, dict):
                value = ", ".join(f"{k} {v}" for k, v in value.items())
            lines.append(f"- {key}: {value}")
        lines.append("")
    return "\n".join(lines)
