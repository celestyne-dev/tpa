"""Sponsored articles and newsletters (disclosure workflow).

Sponsorship details sit beside the existing article: the article keeps its editor,
revisions, approvals, SEO and publishing queue. Publication is refused until a
disclosure is set and the sponsorship review is approved; once a sponsorship exists
the public label is always shown, whatever its review state.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ...auth.permissions import Permission as P
from ...auth.rbac import has_permissions
from ...extensions import db
from ...models import (
    Article,
    ArticleSponsorship,
    MediaAsset,
    NewsletterSponsorship,
    Partner,
    SponsorshipCampaign,
)
from ...models.partnerships import REVIEW_STATUSES
from ...utils.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import common

DEFAULT_LABEL = "Sponsored Content"
MIN_DISCLOSURE = 10


def publish_problems(article: Article) -> list[str]:
    record = getattr(article, "sponsorship", None)
    if record is None:
        return []
    problems = []
    if len(record.disclosure_text.strip()) < MIN_DISCLOSURE:
        problems.append("Add the sponsorship disclosure shown to readers.")
    if not record.sponsor_name.strip():
        problems.append("Name the sponsoring organisation.")
    if record.review_status != "approved":
        problems.append("The sponsorship review must be approved before publishing.")
    return problems


def sponsorship_dict(record: ArticleSponsorship | None, user) -> dict[str, Any] | None:
    if record is None:
        return None
    return {
        "article_id": record.article_id,
        "partner_id": record.partner_id,
        "campaign_id": record.campaign_id,
        "sponsor_name": record.sponsor_name,
        "label": record.label,
        "disclosure_text": record.disclosure_text,
        "review_status": record.review_status,
        "sponsor_approval_notes": record.sponsor_approval_notes,
        "starts_on": record.starts_on.isoformat() if record.starts_on else None,
        "ends_on": record.ends_on.isoformat() if record.ends_on else None,
        "sponsored_links": record.sponsored_links,
        "sponsor_media_ids": record.sponsor_media_ids,
        "approved_at": iso(record.approved_at),
        "can_approve": has_permissions(user, P.SPONSORSHIPS_APPROVE),
        "history": common.history("article_sponsorship", record.article_id),
    }


def get_article(article_id: int) -> Article:
    article = db.session.get(Article, article_id)
    if article is None:
        raise NotFoundError()
    return article


def save(article: Article, data: dict[str, Any], actor) -> ArticleSponsorship:
    record = article.sponsorship
    creating = record is None
    record = record or ArticleSponsorship(article_id=article.id, review_status="draft")
    if "sponsor_name" in data or creating:
        record.sponsor_name = common.text(data, "sponsor_name", 160, required=True)
    if "label" in data:
        label = common.text(data, "label", 60) or DEFAULT_LABEL
        if (
            "sponsor" not in label.lower()
            and "paid" not in label.lower()
            and "ad" not in label.lower().split()
        ):
            raise ValidationError(
                details={"label": ["The label must clearly say the content is sponsored or paid."]}
            )
        record.label = label
    if "disclosure_text" in data:
        record.disclosure_text = common.text(data, "disclosure_text", 400)
    if "sponsor_approval_notes" in data:
        record.sponsor_approval_notes = common.text(data, "sponsor_approval_notes", 2000)
    if "partner_id" in data:
        record.partner_id = (
            data["partner_id"]
            if data["partner_id"] and db.session.get(Partner, data["partner_id"])
            else None
        )
    if "campaign_id" in data:
        if data["campaign_id"] and db.session.get(SponsorshipCampaign, data["campaign_id"]) is None:
            raise ValidationError(details={"campaign_id": ["Unknown campaign."]})
        record.campaign_id = data["campaign_id"] or None
    if "starts_on" in data:
        record.starts_on = common.parse_date(data, "starts_on")
    if "ends_on" in data:
        record.ends_on = common.parse_date(data, "ends_on")
    if record.starts_on and record.ends_on and record.ends_on < record.starts_on:
        raise ValidationError(
            details={"ends_on": ["The end date must be on or after the start date."]}
        )
    if "sponsored_links" in data:
        links = data["sponsored_links"] or []
        if not isinstance(links, list) or len(links) > 20:
            raise ValidationError(details={"sponsored_links": ["Add up to 20 links."]})
        record.sponsored_links = [
            common.safe_https_url(u, "sponsored_links", required=True) for u in links
        ]
    if "sponsor_media_ids" in data:
        ids = data["sponsor_media_ids"] or []
        if (
            not isinstance(ids, list)
            or len(ids) > 20
            or not all(isinstance(i, int) and db.session.get(MediaAsset, i) for i in ids)
        ):
            raise ValidationError(
                details={"sponsor_media_ids": ["Choose images from the media library."]}
            )
        record.sponsor_media_ids = ids
    previous = record.review_status
    if "review_status" in data:
        target = common.choice(data, "review_status", REVIEW_STATUSES)
        if target == "approved":
            raise ValidationError(
                details={"review_status": ["Use “Approve” to approve the sponsorship."]}
            )
        record.review_status = target
    elif not creating and previous == "approved" and set(data) - {"sponsor_approval_notes"}:
        record.review_status = "internal_review"  # material edits need a fresh approval
    if previous == "approved" and record.review_status != "approved":
        record.approved_at = record.approved_by_id = None
        if article.status == "scheduled":
            # Never let a scheduled publication go out without the approval.
            article.status, article.published_at = "draft", None
            audit_service.record(
                "article.unscheduled",
                "article",
                article.id,
                actor=actor,
                details={"reason": "sponsorship approval withdrawn"},
            )
    db.session.add(record)
    db.session.flush()
    common.record_event(
        "article_sponsorship",
        article.id,
        "created" if creating else "updated",
        actor,
        from_state=previous if not creating else "",
        to_state=record.review_status,
    )
    audit_service.record(
        "article.sponsorship_saved",
        "article",
        article.id,
        actor=actor,
        details={"fields": sorted(data), "review_status": record.review_status},
    )
    _touch_public(article, actor)
    return record


def approve(article: Article, actor) -> ArticleSponsorship:
    if not has_permissions(actor, P.SPONSORSHIPS_APPROVE):
        raise ForbiddenError()
    record = article.sponsorship
    if record is None:
        raise NotFoundError("This article has no sponsorship.")
    if len(record.disclosure_text.strip()) < MIN_DISCLOSURE or not record.sponsor_name.strip():
        raise ValidationError(
            details={"review_status": ["Add the sponsor name and disclosure first."]}
        )
    previous = record.review_status
    record.review_status = "approved"
    record.approved_at, record.approved_by_id = common.now(), actor.id
    common.record_event(
        "article_sponsorship",
        article.id,
        "approved",
        actor,
        from_state=previous,
        to_state="approved",
    )
    audit_service.record("article.sponsorship_approved", "article", article.id, actor=actor)
    return record


def remove(article: Article, actor) -> None:
    if article.status in ("published", "scheduled") or article.first_published_at:
        raise ConflictError(
            "Published sponsored content keeps its disclosure. Unpublish or archive it instead."
        )
    if article.sponsorship is not None:
        db.session.delete(article.sponsorship)
        audit_service.record("article.sponsorship_removed", "article", article.id, actor=actor)


def _touch_public(article: Article, actor) -> None:
    if article.status == "published":
        from ..publication_service import record_public_change

        record_public_change("article", article.id, "sponsorship_changed", actor)


def set_newsletter_sponsorship(campaign, value: Any, actor) -> None:
    if not has_permissions(actor, P.SPONSORSHIPS_MANAGE):
        raise ForbiddenError("Changing a newsletter sponsorship needs sponsorship rights.")
    existing = db.session.scalar(
        select(NewsletterSponsorship).where(NewsletterSponsorship.campaign_id == campaign.id)
    )
    if value is None:
        if existing is not None:
            db.session.delete(existing)
        return
    if not isinstance(value, dict):
        raise ValidationError(details={"sponsorship": ["Send the sponsor and disclosure."]})
    record = existing or NewsletterSponsorship(campaign_id=campaign.id)
    record.sponsor_name = common.text(value, "sponsor_name", 160, required=True)
    record.disclosure_text = common.text(value, "disclosure_text", 400, required=True)
    sc = value.get("sponsorship_campaign_id")
    if sc and db.session.get(SponsorshipCampaign, sc) is None:
        raise ValidationError(details={"sponsorship": ["Unknown sponsorship campaign."]})
    record.sponsorship_campaign_id = sc or None
    db.session.add(record)
    db.session.flush()
    db.session.refresh(campaign)
    audit_service.record("newsletter.sponsorship_saved", "campaign", campaign.id, actor=actor)
