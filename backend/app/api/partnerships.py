"""Public partnership endpoints: the inquiry form, the published media kit and the
affiliate redirect.

- Inquiries are rate-limited per IP and per address and checked for spam; a 201
  "received" answer is only given after the inquiry is committed.
- ``/go/<slug>`` redirects only to destinations stored on validated admin records
  (never to a URL taken from the request), so it cannot be used as an open redirect.
  Clicks are counted as daily aggregates; nothing identifies the visitor.
"""

from __future__ import annotations

from flask import current_app, redirect, request
from flask_restful import Resource

from ..extensions import db, limiter
from ..services.partnerships import affiliates, crm, media_kit
from ..utils.errors import NotFoundError, ValidationError
from ..utils.responses import success

RECEIVED = {
    "status": "received",
    "message": (
        "Thank you. Your inquiry has been received and our partnerships team will review it."
    ),
}


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object in the request body.")
    return data


def _email_key() -> str:
    body = request.get_json(silent=True)
    email = body.get("email") if isinstance(body, dict) else ""
    return "partnership-email:" + str(email or "").strip().lower()[:254]


_inquiry_limits = [
    limiter.limit(lambda: current_app.config["RATELIMIT_PARTNERSHIP_INQUIRY"]),
    limiter.limit("3 per hour", key_func=_email_key),
]


class PartnershipInquiryResource(Resource):
    method_decorators = {"post": _inquiry_limits}

    def post(self):
        inquiry = crm.submit_inquiry(_body(), ip=request.remote_addr)
        if inquiry is None:
            # Spam: don't tell bots they were caught, and don't claim anything was stored.
            return success({"status": "accepted", "message": "Thank you."}, status=202)
        db.session.commit()
        crm.notify_team(inquiry)
        db.session.commit()
        return success({**RECEIVED, "reference": f"PI-{inquiry.id:05d}"}, status=201)


class MediaKitPublicResource(Resource):
    def get(self):
        doc = media_kit.public_document()
        if doc is None:
            raise NotFoundError("The media kit has not been published yet.")
        return success(doc)


class AffiliateGoResource(Resource):
    method_decorators = {"get": [limiter.limit("120 per minute")]}

    def get(self, slug: str):
        url = affiliates.follow(slug, request.args.get("from"))
        if url is None:
            raise NotFoundError("This link is no longer available.")
        db.session.commit()
        response = redirect(url, code=302)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


PUBLIC_PARTNERSHIP_ROUTES = [
    (PartnershipInquiryResource, "/partnership-inquiries"),
    (MediaKitPublicResource, "/media-kit"),
    (AffiliateGoResource, "/go/<string:slug>"),
]
PARTNERSHIP_PRIVATE_PREFIXES = ("/api/v1/partnership-inquiries", "/api/v1/go/")
