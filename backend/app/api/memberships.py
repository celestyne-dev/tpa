"""Public membership plans (/api/v1/memberships…, Batch 10.1).

Only published plans, their current prices and their published included courses and
resources are returned. ``/account/membership``… (Batch 10.2): the signed-in customer's own
membership, test-mode checkout and server-side payment verification. Batch 10.3: cancel at
period end, resume, and a Paystack-hosted payment-method link.
"""

from __future__ import annotations

from flask import request
from flask_restful import Resource

from ..auth.customer_session import current_customer, require_customer
from ..extensions import db, limiter
from ..services.memberships import billing, lifecycle, plans
from ..utils.errors import ValidationError
from ..utils.responses import success


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object in the request body.")
    return data


class MembershipPlansPublicResource(Resource):
    def get(self):
        return success(plans.published_plans())


class MembershipPlanPublicResource(Resource):
    def get(self, slug: str):
        return success(plans.published_plan(slug[:120]))


class AccountMembershipResource(Resource):
    @require_customer
    def get(self):
        data = billing.customer_view(current_customer())
        db.session.commit()
        return success(data)


class AccountMembershipCheckoutResource(Resource):
    method_decorators = {"post": [limiter.limit("10 per minute")]}

    @require_customer
    def post(self):
        data = billing.start_checkout(current_customer(), _body())
        db.session.commit()
        return success(data, status=200 if data["resumed"] else 201)


class AccountMembershipVerifyResource(Resource):
    method_decorators = {"post": [limiter.limit("30 per minute")]}

    @require_customer
    def post(self):
        data = billing.verify_for_customer(current_customer(), _body().get("subscription_id"))
        db.session.commit()
        return success(data)


class AccountMembershipCancelResource(Resource):
    method_decorators = {"post": [limiter.limit("10 per minute")]}

    @require_customer
    def post(self):
        data = lifecycle.cancel(current_customer(), _body())
        db.session.commit()
        return success(data)


class AccountMembershipResumeResource(Resource):
    method_decorators = {"post": [limiter.limit("10 per minute")]}

    @require_customer
    def post(self):
        data = lifecycle.resume(current_customer(), _body())
        db.session.commit()
        return success(data)


class AccountMembershipPaymentMethodResource(Resource):
    method_decorators = {"post": [limiter.limit("10 per minute")]}

    @require_customer
    def post(self):
        data = lifecycle.payment_method_link(current_customer(), _body().get("subscription_id"))
        db.session.commit()
        return success(data)


PUBLIC_MEMBERSHIP_ROUTES = [
    (MembershipPlansPublicResource, "/memberships"),
    (MembershipPlanPublicResource, "/memberships/<string:slug>"),
    (AccountMembershipResource, "/account/membership"),
    (AccountMembershipCheckoutResource, "/account/membership/checkout"),
    (AccountMembershipVerifyResource, "/account/membership/verify"),
    (AccountMembershipCancelResource, "/account/membership/cancel"),
    (AccountMembershipResumeResource, "/account/membership/resume"),
    (AccountMembershipPaymentMethodResource, "/account/membership/payment-method"),
]
