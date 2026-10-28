"""Admin API for membership plans (/api/v1/admin/membership-plans…, Batch 10.1).

Every resource requires ``memberships.view``; the service checks ``memberships.manage``
(content, prices, included products) and ``memberships.publish`` (status changes).
"""

from __future__ import annotations

from flask import request
from flask_jwt_extended import current_user
from flask_restful import Resource

from ...auth.decorators import require_permission
from ...auth.permissions import Permission as P
from ...extensions import db
from ...services.memberships import billing, plans
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


MEMBERSHIP_ADMIN_ROUTES = [
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
