"""Payment provider interface.

Providers turn an order into a hosted checkout session, verify transactions
server-side, authenticate webhooks and (where configured) issue refunds. Order
state is never changed here: ``app/services/commerce/payments.py`` decides what
a verified result means for an order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """The provider could not be reached or rejected the request (message is safe to log)."""


@dataclass(frozen=True)
class CheckoutSession:
    authorization_url: str
    access_code: str | None
    reference: str


@dataclass(frozen=True)
class VerifiedTransaction:
    """What the provider says about a transaction, fetched server-to-server."""

    reference: str
    provider_id: str
    status: str  # success | failed | abandoned | pending | reversed | ...
    amount_minor: int
    currency: str
    mode: str  # test | live
    channel: str = ""
    paid_at: datetime | None = None
    gateway_response: str = ""
    # Subscription checkouts (Batch 10.2): the plan the charge was for and the provider's
    # customer record. Empty for one-time payments.
    plan_code: str = ""
    customer_code: str = ""


@dataclass(frozen=True)
class ProviderPlan:
    """A recurring plan as the provider reports it (fetched server-to-server)."""

    plan_code: str
    amount_minor: int
    currency: str
    interval: str  # month | year (normalised)
    mode: str | None  # test | live, when the provider says


@dataclass(frozen=True)
class ProviderSubscription:
    subscription_code: str
    status: str
    plan_code: str
    customer_code: str
    customer_email: str
    email_token: str
    next_payment_at: datetime | None
    mode: str | None


@dataclass(frozen=True)
class WebhookEvent:
    event_type: str
    dedupe_key: str
    reference: str | None
    mode: str | None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RefundResult:
    provider_refund_id: str
    status: str  # pending | processing | processed | failed
    amount_minor: int
    currency: str


class PaymentProvider(Protocol):
    name: str
    supported_currencies: frozenset[str]
    supported_channels: tuple[str, ...]

    @property
    def mode(self) -> str | None: ...

    def configured(self) -> bool: ...

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
    ) -> CheckoutSession: ...

    def verify(self, reference: str) -> VerifiedTransaction: ...

    def verify_signature(self, raw_body: bytes, headers: dict[str, str]) -> bool: ...

    def parse_event(self, payload: dict[str, Any]) -> WebhookEvent: ...

    def refund(
        self, *, transaction_id: str, amount_minor: int, currency: str, note: str
    ) -> RefundResult: ...

    def fetch_refund(self, provider_refund_id: str) -> RefundResult: ...
