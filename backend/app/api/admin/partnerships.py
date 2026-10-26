"""Admin API for partners, inquiries, opportunities, sponsorship campaigns, advertising
inventory and bookings, sponsored articles, affiliates, the media kit, audience
measurements and partnership reports. Each method checks its own permission."""

from __future__ import annotations

from flask import Response, request
from flask_jwt_extended import current_user
from flask_restful import Resource

from ...auth.decorators import require_any_permission, require_permission
from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import AudienceMetric, RateCard
from ...services.admin.article_admin import get_article_for
from ...services.partnerships import advertising, affiliates, crm, media_kit, reports, sponsored
from ...utils.errors import NotFoundError, ValidationError
from ...utils.responses import success


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object in the request body.")
    return data


def _args() -> dict:
    def to_int(name, default, low, high):
        raw = request.args.get(name)
        if raw in (None, ""):
            return default
        try:
            return max(low, min(high, int(raw)))
        except ValueError:
            raise ValidationError(details={name: ["Must be a number."]}) from None

    args = {
        k: v for k, v in request.args.items() if k not in ("page", "page_size") and len(v) <= 120
    }
    for key in ("partner_id", "campaign_id", "placement_id", "program_id"):
        if args.get(key) and not args[key].isdigit():
            raise ValidationError(details={key: ["Must be a number."]})
    args["page"] = to_int("page", 1, 1, 10000)
    args["page_size"] = to_int("page_size", 25, 1, 100)
    return args


def _paged(items, total, args):
    return success(items, {"total": total, "page": args["page"], "page_size": args["page_size"]})


# ---- partners and inquiries -------------------------------------------------------------


class PartnerListResource(Resource):
    @require_permission(P.PARTNERSHIPS_VIEW)
    def get(self):
        args = _args()
        return _paged(*crm.list_partners(args), args)

    @require_permission(P.PARTNERSHIPS_MANAGE)
    def post(self):
        partner = crm.save_partner(_body(), current_user)
        db.session.commit()
        return success(crm.partner_dict(partner, detail=True), status=201)


class PartnerResource(Resource):
    @require_permission(P.PARTNERSHIPS_VIEW)
    def get(self, partner_id: int):
        return success(crm.partner_dict(crm.get_partner(partner_id), detail=True))

    @require_permission(P.PARTNERSHIPS_MANAGE)
    def put(self, partner_id: int):
        partner = crm.save_partner(_body(), current_user, crm.get_partner(partner_id))
        db.session.commit()
        return success(crm.partner_dict(partner, detail=True))


class InquiryListResource(Resource):
    @require_permission(P.PARTNERSHIPS_VIEW)
    def get(self):
        args = _args()
        return _paged(*crm.list_inquiries(args), args)


class InquiryResource(Resource):
    @require_permission(P.PARTNERSHIPS_MANAGE)
    def put(self, inquiry_id: int):
        inquiry = crm.update_inquiry(inquiry_id, _body(), current_user)
        db.session.commit()
        return success(crm.inquiry_dict(inquiry))


# ---- opportunities and campaigns --------------------------------------------------------


class OpportunityListResource(Resource):
    @require_permission(P.PARTNERSHIPS_VIEW)
    def get(self):
        args = _args()
        return _paged(*crm.list_opportunities(args, current_user), args)

    @require_permission(P.PARTNERSHIPS_MANAGE)
    def post(self):
        opportunity = crm.save_opportunity(_body(), current_user)
        db.session.commit()
        return success(crm.opportunity_dict(opportunity, current_user, detail=True), status=201)


class OpportunityResource(Resource):
    @require_permission(P.PARTNERSHIPS_VIEW)
    def get(self, opportunity_id: int):
        return success(
            crm.opportunity_dict(crm.get_opportunity(opportunity_id), current_user, detail=True)
        )

    @require_permission(P.PARTNERSHIPS_MANAGE)
    def put(self, opportunity_id: int):
        opportunity = crm.save_opportunity(
            _body(), current_user, crm.get_opportunity(opportunity_id)
        )
        db.session.commit()
        return success(crm.opportunity_dict(opportunity, current_user, detail=True))


class OpportunityStageResource(Resource):
    @require_permission(P.PARTNERSHIPS_MANAGE)
    def post(self, opportunity_id: int):
        opportunity = crm.move_opportunity(
            crm.get_opportunity(opportunity_id), _body(), current_user
        )
        db.session.commit()
        return success(crm.opportunity_dict(opportunity, current_user, detail=True))


class OpportunityInteractionResource(Resource):
    @require_permission(P.PARTNERSHIPS_MANAGE)
    def post(self, opportunity_id: int):
        opportunity = crm.get_opportunity(opportunity_id)
        crm.add_interaction(opportunity, _body(), current_user)
        db.session.commit()
        return success(crm.opportunity_dict(opportunity, current_user, detail=True), status=201)


class SponsorshipCampaignListResource(Resource):
    @require_permission(P.SPONSORSHIPS_VIEW)
    def get(self):
        args = _args()
        return _paged(*crm.list_campaigns(args, current_user), args)

    @require_permission(P.SPONSORSHIPS_MANAGE)
    def post(self):
        campaign = crm.save_campaign(_body(), current_user)
        db.session.commit()
        return success(crm.campaign_dict(campaign, current_user, detail=True), status=201)


class SponsorshipCampaignResource(Resource):
    @require_permission(P.SPONSORSHIPS_VIEW)
    def get(self, campaign_id: int):
        return success(crm.campaign_dict(crm.get_campaign(campaign_id), current_user, detail=True))

    @require_permission(P.SPONSORSHIPS_MANAGE)
    def put(self, campaign_id: int):
        campaign = crm.save_campaign(_body(), current_user, crm.get_campaign(campaign_id))
        db.session.commit()
        return success(crm.campaign_dict(campaign, current_user, detail=True))


class SponsorshipCampaignStatusResource(Resource):
    @require_any_permission(P.SPONSORSHIPS_MANAGE, P.SPONSORSHIPS_APPROVE)
    def post(self, campaign_id: int):
        campaign = crm.move_campaign(crm.get_campaign(campaign_id), _body(), current_user)
        db.session.commit()
        return success(crm.campaign_dict(campaign, current_user, detail=True))


class PartnershipOptionsResource(Resource):
    @require_any_permission(
        P.PARTNERSHIPS_VIEW, P.SPONSORSHIPS_VIEW, P.ADVERTISING_VIEW, P.AFFILIATES_VIEW
    )
    def get(self):
        partners, _ = crm.list_partners({"page": 1, "page_size": 500})
        campaigns, _ = crm.list_campaigns({"page": 1, "page_size": 500}, current_user)
        return success(
            {
                "users": crm.user_options(),
                "partners": [{"id": p["id"], "name": p["name"]} for p in partners],
                "campaigns": [
                    {"id": c["id"], "name": c["name"], "status": c["status"]} for c in campaigns
                ],
                "placements": [
                    {"id": p["id"], "key": p["key"], "name": p["name"], "is_active": p["is_active"]}
                    for p in advertising.list_placements()
                ],
            }
        )


# ---- inventory, rates and bookings ------------------------------------------------------


class PlacementListResource(Resource):
    @require_permission(P.ADVERTISING_VIEW)
    def get(self):
        return success(advertising.list_placements())

    @require_permission(P.ADVERTISING_MANAGE_INVENTORY)
    def post(self):
        placement = advertising.save_placement(_body(), current_user)
        db.session.commit()
        return success(advertising.placement_dict(placement), status=201)


class PlacementResource(Resource):
    @require_permission(P.ADVERTISING_MANAGE_INVENTORY)
    def put(self, placement_id: int):
        placement = advertising.save_placement(
            _body(), current_user, advertising.get_placement(placement_id)
        )
        db.session.commit()
        return success(advertising.placement_dict(placement))


class RateListResource(Resource):
    @require_permission(P.ADVERTISING_VIEW)
    def get(self):
        return success(advertising.list_rates())

    @require_permission(P.ADVERTISING_MANAGE_INVENTORY)
    def post(self):
        rate = advertising.save_rate(_body(), current_user)
        db.session.commit()
        return success(advertising.rate_dict(rate), status=201)


class RateResource(Resource):
    @require_permission(P.ADVERTISING_MANAGE_INVENTORY)
    def put(self, rate_id: int):
        rate = db.session.get(RateCard, rate_id)
        if rate is None:
            raise NotFoundError()
        rate = advertising.save_rate(_body(), current_user, rate)
        db.session.commit()
        return success(advertising.rate_dict(rate))


class BookingListResource(Resource):
    @require_permission(P.ADVERTISING_VIEW)
    def get(self):
        return success(advertising.list_bookings(_args(), current_user))

    @require_permission(P.ADVERTISING_MANAGE_BOOKINGS)
    def post(self):
        booking, found = advertising.save_booking(_body(), current_user)
        db.session.commit()
        return success(
            advertising.booking_dict(booking, current_user), {"conflicts": found}, status=201
        )


class BookingResource(Resource):
    @require_permission(P.ADVERTISING_VIEW)
    def get(self, booking_id: int):
        return success(advertising.booking_dict(advertising.get_booking(booking_id), current_user))

    @require_permission(P.ADVERTISING_MANAGE_BOOKINGS)
    def put(self, booking_id: int):
        booking, found = advertising.save_booking(
            _body(), current_user, advertising.get_booking(booking_id)
        )
        db.session.commit()
        return success(advertising.booking_dict(booking, current_user), {"conflicts": found})


class BookingStatusResource(Resource):
    @require_permission(P.ADVERTISING_MANAGE_BOOKINGS)
    def post(self, booking_id: int):
        booking = advertising.move_booking(
            advertising.get_booking(booking_id), _body(), current_user
        )
        db.session.commit()
        return success(advertising.booking_dict(booking, current_user))


class BookingConflictResource(Resource):
    @require_permission(P.ADVERTISING_VIEW)
    def post(self):
        from ...services.partnerships import common

        data = _body()
        placement = advertising.get_placement(int(data.get("placement_id") or 0))
        starts = common.parse_datetime(data, "starts_at", required=True)
        ends = common.parse_datetime(data, "ends_at", required=True)
        exclude = data.get("booking_id") if isinstance(data.get("booking_id"), int) else None
        return success(advertising.conflicts(placement, starts, ends, exclude))


# ---- finance ----------------------------------------------------------------------------


class FinanceEntryListResource(Resource):
    @require_permission(P.PARTNERSHIP_FINANCE_VIEW)
    def get(self):
        return success(reports.list_entries(_args()))

    @require_permission(P.PARTNERSHIP_FINANCE_MANAGE)
    def post(self):
        entry = reports.add_entry(_body(), current_user)
        db.session.commit()
        return success(reports.entry_dict(entry), status=201)


class PartnershipReportResource(Resource):
    @require_any_permission(P.PARTNERSHIP_FINANCE_VIEW, P.PARTNERSHIP_REPORTS_EXPORT)
    def get(self):
        return success(reports.report(_args()))


class PartnershipReportExportResource(Resource):
    @require_permission(P.PARTNERSHIP_REPORTS_EXPORT)
    def get(self):
        content = reports.export_csv(_args(), current_user)
        db.session.commit()
        return Response(
            content,
            mimetype="text/csv",
            headers={"Content-Disposition": 'attachment; filename="partnership-report.csv"'},
        )


# ---- sponsored articles -----------------------------------------------------------------


class ArticleSponsorshipResource(Resource):
    @require_permission(P.SPONSORSHIPS_VIEW)
    def get(self, article_id: int):
        article = get_article_for(article_id, current_user)
        return success(sponsored.sponsorship_dict(article.sponsorship, current_user))

    @require_permission(P.SPONSORSHIPS_MANAGE)
    def put(self, article_id: int):
        article = get_article_for(article_id, current_user)
        record = sponsored.save(article, _body(), current_user)
        db.session.commit()
        return success(sponsored.sponsorship_dict(record, current_user))

    @require_permission(P.SPONSORSHIPS_MANAGE)
    def delete(self, article_id: int):
        article = get_article_for(article_id, current_user)
        sponsored.remove(article, current_user)
        db.session.commit()
        return success(None)


class ArticleSponsorshipApproveResource(Resource):
    @require_permission(P.SPONSORSHIPS_APPROVE)
    def post(self, article_id: int):
        article = get_article_for(article_id, current_user)
        record = sponsored.approve(article, current_user)
        db.session.commit()
        return success(sponsored.sponsorship_dict(record, current_user))


# ---- affiliates -------------------------------------------------------------------------


class AffiliateProgramListResource(Resource):
    @require_permission(P.AFFILIATES_VIEW)
    def get(self):
        return success(affiliates.list_programs(current_user))

    @require_permission(P.AFFILIATES_MANAGE)
    def post(self):
        program = affiliates.save_program(_body(), current_user)
        db.session.commit()
        return success(affiliates.program_dict(program, current_user), status=201)


class AffiliateProgramResource(Resource):
    @require_permission(P.AFFILIATES_MANAGE)
    def put(self, program_id: int):
        program = affiliates.save_program(_body(), current_user, affiliates.get_program(program_id))
        db.session.commit()
        return success(affiliates.program_dict(program, current_user))


class AffiliateLinkListResource(Resource):
    @require_permission(P.AFFILIATES_VIEW)
    def get(self):
        return success(affiliates.list_links(_args()))

    @require_permission(P.AFFILIATES_MANAGE_LINKS)
    def post(self):
        link = affiliates.save_link(_body(), current_user)
        db.session.commit()
        return success(affiliates.link_dict(link), status=201)


class AffiliateLinkResource(Resource):
    @require_permission(P.AFFILIATES_MANAGE_LINKS)
    def put(self, link_id: int):
        link = affiliates.save_link(_body(), current_user, affiliates.get_link(link_id))
        db.session.commit()
        return success(affiliates.link_dict(link))


class AffiliateClickResource(Resource):
    @require_permission(P.AFFILIATES_VIEW)
    def get(self):
        return success(affiliates.click_report(_args()))


class AffiliateCommissionListResource(Resource):
    @require_any_permission(P.AFFILIATES_MANAGE, P.PARTNERSHIP_FINANCE_VIEW)
    def get(self):
        return success(affiliates.list_commissions(_args()))

    @require_any_permission(P.AFFILIATES_MANAGE, P.PARTNERSHIP_FINANCE_MANAGE)
    def post(self):
        record = affiliates.add_manual_commission(_body(), current_user)
        db.session.commit()
        return success(affiliates.commission_dict(record), status=201)


class AffiliateCommissionStatusResource(Resource):
    @require_any_permission(P.AFFILIATES_MANAGE, P.PARTNERSHIP_FINANCE_MANAGE)
    def post(self, commission_id: int):
        record = affiliates.update_commission_status(
            commission_id, _body().get("status"), current_user
        )
        db.session.commit()
        return success(affiliates.commission_dict(record))


class AffiliateCommissionImportResource(Resource):
    @require_any_permission(P.AFFILIATES_MANAGE, P.PARTNERSHIP_FINANCE_MANAGE)
    def post(self):
        upload = request.files.get("file")
        if upload is None:
            raise ValidationError(details={"file": ["Choose a CSV file."]})
        raw = upload.read(2_000_001)
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValidationError(details={"file": ["The file must be UTF-8 CSV."]}) from None
        result = affiliates.import_commissions(content, dict(request.form), current_user)
        db.session.commit()
        return success(result)


class AffiliateDisclosureResource(Resource):
    @require_permission(P.AFFILIATES_VIEW)
    def get(self):
        return success({"text": affiliates.disclosure_text()})

    @require_permission(P.AFFILIATES_MANAGE)
    def put(self):
        text = affiliates.set_disclosure(_body().get("text"), current_user)
        db.session.commit()
        return success({"text": text})


# ---- media kit and audience measurements ------------------------------------------------


class MediaKitResource(Resource):
    @require_permission(P.MEDIA_KIT_MANAGE)
    def get(self):
        return success(media_kit.admin_view())

    @require_permission(P.MEDIA_KIT_MANAGE)
    def put(self):
        media_kit.save_draft(_body(), current_user)
        db.session.commit()
        return success(media_kit.admin_view())


class MediaKitPublishResource(Resource):
    @require_permission(P.MEDIA_KIT_MANAGE)
    def post(self):
        media_kit.publish(current_user)
        db.session.commit()
        return success(media_kit.admin_view())


class AudienceMetricListResource(Resource):
    @require_any_permission(P.MEDIA_KIT_MANAGE, P.PARTNERSHIPS_VIEW)
    def get(self):
        return success(media_kit.list_metrics(), {"types": media_kit.METRIC_TYPES})

    @require_permission(P.MEDIA_KIT_MANAGE)
    def post(self):
        metric = media_kit.save_metric(_body(), current_user)
        db.session.commit()
        return success(media_kit.metric_dict(metric), status=201)


class AudienceMetricResource(Resource):
    @require_permission(P.MEDIA_KIT_MANAGE)
    def put(self, metric_id: int):
        metric = db.session.get(AudienceMetric, metric_id)
        if metric is None:
            raise NotFoundError()
        metric = media_kit.save_metric(_body(), current_user, metric)
        db.session.commit()
        return success(media_kit.metric_dict(metric))

    @require_permission(P.MEDIA_KIT_MANAGE)
    def delete(self, metric_id: int):
        media_kit.delete_metric(metric_id, current_user)
        db.session.commit()
        return success(None)


PARTNERSHIP_ROUTES = [
    (PartnerListResource, "/admin/partners"),
    (PartnerResource, "/admin/partners/<int:partner_id>"),
    (InquiryListResource, "/admin/partnership-inquiries"),
    (InquiryResource, "/admin/partnership-inquiries/<int:inquiry_id>"),
    (OpportunityListResource, "/admin/opportunities"),
    (OpportunityResource, "/admin/opportunities/<int:opportunity_id>"),
    (OpportunityStageResource, "/admin/opportunities/<int:opportunity_id>/stage"),
    (OpportunityInteractionResource, "/admin/opportunities/<int:opportunity_id>/interactions"),
    (SponsorshipCampaignListResource, "/admin/sponsorship-campaigns"),
    (SponsorshipCampaignResource, "/admin/sponsorship-campaigns/<int:campaign_id>"),
    (SponsorshipCampaignStatusResource, "/admin/sponsorship-campaigns/<int:campaign_id>/status"),
    (PartnershipOptionsResource, "/admin/partnership-options"),
    (PlacementListResource, "/admin/ad-placements"),
    (PlacementResource, "/admin/ad-placements/<int:placement_id>"),
    (RateListResource, "/admin/rate-cards"),
    (RateResource, "/admin/rate-cards/<int:rate_id>"),
    (BookingListResource, "/admin/ad-bookings"),
    (BookingConflictResource, "/admin/ad-bookings/conflicts"),
    (BookingResource, "/admin/ad-bookings/<int:booking_id>"),
    (BookingStatusResource, "/admin/ad-bookings/<int:booking_id>/status"),
    (FinanceEntryListResource, "/admin/partnership-finance"),
    (PartnershipReportResource, "/admin/partnership-reports"),
    (PartnershipReportExportResource, "/admin/partnership-reports/export"),
    (ArticleSponsorshipResource, "/admin/articles/<int:article_id>/sponsorship"),
    (ArticleSponsorshipApproveResource, "/admin/articles/<int:article_id>/sponsorship/approve"),
    (AffiliateProgramListResource, "/admin/affiliate-programs"),
    (AffiliateProgramResource, "/admin/affiliate-programs/<int:program_id>"),
    (AffiliateLinkListResource, "/admin/affiliate-links"),
    (AffiliateLinkResource, "/admin/affiliate-links/<int:link_id>"),
    (AffiliateClickResource, "/admin/affiliate-clicks"),
    (AffiliateCommissionListResource, "/admin/affiliate-commissions"),
    (AffiliateCommissionImportResource, "/admin/affiliate-commissions/import"),
    (AffiliateCommissionStatusResource, "/admin/affiliate-commissions/<int:commission_id>/status"),
    (AffiliateDisclosureResource, "/admin/affiliate-disclosure"),
    (MediaKitResource, "/admin/media-kit"),
    (MediaKitPublishResource, "/admin/media-kit/publish"),
    (AudienceMetricListResource, "/admin/audience-metrics"),
    (AudienceMetricResource, "/admin/audience-metrics/<int:metric_id>"),
]
