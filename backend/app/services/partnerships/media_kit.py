"""The media kit: editable content (draft/published) and dated audience measurements.

Every figure shown publicly is an administrator-entered measurement with its platform,
source and measurement date, displayed as "measured on …" (never as a live count).
Social followers are always labelled as social followers, never as website traffic.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ...cms.blocks import safe_href
from ...extensions import db
from ...models import AdPlacement, AudienceMetric, MediaAsset, SiteSetting
from ...utils.errors import NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import common
from .advertising import public_rates

DRAFT_KEY = "media_kit.draft"
PUBLISHED_KEY = "media_kit.published"
METRIC_TYPES = {
    "social_followers": "Social media followers",
    "newsletter_subscribers": "Newsletter subscribers (confirmed)",
    "website_users": "Website users",
    "website_pageviews": "Website page views",
    "email_open_rate": "Email open rate (%)",
    "other": "Other",
}
TEXT_FIELDS = {
    "about": 3000,
    "editorial_focus": 3000,
    "audience_summary": 3000,
    "audience_geography": 1000,
    "placements_intro": 2000,
    "collaboration_guidelines": 4000,
    "sponsorship_policies": 4000,
}
EMPTY: dict[str, Any] = {
    **{k: "" for k in TEXT_FIELDS},
    "content_categories": [],
    "campaign_formats": [],
    "contact_cta": {"label": "Start a partnership conversation", "href": "/partner-with-us"},
    "brand_asset_ids": [],
    "show_rate_card": False,
    "show_metrics": True,
    "show_placements": True,
}


def _get(key: str) -> dict[str, Any] | None:
    record = db.session.get(SiteSetting, key)
    return record.value if record is not None and isinstance(record.value, dict) else None


def _set(key: str, value: dict[str, Any], actor) -> None:
    record = db.session.get(SiteSetting, key) or SiteSetting(key=key)
    record.value, record.updated_by_id = value, actor.id
    db.session.add(record)


def validate(data: dict[str, Any]) -> dict[str, Any]:
    doc = dict(EMPTY)
    for field, limit in TEXT_FIELDS.items():
        doc[field] = common.text(data, field, limit)
    cats = data.get("content_categories") or []
    if not isinstance(cats, list) or len(cats) > 20:
        raise ValidationError(details={"content_categories": ["Up to 20 categories."]})
    doc["content_categories"] = [common.text({"v": c}, "v", 80) for c in cats if str(c).strip()]
    formats = data.get("campaign_formats") or []
    if not isinstance(formats, list) or len(formats) > 20:
        raise ValidationError(details={"campaign_formats": ["Up to 20 formats."]})
    doc["campaign_formats"] = [
        {
            "name": common.text(f, "name", 120, required=True),
            "description": common.text(f, "description", 600),
        }
        for f in formats
        if isinstance(f, dict)
    ]
    cta = data.get("contact_cta") or EMPTY["contact_cta"]
    label = common.text(cta, "label", 60, required=True)
    href = str(cta.get("href") or "").strip()
    if not safe_href(href) or href.startswith(("/admin", "/api")):
        raise ValidationError(details={"contact_cta": ["Use a site path or https link."]})
    doc["contact_cta"] = {"label": label, "href": href}
    assets = data.get("brand_asset_ids") or []
    if (
        not isinstance(assets, list)
        or len(assets) > 20
        or not all(isinstance(i, int) and db.session.get(MediaAsset, i) for i in assets)
    ):
        raise ValidationError(
            details={"brand_asset_ids": ["Choose approved assets from the media library."]}
        )
    doc["brand_asset_ids"] = assets
    for flag in ("show_rate_card", "show_metrics", "show_placements"):
        doc[flag] = data.get(flag, EMPTY[flag]) is True
    return doc


def admin_view() -> dict[str, Any]:
    draft = _get(DRAFT_KEY) or _get(PUBLISHED_KEY) or dict(EMPTY)
    published = _get(PUBLISHED_KEY)
    return {
        "draft": {**EMPTY, **draft},
        "published": published is not None,
        "has_changes": draft != published,
    }


def save_draft(data: dict[str, Any], actor) -> dict[str, Any]:
    doc = validate(data)
    _set(DRAFT_KEY, doc, actor)
    audit_service.record("media_kit.draft_saved", "media_kit", actor=actor)
    return doc


def publish(actor) -> None:
    draft = _get(DRAFT_KEY)
    if draft is None:
        raise ValidationError("Save the media kit draft first.")
    _set(PUBLISHED_KEY, validate(draft), actor)
    audit_service.record("media_kit.published", "media_kit", actor=actor)
    from ..publication_service import record_public_change

    record_public_change("media_kit", "advertise", "media_kit_published", actor)


def metric_dict(m: AudienceMetric) -> dict[str, Any]:
    return {
        "id": m.id,
        "metric_type": m.metric_type,
        "label": METRIC_TYPES.get(m.metric_type, m.metric_type),
        "value": float(m.value),
        "platform": m.platform,
        "period_label": m.period_label,
        "source": m.source,
        "measured_on": m.measured_on.isoformat(),
        "verified": m.verified,
        "is_public": m.is_public,
        "notes": m.notes,
        "entered_by_id": m.entered_by_id,
        "updated_at": iso(m.updated_at),
    }


def list_metrics() -> list[dict[str, Any]]:
    return [
        metric_dict(m)
        for m in db.session.scalars(
            select(AudienceMetric).order_by(AudienceMetric.measured_on.desc())
        )
    ]


def save_metric(
    data: dict[str, Any], actor, metric: AudienceMetric | None = None
) -> AudienceMetric:
    creating = metric is None
    metric = metric or AudienceMetric(entered_by_id=actor.id)
    if "metric_type" in data or creating:
        metric.metric_type = common.choice(data, "metric_type", tuple(METRIC_TYPES))
    if "value" in data or creating:
        value = data.get("value")
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value < 0
            or value > 10**12
        ):
            raise ValidationError(details={"value": ["Enter the measured number."]})
        if metric.metric_type == "email_open_rate" and value > 100:
            raise ValidationError(details={"value": ["A rate is a percentage up to 100."]})
        metric.value = value
    if "platform" in data or creating:
        metric.platform = common.text(data, "platform", 80, required=True)
    if "source" in data or creating:
        metric.source = common.text(data, "source", 300, required=True)
    if "measured_on" in data or creating:
        measured = common.parse_date(data, "measured_on", required=True)
        if measured > common.now().date():
            raise ValidationError(
                details={"measured_on": ["A measurement can't be dated in the future."]}
            )
        metric.measured_on = measured
    for field, limit in (("period_label", 80), ("notes", 600)):
        if field in data:
            setattr(metric, field, common.text(data, field, limit))
    if "verified" in data:
        metric.verified = data["verified"] is True
    if "is_public" in data:
        metric.is_public = data["is_public"] is True
    if metric.is_public and not metric.verified:
        raise ValidationError(
            details={"is_public": ["Only verified measurements can be shown publicly."]}
        )
    db.session.add(metric)
    db.session.flush()
    audit_service.record("audience_metric.saved", "audience_metric", metric.id, actor=actor)
    return metric


def delete_metric(metric_id: int, actor) -> None:
    metric = db.session.get(AudienceMetric, metric_id)
    if metric is None:
        raise NotFoundError()
    db.session.delete(metric)
    audit_service.record("audience_metric.deleted", "audience_metric", metric_id, actor=actor)


def public_metrics() -> list[dict[str, Any]]:
    rows = db.session.scalars(
        select(AudienceMetric)
        .where(AudienceMetric.is_public.is_(True), AudienceMetric.verified.is_(True))
        .order_by(AudienceMetric.metric_type, AudienceMetric.measured_on.desc())
    )
    return [
        {
            "label": METRIC_TYPES.get(m.metric_type, m.metric_type),
            "metric_type": m.metric_type,
            "value": float(m.value),
            "platform": m.platform,
            "period_label": m.period_label,
            "source": m.source,
            "measured_on": m.measured_on.isoformat(),
        }
        for m in rows
    ]


def public_document() -> dict[str, Any] | None:
    doc = _get(PUBLISHED_KEY)
    if doc is None:
        return None
    assets = []
    for media_id in doc.get("brand_asset_ids", []):
        asset = db.session.get(MediaAsset, media_id)
        if asset and asset.as_image():
            assets.append(asset.as_image())
    placements = (
        [
            {
                "name": p.name,
                "type": p.placement_type,
                "channel": p.channel,
                "dimensions": p.dimensions,
                "formats": p.creative_formats,
            }
            for p in db.session.scalars(
                select(AdPlacement)
                .where(AdPlacement.is_active.is_(True))
                .order_by(AdPlacement.name)
            )
        ]
        if doc.get("show_placements")
        else []
    )
    return {
        **{k: doc.get(k, v) for k, v in EMPTY.items() if k != "brand_asset_ids"},
        "brand_assets": assets,
        "placements": placements,
        "rate_card": public_rates() if doc.get("show_rate_card") else [],
        "metrics": public_metrics() if doc.get("show_metrics") else [],
        "notes": [
            "Audience figures are measurements taken on the date shown, from the stated source.",
            "Rates are indicative; final terms are agreed in writing for each campaign.",
        ],
    }
