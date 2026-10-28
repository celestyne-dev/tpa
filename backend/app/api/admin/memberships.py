"""Admin API for membership plans (/api/v1/admin/membership-plans…, Batch 10.1).

Every plan resource requires ``memberships.view``; the service checks ``memberships.manage``
(content, prices, included products) and ``memberships.publish`` (status changes).

Batch 10.4: subscriptions, complimentary memberships and reports. The services check
``memberships.manage_subscriptions`` / ``memberships.view_reports`` themselves; read-only
subscriber access also works with ``memberships.view`` + ``customers.view``.
"""

from __future__ import annotations

from flask import request
from flask_jwt_extended import current_user
from flask_restful import Resource

from ...auth.decorators import require_any_permission, require_permission
from ...auth.permissions import Permission as P
from ...extensions import db, limiter
from ...services.memberships import admin as member_admin
from ...services.memberships import billing, plans, reports
from ...utils.errors import ValidationError
from ...utils.responses import success

VIEW = require_permission(P.MEMBERSHIPS_VIEW)


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object in the request body.")
    return data


def _detail(plan):
    return plans.plan_detail(plan, current_user)


class MembershipPlanListResource(Resource):
    @VIEW
    def get(self):
        return success(plans.list_plans(current_user))

    @VIEW
    def post(self):
        plan = plans.create_plan(_body(), current_user)
        db.session.commit()
        return success(_detail(plan), status=201)


class MembershipPlanResource(Resource):
    @VIEW
    def get(self, plan_id: str):
        return success(_detail(plans.get_plan(plan_id)))

    @VIEW
    def patch(self, plan_id: str):
        plan = plans.update_plan(plans.get_plan(plan_id), _body(), current_user)
        db.session.commit()
        return success(_detail(plan))


class MembershipPlanStatusResource(Resource):
    @VIEW
    def post(self, plan_id: str):
        body = _body()
        plan = plans.set_status(plans.get_plan(plan_id), body.get("status"), body, current_user)
        db.session.commit()
        return success(_detail(plan))


class MembershipPlanPricesResource(Resource):
    @VIEW
    def post(self, plan_id: str):
        plan = plans.get_plan(plan_id)
        plans.add_price(plan, _body(), current_user)
        db.session.commit()
        return success(_detail(plan), status=201)


class MembershipPlanPriceRemoveResource(Resource):
    @VIEW
    def post(self, plan_id: str, price_id: str):
        plan = plans.get_plan(plan_id)
        plans.remove_price(plan, price_id, _body(), current_user)
        db.session.commit()
        return success(_detail(plan))


class MembershipPlanAccessResource(Resource):
    @VIEW
    def put(self, plan_id: str):
        plan = plans.set_access(plans.get_plan(plan_id), _body(), current_user)
        db.session.commit()
        return success(_detail(plan))


class MembershipPlanProviderSyncResource(Resource):
    @VIEW
    def post(self, plan_id: str):
        plan = billing.sync_provider_plans(plans.get_plan(plan_id), _body(), current_user)
        db.session.commit()
        return success(_detail(plan))


class MembershipEligibleProductsResource(Resource):
    @VIEW
    def get(self):
        q = (request.args.get("q") or "")[:100]
        return success(plans.eligible_products(current_user, q))


def _page_args() -> dict:
    def to_int(name, default, low, high):
        raw = request.args.get(name)
        if raw in (None, ""):
            return default
        try:
            value = int(raw)
        except ValueError:
            raise ValidationError(details={name: ["Must be a number."]}) from None
        return max(low, min(high, value))

    args = {
        k: v for k, v in request.args.items() if k not in ("page", "page_size") and len(v) <= 120
    }
    args["page"] = to_int("page", 1, 1, 10000)
    args["page_size"] = to_int("page_size", 25, 1, 100)
    return args


SUBSCRIBERS = require_any_permission(
    P.MEMBERSHIPS_MANAGE_SUBSCRIPTIONS, P.MEMBERSHIPS_VIEW, P.MEMBERSHIPS_VIEW_REPORTS
)


class MembershipOverviewResource(Resource):
    @SUBSCRIBERS
    def get(self):
        return success(member_admin.overview(current_user))


class MembershipSubscriptionListResource(Resource):
    @SUBSCRIBERS
    def get(self):
        items, total = member_admin.list_subscriptions(_page_args(), current_user)
        return success(items, {"total": total, "can_manage": member_admin.can_manage(current_user)})


class MembershipSubscriptionResource(Resource):
    @SUBSCRIBERS
    def get(self, subscription_id: str):
        sub = member_admin.get_subscription(subscription_id)
        return success(member_admin.subscription_detail(sub, current_user))


def _subscription_action(func_name: str, rate: str = "30 per minute"):
    class _Action(Resource):
        method_decorators = {"post": [limiter.limit(rate)]}

        @require_permission(P.MEMBERSHIPS_MANAGE_SUBSCRIPTIONS)
        def post(self, subscription_id: str):
            sub = member_admin.get_subscription(subscription_id)
            result = getattr(member_admin, func_name)(sub, _body(), current_user)
            db.session.commit()
            sub = member_admin.get_subscription(subscription_id)
            data = {"subscription": member_admin.subscription_detail(sub, current_user)}
            if isinstance(result, dict):
                data["result"] = result
            return success(data)

    _Action.__name__ = f"MembershipSubscription_{func_name}"
    return _Action


class MembershipGrantListResource(Resource):
    @SUBSCRIBERS
    def get(self):
        items, total = member_admin.list_grants(_page_args(), current_user)
        return success(items, {"total": total})

    @require_permission(P.MEMBERSHIPS_MANAGE_SUBSCRIPTIONS)
    def post(self):
        grant = member_admin.create_grant(_body(), current_user)
        db.session.commit()
        return success(member_admin.grant_dict(grant), status=201)


class MembershipGrantRevokeResource(Resource):
    @require_permission(P.MEMBERSHIPS_MANAGE_SUBSCRIPTIONS)
    def post(self, grant_id: str):
        grant = member_admin.revoke_grant(member_admin.get_grant(grant_id), _body(), current_user)
        db.session.commit()
        return success(member_admin.grant_dict(grant))


class MembershipReportResource(Resource):
    @require_permission(P.MEMBERSHIPS_VIEW_REPORTS)
    def get(self):
        args = {k: request.args.get(k) for k in ("date_from", "date_to")}
        return success(reports.report(args, current_user))


class MembershipInclusionResource(Resource):
    @require_any_permission(P.PRODUCTS_VIEW, P.COURSES_VIEW, P.MEMBERSHIPS_VIEW)
    def get(self, product_id: int):
        return success(plans.plans_including(product_id))


MEMBERSHIP_ADMIN_ROUTES = [
    (MembershipOverviewResource, "/admin/membership-overview"),
    (MembershipSubscriptionListResource, "/admin/membership-subscriptions"),
    (MembershipSubscriptionResource, "/admin/membership-subscriptions/<string:subscription_id>"),
    (
        _subscription_action("reconcile_one", "10 per minute"),
        "/admin/membership-subscriptions/<string:subscription_id>/reconcile",
    ),
    (
        _subscription_action("cancel"),
        "/admin/membership-subscriptions/<string:subscription_id>/cancel",
    ),
    (
        _subscription_action("extend_grace"),
        "/admin/membership-subscriptions/<string:subscription_id>/extend-grace",
    ),
    (MembershipGrantListResource, "/admin/membership-grants"),
    (MembershipGrantRevokeResource, "/admin/membership-grants/<string:grant_id>/revoke"),
    (MembershipReportResource, "/admin/membership-reports"),
    (MembershipInclusionResource, "/admin/membership-inclusion/<int:product_id>"),
    (MembershipPlanListResource, "/admin/membership-plans"),
    (MembershipEligibleProductsResource, "/admin/membership-eligible-products"),
    (MembershipPlanResource, "/admin/membership-plans/<string:plan_id>"),
    (MembershipPlanStatusResource, "/admin/membership-plans/<string:plan_id>/status"),
    (MembershipPlanPricesResource, "/admin/membership-plans/<string:plan_id>/prices"),
    (
        MembershipPlanPriceRemoveResource,
        "/admin/membership-plans/<string:plan_id>/prices/<string:price_id>/remove",
    ),
    (MembershipPlanAccessResource, "/admin/membership-plans/<string:plan_id>/access"),
    (
        MembershipPlanProviderSyncResource,
        "/admin/membership-plans/<string:plan_id>/provider-sync",
    ),
]
