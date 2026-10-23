"""Public storefront, customer account, checkout, download and webhook endpoints.

- Catalogue endpoints are public, cacheable GETs (used by the prerenderer).
- Account, checkout and library endpoints need a customer session; mutations
  also need the customer CSRF token and a trusted Origin.
- The Paystack webhook authenticates with the provider's HMAC signature only.
"""

from __future__ import annotations

from flask import current_app, jsonify, request
from flask_restful import Resource

from ..auth.customer_session import (
    CustomerAuthRequired,
    clear_cookies,
    current_customer,
    current_session,
    require_customer,
    start_session,
)
from ..extensions import db, limiter
from ..models import Customer, Product
from ..payments.config import checkout_available_for, public_status
from ..services import audit_service
from ..services.commerce import catalogue, checkout, customers, downloads, payments
from ..services.commerce import entitlements as ent_service
from ..utils.errors import AuthenticationError, NotFoundError, ValidationError
from ..utils.responses import success
from ._validation import require_slug


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object in the request body.")
    return data


def _arg(name: str, max_len: int = 80) -> str | None:
    value = request.args.get(name)
    if value is None or value == "":
        return None
    if len(value) > max_len:
        raise ValidationError(details={name: ["Too long."]})
    return value


# ---- catalogue --------------------------------------------------------------------------


class ShopProductListResource(Resource):
    def get(self):
        sort = _arg("sort", 20)
        if sort and sort not in ("featured", "newest", "title", "price_asc", "price_desc"):
            raise ValidationError(details={"sort": ["Unknown sort order."]})
        args = {
            "category": _arg("category"),
            "collection": _arg("collection"),
            "type": _arg("type", 40),
            "q": _arg("q", 100),
            "sort": sort,
            "currency": (_arg("currency", 3) or "").upper() or None,
            "featured": request.args.get("featured") in ("1", "true"),
        }
        items = catalogue.list_public(args)
        return success(
            items,
            {
                "total": len(items),
                "display_currencies": catalogue.display_currencies(),
                "categories": catalogue.public_categories(),
                "collections": [
                    {"slug": c["slug"], "name": c["name"]}
                    for c in catalogue.public_collections()
                    if c["product_count"]
                ],
            },
        )


class ShopProductResource(Resource):
    def get(self, slug: str):
        require_slug(slug, "Product")
        data = catalogue.get_public(slug)
        if data is None:
            raise NotFoundError(f"Product '{slug}' was not found.")
        return success(data)


class ShopCollectionListResource(Resource):
    def get(self):
        return success([c for c in catalogue.public_collections() if c["product_count"]])


class ShopCollectionResource(Resource):
    def get(self, slug: str):
        require_slug(slug, "Collection")
        data = catalogue.get_collection(slug)
        if data is None:
            raise NotFoundError(f"Collection '{slug}' was not found.")
        return success(data)


class ShopStatusResource(Resource):
    def get(self):
        return success(public_status(current_customer()))


class CartQuoteResource(Resource):
    method_decorators = {"post": [limiter.limit("60 per minute")]}

    def post(self):
        data = _body()
        return success(checkout.quote(data.get("items"), data.get("currency"), current_customer()))


# ---- customer accounts ------------------------------------------------------------------


def _email_key() -> str:
    body = request.get_json(silent=True)
    email = body.get("email") if isinstance(body, dict) else ""
    return "customer-email:" + customers.normalise_email(str(email or ""))[:254]


def _session_payload(customer: Customer) -> dict:
    return {"customer": customers.profile(customer)}


class AccountRegisterResource(Resource):
    method_decorators = {
        "post": [limiter.limit(lambda: current_app.config["RATELIMIT_CUSTOMER_REGISTER"])]
    }

    def post(self):
        customer, created = customers.register(_body())
        db.session.commit()
        if not created:
            # Same response as a new registration: no account enumeration.
            return success({"registered": True, "signed_in": False}, status=201)
        response = jsonify(
            {"data": {"registered": True, "signed_in": True, **_session_payload(customer)}}
        )
        start_session(customer, response)
        db.session.commit()
        response.status_code = 201
        return response


class AccountLoginResource(Resource):
    method_decorators = {
        "post": [
            limiter.limit(lambda: current_app.config["RATELIMIT_LOGIN"]),
            limiter.limit("10 per hour", key_func=_email_key),
        ]
    }

    def post(self):
        data = _body()
        customer = customers.authenticate(
            str(data.get("email") or ""), str(data.get("password") or "")
        )
        if customer is None:
            audit_service.record("customer.login_failed", "customer")
            db.session.commit()
            raise AuthenticationError(customers.GENERIC_LOGIN_ERROR)
        response = jsonify({"data": _session_payload(customer)})
        start_session(customer, response)
        audit_service.record("customer.login", "customer", customer.id)
        db.session.commit()
        return response


class AccountLogoutResource(Resource):
    def post(self):
        session = current_session()
        if session is not None:
            from datetime import UTC, datetime

            session.revoked_at = datetime.now(UTC)
            db.session.commit()
        response = jsonify({"data": {"signed_out": True}})
        clear_cookies(response)
        return response


class AccountMeResource(Resource):
    def get(self):
        customer = current_customer()
        if customer is None:
            raise CustomerAuthRequired()
        db.session.commit()  # persists last_seen updates
        return success(_session_payload(customer))

    @require_customer
    def patch(self):
        customer = customers.update_profile(current_customer(), _body())
        db.session.commit()
        return success(_session_payload(customer))


_sensitive = [limiter.limit(lambda: current_app.config["RATELIMIT_SENSITIVE"])]


class AccountPasswordResource(Resource):
    method_decorators = {"post": _sensitive}

    @require_customer
    def post(self):
        data = _body()
        session = current_session()
        customers.change_password(
            session.customer, data.get("current_password"), data.get("new_password"), session.id
        )
        db.session.commit()
        return success({"changed": True})


class AccountVerifyEmailResource(Resource):
    method_decorators = {"post": _sensitive}

    def post(self):
        customer = customers.verify_email(_body().get("token"))
        db.session.commit()
        return success({"verified": True, "email": customer.email})


class AccountResendVerificationResource(Resource):
    method_decorators = {"post": [limiter.limit("3 per minute;10 per hour")]}

    @require_customer
    def post(self):
        customer = current_customer()
        if customer.email_verified_at is not None:
            return success({"sent": False, "already_verified": True})
        status = customers.send_verification(customer)
        db.session.commit()
        return success(
            {"sent": status in ("sent", "development_console", "memory"), "delivery": status}
        )


class AccountPasswordResetRequestResource(Resource):
    method_decorators = {
        "post": [
            limiter.limit("5 per minute;20 per hour"),
            limiter.limit("5 per hour", key_func=_email_key),
        ]
    }

    def post(self):
        customers.request_password_reset(str(_body().get("email") or ""))
        db.session.commit()
        return success({"message": "If an account exists for that email, we've sent a reset link."})


class AccountPasswordResetCompleteResource(Resource):
    method_decorators = {"post": _sensitive}

    def post(self):
        data = _body()
        customers.complete_password_reset(data.get("token"), data.get("password"))
        db.session.commit()
        response = jsonify({"data": {"reset": True}})
        clear_cookies(response)
        return response


class AccountExportResource(Resource):
    method_decorators = {"get": [limiter.limit("5 per hour")]}

    @require_customer
    def get(self):
        return success(customers.export_data(current_customer()))


class AccountDeleteResource(Resource):
    method_decorators = {"post": _sensitive}

    @require_customer
    def post(self):
        result = customers.request_deletion(current_customer(), str(_body().get("password") or ""))
        db.session.commit()
        response = jsonify({"data": result})
        clear_cookies(response)
        return response


class AccountOrderListResource(Resource):
    @require_customer
    def get(self):
        from sqlalchemy import select

        from ..models import Order

        customer = current_customer()
        orders = db.session.scalars(
            select(Order).where(Order.customer_id == customer.id).order_by(Order.created_at.desc())
        ).all()
        return success([checkout.order_public_dict(o) for o in orders])


class AccountOrderResource(Resource):
    @require_customer
    def get(self, public_id: str):
        from sqlalchemy import select

        from ..models import Receipt

        order = checkout.customer_order(current_customer(), public_id)
        data = checkout.order_public_dict(order)
        data["receipt"] = payments.receipt_dict(
            db.session.scalar(select(Receipt).where(Receipt.order_id == order.id))
        )
        return success(data)


class AccountLibraryResource(Resource):
    @require_customer
    def get(self):
        return success(ent_service.library(current_customer()))


class AccountDownloadResource(Resource):
    method_decorators = {"post": [limiter.limit(lambda: current_app.config["RATELIMIT_DOWNLOADS"])]}

    @require_customer
    def post(self, entitlement_id: int):
        version_id = _body().get("version_id")
        if not isinstance(version_id, int) or isinstance(version_id, bool):
            raise ValidationError(details={"version_id": ["Choose a file to download."]})
        result = downloads.authorize(current_customer(), entitlement_id, version_id)
        db.session.commit()
        return success(result)


class FreeClaimResource(Resource):
    method_decorators = {"post": [limiter.limit("10 per minute")]}

    @require_customer
    def post(self):
        from sqlalchemy import select

        public_id = _body().get("product_id")
        product = (
            db.session.scalar(select(Product).where(Product.public_id == public_id))
            if isinstance(public_id, str) and len(public_id) <= 32
            else None
        )
        if product is None or product.status != "published":
            raise NotFoundError("This resource was not found.")
        customer = current_customer()
        entitlement, created = ent_service.claim_free(customer, product)
        db.session.commit()
        if created:
            from ..services.commerce import emails

            emails.send(
                "download_instructions",
                customer.email,
                {"name": customer.display_name, "products": [product.title]},
                customer=customer,
            )
            db.session.commit()
        return success(
            {"entitlement_id": entitlement.id, "created": created}, status=201 if created else 200
        )


class DownloadResource(Resource):
    method_decorators = {"get": [limiter.limit(lambda: current_app.config["RATELIMIT_DOWNLOADS"])]}

    def get(self, token: str):
        return downloads.serve(token, current_customer())


# ---- checkout ---------------------------------------------------------------------------


class CheckoutResource(Resource):
    method_decorators = {"post": [limiter.limit(lambda: current_app.config["RATELIMIT_CHECKOUT"])]}

    @require_customer
    def post(self):
        order, url = checkout.create_order(current_customer(), _body())
        db.session.refresh(order)
        return success(
            {"order": checkout.order_public_dict(order), "authorization_url": url}, status=201
        )


class CheckoutOrderResource(Resource):
    @require_customer
    def get(self, public_id: str):
        return success(
            checkout.order_public_dict(checkout.customer_order(current_customer(), public_id))
        )


class CheckoutVerifyResource(Resource):
    method_decorators = {"post": [limiter.limit("20 per minute")]}

    @require_customer
    def post(self, public_id: str):
        order = checkout.customer_order(current_customer(), public_id)
        outcome = payments.verify_order(order, "customer_return")
        db.session.refresh(order)
        return success({"outcome": outcome, "order": checkout.order_public_dict(order)})


class CheckoutRetryResource(Resource):
    method_decorators = {"post": [limiter.limit(lambda: current_app.config["RATELIMIT_CHECKOUT"])]}

    @require_customer
    def post(self, public_id: str):
        customer = current_customer()
        order = checkout.customer_order(customer, public_id)
        outcome = payments.verify_order(order, "customer_retry")
        if outcome in ("paid", "already_paid"):
            db.session.refresh(order)
            return success({"order": checkout.order_public_dict(order), "authorization_url": None})
        allowed, reason = checkout_available_for(customer)
        if not allowed:
            raise checkout.CheckoutClosedError(reason)
        url = checkout.start_payment(order)
        db.session.refresh(order)
        return success({"order": checkout.order_public_dict(order), "authorization_url": url})


class CheckoutCancelResource(Resource):
    @require_customer
    def post(self, public_id: str):
        order = checkout.customer_order(current_customer(), public_id)
        checkout.cancel_unpaid(order, "customer")
        db.session.commit()
        return success(checkout.order_public_dict(order))


class PaystackWebhookResource(Resource):
    def post(self):
        raw = request.get_data(cache=True)
        headers = {k.lower(): v for k, v in request.headers.items()}
        result = payments.handle_webhook("paystack", raw, headers)
        return success(result)


PUBLIC_COMMERCE_ROUTES = [
    (ShopProductListResource, "/shop/products"),
    (ShopProductResource, "/shop/products/<string:slug>"),
    (ShopCollectionListResource, "/shop/collections"),
    (ShopCollectionResource, "/shop/collections/<string:slug>"),
    (ShopStatusResource, "/shop/status"),
    (CartQuoteResource, "/cart/quote"),
    (AccountRegisterResource, "/account/register"),
    (AccountLoginResource, "/account/login"),
    (AccountLogoutResource, "/account/logout"),
    (AccountMeResource, "/account/me"),
    (AccountPasswordResource, "/account/password"),
    (AccountVerifyEmailResource, "/account/verify-email"),
    (AccountResendVerificationResource, "/account/verify-email/resend"),
    (AccountPasswordResetRequestResource, "/account/password-reset"),
    (AccountPasswordResetCompleteResource, "/account/password-reset/complete"),
    (AccountExportResource, "/account/export"),
    (AccountDeleteResource, "/account/delete"),
    (AccountOrderListResource, "/account/orders"),
    (AccountOrderResource, "/account/orders/<string:public_id>"),
    (AccountLibraryResource, "/account/library"),
    (AccountDownloadResource, "/account/library/<int:entitlement_id>/downloads"),
    (FreeClaimResource, "/account/free-claims"),
    (DownloadResource, "/downloads/<string:token>"),
    (CheckoutResource, "/checkout"),
    (CheckoutOrderResource, "/checkout/orders/<string:public_id>"),
    (CheckoutVerifyResource, "/checkout/orders/<string:public_id>/verify"),
    (CheckoutRetryResource, "/checkout/orders/<string:public_id>/retry"),
    (CheckoutCancelResource, "/checkout/orders/<string:public_id>/cancel"),
    (PaystackWebhookResource, "/payments/paystack/webhook"),
]

# Prefixes whose responses are private (never cached, never indexed).
PRIVATE_PREFIXES = (
    "/api/v1/account",
    "/api/v1/checkout",
    "/api/v1/downloads",
    "/api/v1/payments",
    "/api/v1/cart",
)
