"""Public newsletter, lead magnet and provider-feedback endpoints.

- Cookieless: subscribers authenticate with signed links, never a session.
- Responses never reveal whether an address is subscribed (signup and resource claims
  always return the same "check your email" result).
- Signup and claims are rate-limited per IP and per address, with spam checks in the
  service layer.
- One-click unsubscribe follows RFC 8058 (POST with ``List-Unsubscribe=One-Click``).
- Provider feedback (bounces, complaints, deliveries) must be HMAC-signed.
"""

from __future__ import annotations

import hmac
import time

from flask import Response, current_app, request
from flask_restful import Resource

from ..extensions import db, limiter
from ..services.newsletter import config as email_config
from ..services.newsletter import lead_magnets, subscribers, tokens
from ..services.newsletter.queue import process_feedback
from ..utils.errors import AuthenticationError, NotFoundError, ValidationError
from ..utils.responses import success

CHECK_EMAIL = {
    "status": "check_email",
    "message": "Thank you. Please check your inbox for an email from us to continue.",
}


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object in the request body.")
    return data


def _email_key() -> str:
    body = request.get_json(silent=True)
    email = body.get("email") if isinstance(body, dict) else ""
    return "newsletter-email:" + tokens.normalise_email(str(email or ""))[:254]


_signup_limits = [
    limiter.limit(lambda: current_app.config["RATELIMIT_NEWSLETTER_SIGNUP"]),
    limiter.limit("3 per hour", key_func=_email_key),
]


class NewsletterStatusResource(Resource):
    def get(self):
        return success(email_config.public_status())


class NewsletterSubscribeResource(Resource):
    method_decorators = {"post": _signup_limits}

    def post(self):
        subscribers.subscribe(_body(), ip=request.remote_addr)
        db.session.commit()
        return success(CHECK_EMAIL, status=202)


class NewsletterConfirmResource(Resource):
    method_decorators = {"post": [limiter.limit("30 per minute")]}

    def post(self):
        subscriber = subscribers.confirm(str(_body().get("token") or ""))
        db.session.commit()
        return success(
            {"status": "subscribed", "preferences_token": tokens.manage_token(subscriber)}
        )


def _manage() -> subscribers.Subscriber:
    return subscribers.from_manage_token(str(_body().get("token") or ""))


class NewsletterPreferencesResource(Resource):
    method_decorators = [limiter.limit("60 per minute")]

    def post(self):  # look up (token in the body, not the URL)
        return success(subscribers.preferences_view(_manage()))

    def put(self):
        data = _body()
        subscriber = subscribers.update_preferences(_manage(), data)
        db.session.commit()
        return success(subscribers.preferences_view(subscriber))


class NewsletterUnsubscribeResource(Resource):
    method_decorators = [limiter.limit("30 per minute")]

    def post(self):
        data = _body()
        subscriber = subscribers.unsubscribe(
            _manage(),
            reason=str(data.get("reason") or ""),
            via="preferences_page",
            campaign=str(data.get("campaign") or "")[:32],
        )
        db.session.commit()
        return success(
            {"status": "unsubscribed", "email": subscribers.mask_email(subscriber.email)}
        )


class NewsletterOneClickResource(Resource):
    """RFC 8058 one-click unsubscribe, POSTed by mail providers from the List-Unsubscribe
    header. Authenticated by the signed token; no cookies, no Origin header."""

    method_decorators = [limiter.limit("60 per minute")]

    def post(self):
        try:
            subscriber = subscribers.from_manage_token(request.args.get("token", ""))
        except NotFoundError:
            return Response(status=200)  # never reveal anything; nothing to do
        subscribers.unsubscribe(
            subscriber, via="one_click", campaign=(request.args.get("c") or "")[:32]
        )
        db.session.commit()
        return Response(status=200)


class NewsletterEraseResource(Resource):
    method_decorators = [limiter.limit("10 per minute")]

    def post(self):
        subscriber = _manage()
        subscribers.erase(subscriber, via="self")
        db.session.commit()
        return success({"status": "erased"})


class LeadMagnetResource(Resource):
    def get(self, slug: str):
        info = lead_magnets.public_info(slug)
        if info is None:
            raise NotFoundError()
        return success(info)


class LeadMagnetClaimResource(Resource):
    method_decorators = {"post": _signup_limits}

    def post(self, slug: str):
        lead_magnets.claim(slug, _body(), ip=request.remote_addr)
        db.session.commit()
        return success(CHECK_EMAIL, status=202)


class LeadMagnetAccessResource(Resource):
    method_decorators = [limiter.limit("60 per minute")]

    def post(self):
        return success(lead_magnets.access(str(_body().get("token") or "")))


class LeadMagnetDownloadAuthorizeResource(Resource):
    method_decorators = [limiter.limit("30 per minute")]

    def post(self):
        data = _body()
        result = lead_magnets.authorize_download(
            str(data.get("token") or ""), str(data.get("file_id") or "")
        )
        db.session.commit()
        return success(result)


class LeadMagnetDownloadResource(Resource):
    method_decorators = [limiter.limit(lambda: current_app.config["RATELIMIT_DOWNLOADS"])]

    def get(self, signed: str):
        return lead_magnets.serve(signed)


class EmailFeedbackResource(Resource):
    """Normalised bounce/complaint/delivery feedback from the delivery provider (or a small
    adapter in front of it). Body: {"events": [...]} signed with EMAIL_FEEDBACK_SECRET:
    X-TPA-Timestamp: <unix seconds>, X-TPA-Signature: hex HMAC-SHA256 of
    "<timestamp>.<raw body>"."""

    method_decorators = [limiter.limit("120 per minute")]

    def post(self):
        if not current_app.config.get("EMAIL_FEEDBACK_SECRET"):
            raise NotFoundError()
        raw = request.get_data(cache=True)
        stamp = request.headers.get("X-TPA-Timestamp", "")
        signature = request.headers.get("X-TPA-Signature", "")
        if not stamp.isdigit() or abs(time.time() - int(stamp)) > 300:
            raise AuthenticationError("Stale or missing timestamp.")
        expected = tokens.feedback_signature(stamp.encode() + b"." + raw)
        if not hmac.compare_digest(expected, signature):
            raise AuthenticationError("Invalid signature.")
        data = request.get_json(silent=True) or {}
        events = data.get("events") if isinstance(data, dict) else None
        if not isinstance(events, list):
            raise ValidationError(details={"events": ["Send a list of events."]})
        result = process_feedback(events)
        db.session.commit()
        return success(result)


PUBLIC_NEWSLETTER_ROUTES = [
    (NewsletterStatusResource, "/newsletter/status"),
    (NewsletterSubscribeResource, "/newsletter/subscribe"),
    (NewsletterConfirmResource, "/newsletter/confirm"),
    (NewsletterPreferencesResource, "/newsletter/preferences"),
    (NewsletterUnsubscribeResource, "/newsletter/unsubscribe"),
    (NewsletterOneClickResource, "/newsletter/unsubscribe/one-click"),
    (NewsletterEraseResource, "/newsletter/erase"),
    (LeadMagnetResource, "/lead-magnets/<string:slug>"),
    (LeadMagnetClaimResource, "/lead-magnets/<string:slug>/claim"),
    (LeadMagnetAccessResource, "/lead-magnets/access"),
    (LeadMagnetDownloadAuthorizeResource, "/lead-magnets/access/download"),
    (LeadMagnetDownloadResource, "/lead-magnets/download/<string:signed>"),
    (EmailFeedbackResource, "/email/feedback"),
]

# Never cached, never indexed (signed links and personal data).
NEWSLETTER_PRIVATE_PREFIXES = ("/api/v1/newsletter/", "/api/v1/lead-magnets/", "/api/v1/email/")
