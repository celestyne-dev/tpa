"""Partnership and affiliate reporting.

Each figure is reported per currency and kept in its own category: pipeline
(expected, not revenue), contracted, completed, invoiced (manual records), received
(verified or reconciled), outstanding (contracted minus received) and affiliate
commissions as reported/paid by networks. Nothing is converted between currencies.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select

from ...extensions import db
from ...models import (
    AffiliateCommission,
    Booking,
    Opportunity,
    PartnershipFinanceEntry,
    SponsorshipCampaign,
)
from ...utils.errors import NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso
from . import common
from .advertising import effective_state, utilization
from .crm import OPEN_STAGES, get_partner

CONTRACTED = ("approved", "scheduled", "active", "completed")


def _filters(args: dict[str, Any]) -> dict[str, Any]:
    today = date.today()
    return {
        "date_from": common.parse_date(args, "date_from") or today - timedelta(days=365),
        "date_to": common.parse_date(args, "date_to") or today + timedelta(days=365),
        "partner_id": int(args["partner_id"]) if args.get("partner_id") else None,
        "campaign_id": int(args["campaign_id"]) if args.get("campaign_id") else None,
        "currency": (args.get("currency") or "").upper() or None,
        "status": args.get("status") or None,
        "channel": args.get("channel") or None,
    }


def report(args: dict[str, Any]) -> dict[str, Any]:
    f = _filters(args)
    totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def add(currency: str, key: str, amount: int | None) -> None:
        if amount is None or (f["currency"] and currency != f["currency"]):
            return
        totals[currency][key] += amount

    opportunities = select(Opportunity).where(Opportunity.stage.in_(OPEN_STAGES))
    if f["partner_id"]:
        opportunities = opportunities.where(Opportunity.partner_id == f["partner_id"])
    pipeline_by_stage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for o in db.session.scalars(opportunities):
        add(o.currency, "pipeline_expected", o.expected_value_minor)
        if o.expected_value_minor and (not f["currency"] or o.currency == f["currency"]):
            pipeline_by_stage[o.stage][o.currency] += o.expected_value_minor

    campaigns = select(SponsorshipCampaign).where(SponsorshipCampaign.status.in_(CONTRACTED))
    if f["partner_id"]:
        campaigns = campaigns.where(SponsorshipCampaign.partner_id == f["partner_id"])
    if f["campaign_id"]:
        campaigns = campaigns.where(SponsorshipCampaign.id == f["campaign_id"])
    if f["status"]:
        campaigns = campaigns.where(SponsorshipCampaign.status == f["status"])
    campaign_count = defaultdict(int)
    for c in db.session.scalars(campaigns):
        if c.starts_on and c.starts_on > f["date_to"] or c.ends_on and c.ends_on < f["date_from"]:
            continue
        add(c.currency, "contracted", c.contracted_fee_minor)
        if c.status == "completed":
            add(c.currency, "completed_value", c.contracted_fee_minor)
        campaign_count[c.status] += 1

    entries = select(PartnershipFinanceEntry).where(
        PartnershipFinanceEntry.entry_date >= f["date_from"],
        PartnershipFinanceEntry.entry_date <= f["date_to"],
    )
    if f["partner_id"]:
        entries = entries.where(PartnershipFinanceEntry.partner_id == f["partner_id"])
    if f["campaign_id"]:
        entries = entries.where(PartnershipFinanceEntry.campaign_id == f["campaign_id"])
    for e in db.session.scalars(entries):
        if e.kind == "invoiced":
            add(e.currency, "invoiced", e.amount_minor)
        elif e.verified:
            add(e.currency, "received", e.amount_minor)
        else:
            add(e.currency, "received_unverified", e.amount_minor)

    commissions = select(AffiliateCommission).where(
        AffiliateCommission.occurred_on >= f["date_from"],
        AffiliateCommission.occurred_on <= f["date_to"],
    )
    for c in db.session.scalars(commissions):
        if c.status == "reversed":
            continue
        add(c.currency, "affiliate_reported", c.amount_minor)
        if c.status == "paid":
            add(c.currency, "affiliate_paid", c.amount_minor)

    by_currency = []
    for code in sorted(totals):
        t = totals[code]
        by_currency.append(
            {
                "currency": code,
                "pipeline_expected_minor": t["pipeline_expected"],
                "contracted_minor": t["contracted"],
                "completed_value_minor": t["completed_value"],
                "invoiced_minor": t["invoiced"],
                "received_verified_minor": t["received"],
                "received_unverified_minor": t["received_unverified"],
                "outstanding_minor": max(0, t["contracted"] - t["received"]),
                "affiliate_reported_minor": t["affiliate_reported"],
                "affiliate_paid_minor": t["affiliate_paid"],
            }
        )
    window_start = datetime.combine(f["date_from"], time.min, tzinfo=UTC)
    window_end = datetime.combine(f["date_to"] + timedelta(days=1), time.min, tzinfo=UTC)
    bookings = select(Booking).where(Booking.starts_at < window_end, Booking.ends_at > window_start)
    booking_states = defaultdict(int)

    for b in db.session.scalars(bookings):
        if f["channel"] and b.placement.channel != f["channel"]:
            continue
        if f["partner_id"] and b.partner_id != f["partner_id"]:
            continue
        booking_states[effective_state(b)] += 1
    return {
        "filters": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in f.items()},
        "by_currency": by_currency,
        "pipeline_by_stage": {stage: dict(v) for stage, v in pipeline_by_stage.items()},
        "campaigns_by_status": dict(campaign_count),
        "bookings_by_state": dict(booking_states),
        "booking_utilization": utilization(f["date_from"], f["date_to"]),
        "notes": [
            "Pipeline values are expectations, not revenue.",
            "Invoiced and received amounts are manual records; only verified receipts count "
            "as received.",
            "Affiliate commissions are as reported by networks or entered manually with "
            "evidence; clicks are never counted as earnings.",
            "Currencies are reported separately and never converted.",
        ],
    }


def export_csv(args: dict[str, Any], actor) -> str:
    data = report(args)
    from ...utils.csv_safe import SafeWriter

    writer = SafeWriter()
    columns = list(data["by_currency"][0].keys()) if data["by_currency"] else ["currency"]
    writer.writerow(columns)
    for row in data["by_currency"]:
        writer.writerow([row[c] for c in columns])
    audit_service.record(
        "partnership_report.exported", "partnership_report", actor=actor, details=data["filters"]
    )
    return writer.value()


# ---- manual finance entries ---------------------------------------------------------------


def entry_dict(e: PartnershipFinanceEntry) -> dict[str, Any]:
    return {
        "id": e.id,
        "kind": e.kind,
        "partner_id": e.partner_id,
        "campaign_id": e.campaign_id,
        "amount_minor": e.amount_minor,
        "currency": e.currency,
        "entry_date": e.entry_date.isoformat(),
        "reference": e.reference,
        "verified": e.verified,
        "notes": e.notes,
        "created_at": iso(e.created_at),
    }


def list_entries(args: dict[str, Any]) -> list[dict[str, Any]]:
    query = select(PartnershipFinanceEntry)
    if args.get("partner_id"):
        query = query.where(PartnershipFinanceEntry.partner_id == int(args["partner_id"]))
    return [
        entry_dict(e)
        for e in db.session.scalars(
            query.order_by(PartnershipFinanceEntry.entry_date.desc()).limit(1000)
        )
    ]


def add_entry(data: dict[str, Any], actor) -> PartnershipFinanceEntry:
    partner = get_partner(int(data.get("partner_id") or 0))
    campaign_id = data.get("campaign_id")
    if campaign_id and db.session.get(SponsorshipCampaign, campaign_id) is None:
        raise NotFoundError("Unknown campaign.")
    amount = common.money(data, "amount_minor", required=True)
    if amount == 0:
        raise ValidationError(details={"amount_minor": ["Enter an amount above zero."]})
    entry = PartnershipFinanceEntry(
        kind=common.choice(data, "kind", ("invoiced", "received")),
        partner_id=partner.id,
        campaign_id=campaign_id or None,
        amount_minor=amount,
        currency=common.currency(data),
        entry_date=common.parse_date(data, "entry_date", required=True),
        reference=common.text(data, "reference", 120),
        verified=data.get("verified") is True,
        notes=common.text(data, "notes", 1000),
        entered_by_id=actor.id,
    )
    db.session.add(entry)
    db.session.flush()
    audit_service.record(
        "partnership_finance.entry_added",
        "partnership_finance",
        entry.id,
        actor=actor,
        details={"kind": entry.kind, "currency": entry.currency, "verified": entry.verified},
    )
    return entry
