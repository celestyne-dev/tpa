"""Admin API for subscribers, segments, suppressions, campaigns, templates, automations,
lead magnets and email settings. Each method checks its own permission."""

from __future__ import annotations

from datetime import UTC, datetime

from flask import Response, request
from flask_jwt_extended import current_user
from flask_restful import Resource
from sqlalchemy import select

from ...auth.decorators import require_any_permission, require_permission
from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import EmailMessage, EmailTemplate, SubscriberTag
from ...services.newsletter import automations, campaigns, lead_magnets, segments, subscribers
from ...services.newsletter import config as email_config
from ...services.newsletter.queue import retry_message
from ...services.newsletter.starter import ensure_automations, ensure_templates
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from ...utils.responses import success


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object in the request body.")
    return data


def _page_args() -> dict:
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
    args["page"] = to_int("page", 1, 1, 10000)
    args["page_size"] = to_int("page_size", 25, 1, 100)
    return args


def _paged(items, total, args, extra=None):
    meta = {"total": total, "page": args["page"], "page_size": args["page_size"]}
    meta.update(extra or {})
    return success(items, meta)


# ---- subscribers ------------------------------------------------------------------------


class SubscriberListResource(Resource):
    @require_permission(P.SUBSCRIBERS_VIEW)
    def get(self):
        args = _page_args()
        items, total, counts = subscribers.list_subscribers(args)
        return _paged(items, total, args, {"status_counts": counts})


class SubscriberResource(Resource):
    @require_permission(P.SUBSCRIBERS_VIEW)
    def get(self, subscriber_id: int):
        return success(
            subscribers.subscriber_dict(subscribers.get_subscriber(subscriber_id), detail=True)
        )


class SubscriberTagsResource(Resource):
    @require_permission(P.SUBSCRIBERS_MANAGE)
    def put(self, subscriber_id: int):
        subscriber = subscribers.set_tags(
            subscribers.get_subscriber(subscriber_id), _body().get("tags"), current_user
        )
        db.session.commit()
        return success(subscribers.subscriber_dict(subscriber, detail=True))


class SubscriberActionResource(Resource):
    @require_permission(P.SUBSCRIBERS_MANAGE)
    def post(self, subscriber_id: int, action: str):
        subscriber = subscribers.get_subscriber(subscriber_id)
        subscribers.admin_action(
            subscriber, action, request.get_json(silent=True) or {}, current_user
        )
        db.session.commit()
        if action == "erase":
            return success({"erased": True})
        return success(subscribers.subscriber_dict(subscriber, detail=True))


class SubscriberBulkTagResource(Resource):
    @require_permission(P.SUBSCRIBERS_MANAGE)
    def post(self):
        data = _body()
        count = subscribers.bulk_tag(
            data.get("ids"),
            str(data.get("tag") or ""),
            data.get("add", True) is not False,
            current_user,
        )
        db.session.commit()
        return success({"changed": count})


class SubscriberExportResource(Resource):
    @require_permission(P.SUBSCRIBERS_EXPORT)
    def get(self):
        args = _page_args()
        content = subscribers.export_csv(args, current_user)
        db.session.commit()
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
        return Response(
            content,
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="subscribers-{stamp}.csv"'},
        )


class SubscriberImportResource(Resource):
    @require_permission(P.SUBSCRIBERS_MANAGE)
    def post(self):
        data = _body()
        result = subscribers.import_csv(data.get("content"), data, current_user)
        db.session.commit()
        return success(result, status=201)


class SubscriberTagListResource(Resource):
    @require_permission(P.SUBSCRIBERS_VIEW)
    def get(self):
        tags = db.session.scalars(select(SubscriberTag).order_by(SubscriberTag.name))
        return success([subscribers.tag_dict(t) for t in tags])

    @require_permission(P.SUBSCRIBERS_MANAGE)
    def post(self):
        tag = subscribers.save_tag(_body())
        db.session.commit()
        return success(subscribers.tag_dict(tag), status=201)


class SubscriberTagResource(Resource):
    def _get(self, tag_id: int) -> SubscriberTag:
        tag = db.session.get(SubscriberTag, tag_id)
        if tag is None:
            raise NotFoundError()
        return tag

    @require_permission(P.SUBSCRIBERS_MANAGE)
    def patch(self, tag_id: int):
        tag = subscribers.save_tag(_body(), self._get(tag_id))
        db.session.commit()
        return success(subscribers.tag_dict(tag))

    @require_permission(P.SUBSCRIBERS_MANAGE)
    def delete(self, tag_id: int):
        db.session.delete(self._get(tag_id))
        db.session.commit()
        return success({"deleted": True})


class SegmentListResource(Resource):
    @require_any_permission(P.SUBSCRIBERS_VIEW, P.NEWSLETTERS_VIEW)
    def get(self):
        return success(segments.list_segments())

    @require_permission(P.SUBSCRIBERS_MANAGE)
    def post(self):
        segment = segments.save_segment(_body(), current_user)
        db.session.commit()
        return success(segments.segment_dict(segment), status=201)


class SegmentPreviewResource(Resource):
    @require_any_permission(P.SUBSCRIBERS_VIEW, P.NEWSLETTERS_VIEW)
    def post(self):
        rules = segments.validate_rules(_body().get("rules") or [])
        return success({"count": len(segments.resolve(rules))})


class SegmentResource(Resource):
    @require_any_permission(P.SUBSCRIBERS_VIEW, P.NEWSLETTERS_VIEW)
    def get(self, segment_id: int):
        return success(segments.segment_dict(segments.get_segment(segment_id)))

    @require_permission(P.SUBSCRIBERS_MANAGE)
    def patch(self, segment_id: int):
        segment = segments.save_segment(_body(), current_user, segments.get_segment(segment_id))
        db.session.commit()
        return success(segments.segment_dict(segment))

    @require_permission(P.SUBSCRIBERS_MANAGE)
    def delete(self, segment_id: int):
        segments.delete_segment(segments.get_segment(segment_id))
        db.session.commit()
        return success({"deleted": True})


class SuppressionListResource(Resource):
    @require_permission(P.SUBSCRIBERS_VIEW)
    def get(self):
        args = _page_args()
        items, total = subscribers.list_suppressions(args)
        return _paged(items, total, args)

    @require_permission(P.SUBSCRIBERS_MANAGE)
    def post(self):
        subscribers.add_suppression(_body(), current_user)
        db.session.commit()
        return success({"suppressed": True}, status=201)


class SuppressionResource(Resource):
    @require_permission(P.SUBSCRIBERS_MANAGE)
    def delete(self, suppression_id: int):
        subscribers.remove_suppression(suppression_id, current_user)
        db.session.commit()
        return success({"deleted": True})


# ---- campaigns --------------------------------------------------------------------------


class CampaignListResource(Resource):
    @require_permission(P.NEWSLETTERS_VIEW)
    def get(self):
        args = _page_args()
        items, total = campaigns.list_campaigns(args)
        return _paged(
            items,
            total,
            args,
            {"sending_mode": email_config.sending_mode(), "readiness": email_config.readiness()},
        )

    @require_permission(P.NEWSLETTERS_CREATE)
    def post(self):
        campaign = campaigns.create_campaign(_body(), current_user)
        db.session.commit()
        return success(campaigns.campaign_dict(campaign, detail=True), status=201)


class CampaignResource(Resource):
    @require_permission(P.NEWSLETTERS_VIEW)
    def get(self, campaign_id: int):
        return success(campaigns.campaign_dict(campaigns.get_campaign(campaign_id), detail=True))

    @require_permission(P.NEWSLETTERS_EDIT)
    def patch(self, campaign_id: int):
        campaign = campaigns.update_campaign(
            campaigns.get_campaign(campaign_id), _body(), current_user
        )
        db.session.commit()
        return success(campaigns.campaign_dict(campaign, detail=True))

    @require_permission(P.NEWSLETTERS_EDIT)
    def delete(self, campaign_id: int):
        campaigns.delete_campaign(campaigns.get_campaign(campaign_id), current_user)
        db.session.commit()
        return success({"deleted": True})


_ACTIONS = {
    "duplicate": P.NEWSLETTERS_CREATE,
    "approve": P.NEWSLETTERS_PUBLISH,
    "withdraw-approval": P.NEWSLETTERS_PUBLISH,
    "schedule": P.NEWSLETTERS_SCHEDULE,
    "unschedule": P.NEWSLETTERS_SCHEDULE,
    "send": P.NEWSLETTERS_SEND,
    "cancel": P.NEWSLETTERS_SEND,
    "test": P.NEWSLETTERS_EDIT,
}


class CampaignActionResource(Resource):
    @require_permission(P.NEWSLETTERS_VIEW)
    def post(self, campaign_id: int, action: str):
        from ...auth.rbac import has_permissions
        from ...utils.errors import ForbiddenError

        needed = _ACTIONS.get(action)
        if needed is None:
            raise NotFoundError()
        if action == "cancel" and not has_permissions(current_user, needed):
            needed = P.NEWSLETTERS_SCHEDULE  # schedulers may cancel a schedule
        if not has_permissions(current_user, needed):
            raise ForbiddenError()
        campaign = campaigns.get_campaign(campaign_id)
        data = request.get_json(silent=True) or {}
        extra = {}
        if action == "duplicate":
            campaign = campaigns.duplicate_campaign(campaign, current_user)
        elif action == "approve":
            campaigns.approve(campaign, current_user)
        elif action == "withdraw-approval":
            campaigns.withdraw_approval(campaign, current_user)
        elif action == "schedule":
            campaigns.schedule(campaign, data, current_user)
        elif action == "unschedule":
            campaigns.unschedule(campaign, current_user)
        elif action == "send":
            campaigns.send_now(campaign, current_user)
        elif action == "cancel":
            if campaign.status == "sending" and not has_permissions(
                current_user, P.NEWSLETTERS_SEND
            ):
                raise ForbiddenError()
            extra = campaigns.cancel(campaign, current_user)
        elif action == "test":
            extra = campaigns.send_test(campaign, data, current_user)
        db.session.commit()
        return success({"campaign": campaigns.campaign_dict(campaign, detail=True), **extra})


class CampaignPreviewResource(Resource):
    @require_permission(P.NEWSLETTERS_VIEW)
    def post(self, campaign_id: int):
        rendered = campaigns.preview(
            campaigns.get_campaign(campaign_id), request.get_json(silent=True) or None
        )
        return success(rendered)


class CampaignReportResource(Resource):
    @require_permission(P.NEWSLETTERS_REPORTS)
    def get(self, campaign_id: int):
        return success(campaigns.report(campaigns.get_campaign(campaign_id)))


class CampaignMessagesResource(Resource):
    @require_permission(P.NEWSLETTERS_REPORTS)
    def get(self, campaign_id: int):
        args = _page_args()
        items, total = campaigns.messages(campaigns.get_campaign(campaign_id), args)
        return _paged(items, total, args)


class MessageRetryResource(Resource):
    @require_permission(P.NEWSLETTERS_SEND)
    def post(self, message_id: int):
        message = db.session.get(EmailMessage, message_id)
        if message is None:
            raise NotFoundError()
        retry_message(message)
        db.session.commit()
        return success(campaigns.message_dict(message))


# ---- templates --------------------------------------------------------------------------


class TemplateListResource(Resource):
    @require_any_permission(P.NEWSLETTERS_VIEW, P.EMAIL_TEMPLATES_MANAGE)
    def get(self):
        rows = db.session.scalars(
            select(EmailTemplate).order_by(EmailTemplate.is_starter.desc(), EmailTemplate.name)
        )
        return success([campaigns.template_dict(t) for t in rows])

    @require_permission(P.EMAIL_TEMPLATES_MANAGE)
    def post(self):
        template = campaigns.save_template(_body(), current_user)
        db.session.commit()
        return success(campaigns.template_dict(template), status=201)


class TemplateStartersResource(Resource):
    @require_any_permission(P.EMAIL_TEMPLATES_MANAGE, P.EMAIL_AUTOMATIONS_MANAGE)
    def post(self):
        created = {"templates": ensure_templates(), "automations": ensure_automations()}
        db.session.commit()
        return success(created)


class TemplateResource(Resource):
    def _get(self, template_id: int) -> EmailTemplate:
        template = db.session.get(EmailTemplate, template_id)
        if template is None:
            raise NotFoundError()
        return template

    @require_any_permission(P.NEWSLETTERS_VIEW, P.EMAIL_TEMPLATES_MANAGE)
    def get(self, template_id: int):
        return success(campaigns.template_dict(self._get(template_id)))

    @require_permission(P.EMAIL_TEMPLATES_MANAGE)
    def patch(self, template_id: int):
        template = campaigns.save_template(_body(), current_user, self._get(template_id))
        db.session.commit()
        return success(campaigns.template_dict(template))

    @require_permission(P.EMAIL_TEMPLATES_MANAGE)
    def delete(self, template_id: int):
        template = self._get(template_id)
        if template.is_starter:
            raise ConflictError("Starter templates can be edited but not deleted.")
        db.session.delete(template)
        db.session.commit()
        return success({"deleted": True})


# ---- automations ------------------------------------------------------------------------


class AutomationListResource(Resource):
    @require_any_permission(P.EMAIL_AUTOMATIONS_MANAGE, P.NEWSLETTERS_VIEW)
    def get(self):
        return success(automations.list_automations(), {"triggers": automations.triggers()})


class AutomationResource(Resource):
    @require_any_permission(P.EMAIL_AUTOMATIONS_MANAGE, P.NEWSLETTERS_VIEW)
    def get(self, automation_id: int):
        return success(
            automations.automation_dict(automations.get_automation(automation_id), detail=True)
        )

    @require_permission(P.EMAIL_AUTOMATIONS_MANAGE)
    def patch(self, automation_id: int):
        automation = automations.update_automation(
            automations.get_automation(automation_id), _body(), current_user
        )
        db.session.commit()
        return success(automations.automation_dict(automation, detail=True))


class AutomationStepsResource(Resource):
    @require_permission(P.EMAIL_AUTOMATIONS_MANAGE)
    def put(self, automation_id: int):
        automation = automations.replace_steps(
            automations.get_automation(automation_id), _body().get("steps"), current_user
        )
        db.session.commit()
        return success(automations.automation_dict(automation, detail=True))


# ---- lead magnets -----------------------------------------------------------------------


class LeadMagnetListResource(Resource):
    @require_permission(P.LEAD_MAGNETS_MANAGE)
    def get(self):
        return success(lead_magnets.list_magnets())

    @require_permission(P.LEAD_MAGNETS_MANAGE)
    def post(self):
        magnet = lead_magnets.save_magnet(_body(), current_user)
        db.session.commit()
        return success(lead_magnets.magnet_dict(magnet, admin=True), status=201)


class LeadMagnetAdminResource(Resource):
    @require_permission(P.LEAD_MAGNETS_MANAGE)
    def get(self, magnet_id: int):
        return success(lead_magnets.magnet_dict(lead_magnets.get_magnet(magnet_id), admin=True))

    @require_permission(P.LEAD_MAGNETS_MANAGE)
    def patch(self, magnet_id: int):
        magnet = lead_magnets.save_magnet(_body(), current_user, lead_magnets.get_magnet(magnet_id))
        db.session.commit()
        return success(lead_magnets.magnet_dict(magnet, admin=True))

    @require_permission(P.LEAD_MAGNETS_MANAGE)
    def delete(self, magnet_id: int):
        lead_magnets.delete_magnet(lead_magnets.get_magnet(magnet_id), current_user)
        db.session.commit()
        return success({"deleted": True})


# ---- settings ---------------------------------------------------------------------------


class EmailSettingsResource(Resource):
    @require_permission(P.EMAIL_SETTINGS_MANAGE)
    def get(self):
        return success(email_config.admin_view())

    @require_permission(P.EMAIL_SETTINGS_MANAGE)
    def patch(self):
        result = email_config.update_settings(_body(), current_user)
        db.session.commit()
        return success({**email_config.admin_view(), **result})


class EmailAttestationResource(Resource):
    @require_permission(P.EMAIL_SETTINGS_MANAGE)
    def put(self):
        email_config.update_attestation(_body(), current_user)
        db.session.commit()
        return success(email_config.admin_view())


NEWSLETTER_ROUTES = [
    (SubscriberListResource, "/admin/subscribers"),
    (SubscriberExportResource, "/admin/subscribers/export"),
    (SubscriberImportResource, "/admin/subscribers/import"),
    (SubscriberBulkTagResource, "/admin/subscribers/bulk-tag"),
    (SubscriberResource, "/admin/subscribers/<int:subscriber_id>"),
    (SubscriberTagsResource, "/admin/subscribers/<int:subscriber_id>/tags"),
    (SubscriberActionResource, "/admin/subscribers/<int:subscriber_id>/<string:action>"),
    (SubscriberTagListResource, "/admin/subscriber-tags"),
    (SubscriberTagResource, "/admin/subscriber-tags/<int:tag_id>"),
    (SegmentListResource, "/admin/subscriber-segments"),
    (SegmentPreviewResource, "/admin/subscriber-segments/preview"),
    (SegmentResource, "/admin/subscriber-segments/<int:segment_id>"),
    (SuppressionListResource, "/admin/email-suppressions"),
    (SuppressionResource, "/admin/email-suppressions/<int:suppression_id>"),
    (CampaignListResource, "/admin/newsletters"),
    (CampaignResource, "/admin/newsletters/<int:campaign_id>"),
    (CampaignPreviewResource, "/admin/newsletters/<int:campaign_id>/preview"),
    (CampaignReportResource, "/admin/newsletters/<int:campaign_id>/report"),
    (CampaignMessagesResource, "/admin/newsletters/<int:campaign_id>/messages"),
    (CampaignActionResource, "/admin/newsletters/<int:campaign_id>/<string:action>"),
    (MessageRetryResource, "/admin/email-messages/<int:message_id>/retry"),
    (TemplateListResource, "/admin/email-templates"),
    (TemplateStartersResource, "/admin/email-templates/starters"),
    (TemplateResource, "/admin/email-templates/<int:template_id>"),
    (AutomationListResource, "/admin/email-automations"),
    (AutomationResource, "/admin/email-automations/<int:automation_id>"),
    (AutomationStepsResource, "/admin/email-automations/<int:automation_id>/steps"),
    (LeadMagnetListResource, "/admin/lead-magnets"),
    (LeadMagnetAdminResource, "/admin/lead-magnets/<int:magnet_id>"),
    (EmailSettingsResource, "/admin/email-settings"),
    (EmailAttestationResource, "/admin/email-settings/attestation"),
]
