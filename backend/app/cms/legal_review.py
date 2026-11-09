"""Review status of legal documents (the CMS "Legal document" section).

A document is "pending_review" until someone marks it "approved". While pending, it is
shown as "Draft — pending legal review" with no effective date, the page is noindex and
it is left out of the sitemap and of structured-data claims, whatever the page's own SEO
settings say. Templates and new sections start as pending, so publishing a template
unchanged can never present it as approved. Approval needs an effective date and the
draft wording removed.

Documents saved before review status existed have no value; they are left as they were
(their editor shows "Pending legal review" the next time they are opened and saved).
"""

from __future__ import annotations

from typing import Any

PENDING = "pending_review"
APPROVED = "approved"
CHOICES = {PENDING: "Pending legal review (draft)", APPROVED: "Approved"}
DRAFT_MARKERS = ("pending legal review", "decision pending")


def pending_legal_review(sections: list[dict[str, Any]] | None) -> bool:
    """Whether a page (draft or published snapshot) shows a legal document still under
    review. Hidden sections don't count."""
    return any(
        s.get("section_type") == "legal_document"
        and s.get("is_visible", True)
        and (s.get("content") or {}).get("review_status") == PENDING
        for s in sections or []
    )


def check_approval(content: dict[str, Any], errors: dict[str, Any]) -> None:
    """An approved document must say when it takes effect and carry no draft wording."""
    if content.get("review_status") != APPROVED:
        return
    if not content.get("effective_date"):
        errors["effective_date"] = ["Set the effective date before marking the document approved."]
    notice = f"{content.get('notice_title') or ''} {content.get('notice') or ''}".lower()
    if any(m in notice for m in DRAFT_MARKERS):
        errors["notice"] = ["Remove the draft notice before marking the document approved."]
    for block in content.get("body") or []:
        if block.get("type") == "callout" and any(
            m in f"{block.get('title') or ''} {block.get('text') or ''}".lower()
            for m in DRAFT_MARKERS
        ):
            errors["body"] = ["Remove the “Decision pending” notes before marking it approved."]
            break
