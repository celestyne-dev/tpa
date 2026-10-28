"""Paystack provider (hosted checkout, server-side verification, signed webhooks, refunds).

Uses Paystack's documented REST API:
- POST /transaction/initialize      -> authorization_url, access_code, reference
- GET  /transaction/verify/:ref     -> status, amount (subunit), currency, domain, id
- POST /refund, GET /refund/:id     -> refund status
- POST /plan, GET /plan/:code       -> recurring plans (Batch 10.2, subscriptions)
- GET  /subscription/:code          -> subscription status, plan and customer
- POST /subscription/disable|enable -> stop / restart future charges (code + email token)
- GET  /subscription/:code/manage/link -> hosted page where the customer updates their card
  (Batch 10.3). Card details and authorisation codes never reach this application.
- Webhooks: ``x-paystack-signature`` is the HMAC-SHA512 of the raw request body,
  keyed with the secret key.

The secret key is read from the environment (``PAYSTACK_SECRET_KEY``) and is
only ever sent to Paystack in the Authorization header. Card details never
touch this application: customers pay on Paystack's hosted page.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from flask import current_app

from .base import (
    CheckoutSession,
    ProviderError,
    ProviderPlan,
    ProviderSubscription,
    RefundResult,
    VerifiedTransaction,
    WebhookEvent,
)

logger = logging.getLogger("tpa.payments")

# Currencies Paystack can process for some merchants. Whether *this* merchant can
# charge in a currency depends on their country and account activation, which is
# why checkout also requires the Super Admin to enable each currency explicitly.
SUPPORTED_CURRENCIES = frozenset({"NGN", "GHS", "ZAR", "KES", "USD", "XOF", "EGP"})
SUPPORTED_CHANNELS = (
    "card",
    "mobile_money",
    "bank",
    "bank_transfer",
    "ussd",
    "qr",
    "apple_pay",
    "eft",
)
# Fields kept from webhook/verify payloads. Customer authorisation data (card BIN,
# last4, signatures, authorisation codes) and personal details are dropped.
_KEEP = (
    "id",
    "domain",
    "status",
    "reference",
    "transaction_reference",
    "refund_reference",
    "amount",
    "currency",
    "channel",
    "paid_at",
    "paidAt",
    "gateway_response",
    "deducted_amount",
    "merchant_note",
)


# Paystack's interval names <-> ours.
PLAN_INTERVALS = {"month": "monthly", "year": "annually"}
_INTERVALS_BACK = {v: k for k, v in PLAN_INTERVALS.items()}


def _code(value: Any, key: str) -> str:
    """A code from a field that may hold the code itself or an object containing it."""
    if isinstance(value, dict):
        value = value.get(key)
    return str(value) if isinstance(value, str) else ""


def _parse_time(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def sanitize(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    out = {k: data[k] for k in _KEEP if k in data and not isinstance(data[k], dict | list)}
    transaction = data.get("transaction")
    if isinstance(transaction, dict):
        out["transaction"] = {
            k: transaction.get(k) for k in ("id", "reference") if k in transaction
        }
    elif transaction is not None and not isinstance(transaction, list):
        out["transaction"] = transaction
    return out


class PaystackProvider:
    name = "paystack"
    supported_currencies = SUPPORTED_CURRENCIES
    supported_channels = SUPPORTED_CHANNELS

    def __init__(self, secret_key: str | None = None, api_base: str | None = None):
        cfg = current_app.config
        self._secret = secret_key if secret_key is not None else cfg.get("PAYSTACK_SECRET_KEY", "")
        self._base = (api_base or cfg.get("PAYSTACK_API_BASE") or "https://api.paystack.co").rstrip(
            "/"
        )
        self._timeout = cfg.get("PAYSTACK_TIMEOUT_SECONDS", 20)

    # ---- configuration -------------------------------------------------------------

    @property
    def mode(self) -> str | None:
        if self._secret.startswith("sk_test_"):
            return "test"
        if self._secret.startswith("sk_live_"):
            return "live"
        return None

    def configured(self) -> bool:
        return self.mode is not None

    # ---- HTTP ---------------------------------------------------------------------------

    def _request(self, method: str, path: str, body: dict | None = None) -> dict[str, Any]:
        if not self.configured():
            raise ProviderError("Paystack is not configured (PAYSTACK_SECRET_KEY).")
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self._base + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._secret}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "ThinkPositiveAlways/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as err:
            try:
                payload = json.loads(err.read().decode("utf-8") or "{}")
            except ValueError:
                payload = {}
            message = str(payload.get("message") or f"HTTP {err.code}")[:200]
            logger.warning("Paystack %s %s failed: %s", method, path.split("/")[1], message)
            raise ProviderError(f"Paystack: {message}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as err:
            logger.warning("Paystack request failed: %s", err.__class__.__name__)
            raise ProviderError("Paystack could not be reached. Please try again.") from None
        if not isinstance(payload, dict) or payload.get("status") is not True:
            message = str((payload or {}).get("message") or "request failed")[:200]
            raise ProviderError(f"Paystack: {message}")
        return payload.get("data") or {}

    # ---- checkout -----------------------------------------------------------------------

    def initialize(
        self,
        *,
        email: str,
        amount_minor: int,
        currency: str,
        reference: str,
        callback_url: str,
        channels: list[str],
        metadata: dict[str, Any],
        plan: str | None = None,
    ) -> CheckoutSession:
        body: dict[str, Any] = {
            "email": email,
            "amount": str(amount_minor),
            "currency": currency,
            "reference": reference,
            "callback_url": callback_url,
            "metadata": metadata,
        }
        if channels:
            body["channels"] = channels
        if plan:
            # Paystack charges the plan's amount and creates the subscription after the
            # first successful payment; the amount is still sent and verified afterwards.
            body["plan"] = plan
        data = self._request("POST", "/transaction/initialize", body)
        url = data.get("authorization_url")
        local_mock = self._base.startswith("http://127.0.0.1")  # development mock only
        if not isinstance(url, str) or not (
            url.startswith("https://") or (local_mock and url.startswith("http://127.0.0.1"))
        ):
            raise ProviderError("Paystack returned an invalid checkout address.")
        if data.get("reference") not in (None, reference):
            raise ProviderError("Paystack returned a different reference.")
        return CheckoutSession(url, data.get("access_code"), reference)

    def verify(self, reference: str) -> VerifiedTransaction:
        data = self._request("GET", f"/transaction/verify/{urllib.parse.quote(reference, safe='')}")
        return self._transaction(data)

    @staticmethod
    def _transaction(data: dict[str, Any]) -> VerifiedTransaction:
        try:
            amount = int(data.get("amount"))
        except (TypeError, ValueError):
            raise ProviderError("Paystack returned an invalid amount.") from None
        return VerifiedTransaction(
            reference=str(data.get("reference") or ""),
            provider_id=str(data.get("id") or ""),
            status=str(data.get("status") or "").lower(),
            amount_minor=amount,
            currency=str(data.get("currency") or "").upper(),
            mode="live" if data.get("domain") == "live" else "test",
            channel=str(data.get("channel") or "")[:40],
            paid_at=_parse_time(data.get("paid_at") or data.get("paidAt")),
            gateway_response=str(data.get("gateway_response") or "")[:200],
            plan_code=(
                _code(data.get("plan"), "plan_code") or _code(data.get("plan_object"), "plan_code")
            )[:60],
            customer_code=_code(data.get("customer"), "customer_code")[:60],
        )

    # ---- recurring plans and subscriptions ------------------------------------------------

    def create_plan(
        self, *, name: str, amount_minor: int, currency: str, interval: str
    ) -> ProviderPlan:
        if interval not in PLAN_INTERVALS:
            raise ProviderError("Unsupported billing interval.")
        data = self._request(
            "POST",
            "/plan",
            {
                "name": name[:100],
                "amount": str(amount_minor),
                "currency": currency,
                "interval": PLAN_INTERVALS[interval],
            },
        )
        return self._plan(data)

    def fetch_plan(self, plan_code: str) -> ProviderPlan:
        return self._plan(self._request("GET", f"/plan/{urllib.parse.quote(plan_code, safe='')}"))

    @staticmethod
    def _plan(data: dict[str, Any]) -> ProviderPlan:
        try:
            amount = int(data.get("amount"))
        except (TypeError, ValueError):
            raise ProviderError("Paystack returned an invalid plan amount.") from None
        code = data.get("plan_code")
        if not isinstance(code, str) or not code:
            raise ProviderError("Paystack returned a plan without a code.")
        domain = data.get("domain")
        return ProviderPlan(
            plan_code=code[:60],
            amount_minor=amount,
            currency=str(data.get("currency") or "").upper(),
            interval=_INTERVALS_BACK.get(str(data.get("interval") or ""), ""),
            mode=("live" if domain == "live" else "test") if domain else None,
        )

    def fetch_subscription(self, subscription_code: str) -> ProviderSubscription:
        data = self._request(
            "GET", f"/subscription/{urllib.parse.quote(subscription_code, safe='')}"
        )
        customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
        domain = data.get("domain")
        return ProviderSubscription(
            subscription_code=str(data.get("subscription_code") or "")[:60],
            status=str(data.get("status") or "").lower()[:30],
            plan_code=_code(data.get("plan"), "plan_code")[:60],
            customer_code=str(customer.get("customer_code") or "")[:60],
            customer_email=str(customer.get("email") or "").strip().lower()[:254],
            email_token=str(data.get("email_token") or "")[:100],
            next_payment_at=_parse_time(data.get("next_payment_date")),
            mode=("live" if domain == "live" else "test") if domain else None,
        )

    def disable_subscription(self, subscription_code: str, email_token: str) -> None:
        """Stop future charges (Paystack keeps the subscription record)."""
        self._request(
            "POST", "/subscription/disable", {"code": subscription_code, "token": email_token}
        )

    def enable_subscription(self, subscription_code: str, email_token: str) -> None:
        self._request(
            "POST", "/subscription/enable", {"code": subscription_code, "token": email_token}
        )

    def manage_link(self, subscription_code: str) -> str:
        """A short-lived Paystack-hosted page for updating the payment method."""
        data = self._request(
            "GET", f"/subscription/{urllib.parse.quote(subscription_code, safe='')}/manage/link"
        )
        link = data.get("link")
        host = urllib.parse.urlparse(link).hostname if isinstance(link, str) else None
        if (
            not host
            or not link.startswith("https://")
            or not (host == "paystack.com" or host.endswith(".paystack.com"))
        ):
            raise ProviderError("Paystack returned an invalid management link.")
        return link

    # ---- webhooks -----------------------------------------------------------------------

    def verify_signature(self, raw_body: bytes, headers: dict[str, str]) -> bool:
        signature = headers.get("x-paystack-signature") or headers.get("X-Paystack-Signature")
        if not self.configured() or not signature:
            return False
        expected = hmac.new(self._secret.encode(), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, signature.strip().lower())

    def parse_event(self, payload: dict[str, Any]) -> WebhookEvent:
        event_type = str(payload.get("event") or "")[:60]
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        clean = sanitize(data)
        if event_type.startswith("refund."):
            reference = data.get("transaction_reference")
            if reference is None and isinstance(data.get("transaction"), dict):
                reference = data["transaction"].get("reference")
            ident = data.get("id") or data.get("refund_reference") or reference
        elif event_type.startswith("subscription."):
            reference = None
            ident = data.get("subscription_code") or data.get("id")
        elif event_type.startswith(("invoice.", "charge.dispute.")):
            # Invoices (renewal attempts) and disputes point at a transaction.
            tx = data.get("transaction") if isinstance(data.get("transaction"), dict) else {}
            reference = tx.get("reference") or data.get("transaction_reference")
            ident = data.get("invoice_code") or data.get("id") or reference
        else:
            reference = data.get("reference")
            ident = data.get("id") or reference
        status = str(data.get("status") or "")
        # Codes only (never authorisation data or personal details) for subscription routing.
        codes = {
            "plan_code": (
                _code(data.get("plan"), "plan_code") or _code(data.get("plan_object"), "plan_code")
            )[:60],
            "subscription_code": (
                str(data.get("subscription_code") or "")
                or _code(data.get("subscription"), "subscription_code")
            )[:60],
            "invoice_code": str(data.get("invoice_code") or "")[:60],
            "customer_code": _code(data.get("customer"), "customer_code")[:60],
        }
        clean |= {k: v for k, v in codes.items() if v}
        return WebhookEvent(
            event_type=event_type,
            dedupe_key=f"{event_type}:{ident}:{status}"[:160],
            reference=str(reference)[:100] if reference else None,
            mode=("live" if data.get("domain") == "live" else "test") if data else None,
            data=clean | {"raw_status": status},
        )

    # ---- refunds ------------------------------------------------------------------------

    def refund(
        self, *, transaction_id: str, amount_minor: int, currency: str, note: str
    ) -> RefundResult:
        data = self._request(
            "POST",
            "/refund",
            {
                "transaction": transaction_id,
                "amount": str(amount_minor),
                "currency": currency,
                "merchant_note": note[:200],
            },
        )
        return self._refund(data, amount_minor, currency)

    def fetch_refund(self, provider_refund_id: str) -> RefundResult:
        data = self._request("GET", f"/refund/{urllib.parse.quote(provider_refund_id, safe='')}")
        return self._refund(data, None, None)

    @staticmethod
    def _refund(data: dict[str, Any], amount: int | None, currency: str | None) -> RefundResult:
        try:
            value = int(data.get("amount", amount))
        except (TypeError, ValueError):
            value = amount or 0
        return RefundResult(
            provider_refund_id=str(data.get("id") or ""),
            status=str(data.get("status") or "pending").lower(),
            amount_minor=value,
            currency=str(data.get("currency") or currency or "").upper(),
        )


def get_provider(name: str = "paystack"):
    """Provider factory (tests replace it through ``app.extensions['tpa_payment_provider']``)."""
    override = current_app.extensions.get("tpa_payment_provider")
    if override is not None:
        return override
    if name != "paystack":
        raise ProviderError(f"Unknown payment provider '{name}'.")
    return PaystackProvider()
