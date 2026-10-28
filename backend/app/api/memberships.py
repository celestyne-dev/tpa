"""Public membership plans (/api/v1/memberships…, Batch 10.1).

Only published plans, their current prices and their published included courses and
resources are returned. Paid subscriptions are not available yet (``billing``).
"""

from __future__ import annotations

from flask_restful import Resource

from ..services.memberships import plans
from ..utils.responses import success


class MembershipPlansPublicResource(Resource):
    def get(self):
        return success(plans.published_plans())


class MembershipPlanPublicResource(Resource):
    def get(self, slug: str):
        return success(plans.published_plan(slug[:120]))


PUBLIC_MEMBERSHIP_ROUTES = [
    (MembershipPlansPublicResource, "/memberships"),
    (MembershipPlanPublicResource, "/memberships/<string:slug>"),
]
