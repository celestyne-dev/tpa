"""Public page-view beacon (Batch 11.1): ``POST /api/v1/analytics/collect``.

Always answers 204 with no body (recorded or not), so it reveals nothing about other
visitors, customers or administrators and can't be used to probe. Rate limited per
client address; bodies over 2 KB are ignored.
"""

from __future__ import annotations

from flask import current_app, request
from flask_restful import Resource

from ..extensions import db, limiter
from ..services.analytics import tracking


class AnalyticsCollectResource(Resource):
    method_decorators = {
        "post": [limiter.limit(lambda: current_app.config["RATELIMIT_ANALYTICS_COLLECT"])]
    }

    def post(self):
        raw = request.get_data(cache=False, as_text=False)[: tracking.MAX_BODY + 1]
        result = tracking.collect(raw)
        if result.get("recorded"):
            db.session.commit()
        else:
            db.session.rollback()
        return "", 204, {"Cache-Control": "no-store"}


PUBLIC_ANALYTICS_ROUTES = [(AnalyticsCollectResource, "/analytics/collect")]
