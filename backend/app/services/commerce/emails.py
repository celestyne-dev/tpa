"""Transactional email templates (plain text) and honest delivery records.

Messages go through the existing mail abstraction (``app/services/mail.py``).
Every attempt is recorded in ``email_deliveries`` with what really happened:
``sent`` (SMTP accepted it), ``development_console`` (written to the server log,
not sent), ``memory`` (tests), ``not_configured`` or ``failed``. Nothing in the
admin or the storefront claims an email was sent unless the status is ``sent``.
"""

from __future__ import annotations

from typing import Any

from flask import current_app

from ...commerce.currency import format_money
from ...extensions import db
from ...models import Customer, EmailDelivery, Order
from .. import mail

STATUS_BY_BACKEND = {
    "smtp": "sent",
    "development_console": "development_console",
    "memory": "memory",
}


def _site() -> str:
    return current_app.config["SITE_URL"]


def _brand() -> str:
    from ..settings_service import get_values

    return get_values().get("site.name") or "Think Positive Always"


def _signature() -> str:
    return f"\n\nWith warmth,\n{_brand()}\n{_site()}\n"


def _lines(order: Order) -> str:
    return "\n".join(
        f"- {item.title}: {format_money(item.line_total_minor, item.currency)}"
        for item in order.items
    )


def render(template: str, context: dict[str, Any]) -> tuple[str, str]:
    """Return (subject, text) for a template."""
    brand = _brand()
    name = context.get("name") or "there"
    order: Order | None = context.get("order")
    if template == "verify_email":
        return (
            f"Confirm your email for {brand}",
            f"Hello {name},\n\nPlease confirm your email address to finish setting up your "
            f"account:\n\n{context['link']}\n\nThis link expires in {context['hours']} hours. "
            + (
                "Confirming adds the purchases made with this email address to the account, "
                "so only confirm if you created it. "
                if context.get("claims_purchases")
                else ""
            )
            + "If you did not create an account, you can ignore this email."
            + _signature(),
        )
    if template == "password_reset":
        return (
            f"Reset your {brand} password",
            f"Hello {name},\n\nSomeone asked to reset the password for your account. To choose "
            f"a new password, open this link:\n\n{context['link']}\n\nIt expires in "
            f"{context['minutes']} minutes and can be used once. If this wasn't you, ignore "
            "this email; your password has not changed." + _signature(),
        )
    if template == "order_confirmation":
        return (
            f"Order {order.number} confirmed",
            f"Hello {name},\n\nThank you for your order. Your payment has been confirmed.\n\n"
            f"Order: {order.number}\n{_lines(order)}\n\nTotal charged: "
            f"{format_money(order.total_minor, order.currency)}"
            + (" (test mode — no real money was charged)" if order.mode == "test" else "")
            + f"\nReceipt: {context.get('receipt_number', '')}\n\n"
            + (
                f"Your downloads: {context['access_link']}"
                if context.get("access_link")
                else f"View your order: {_site()}/account/orders"
            )
            + _signature(),
        )
    if template == "payment_received":
        return (
            f"Receipt {context.get('receipt_number', '')} for order {order.number}",
            f"Hello {name},\n\nThis is your receipt.\n\nReceipt: {context.get('receipt_number')}\n"
            f"Order: {order.number}\nDate: {context.get('paid_at', '')}\n{_lines(order)}\n\n"
            f"Amount paid: {format_money(order.total_minor, order.currency)}\n"
            f"Payment reference: {context.get('reference', '')}\n"
            + ("Mode: TEST (no real money was charged)\n" if order.mode == "test" else "")
            + "\nPrices are in the currency shown; no currency conversion was applied by us."
            + _signature(),
        )
    if template == "payment_failed":
        return (
            f"Payment not completed for order {order.number}",
            f"Hello {name},\n\nYour payment for order {order.number} was not completed, so you "
            "have not been charged by us for this attempt. "
            + (
                "You can try again from the checkout page in the browser you used, or start a "
                f"new checkout from the shop:\n\n{_site()}/shop"
                if order.is_guest
                else f"You can try again from your account:\n\n{_site()}/account/orders"
            )
            + "\n\nIf money left your account, contact us with the order number and we'll "
            "investigate." + _signature(),
        )
    if template == "download_instructions" and context.get("access_link"):
        products = "\n".join(f"- {t}" for t in context.get("products", []))
        return (
            "Your downloads are ready",
            f"Hello {name},\n\nThank you for your purchase. Download your resources here:\n"
            f"{products}\n\n{context['access_link']}\n\nThis private link works for "
            f"{context['hours']} hours; don't share it. You can ask for a new link at any time "
            f"from {_site()}/purchases using this email address.\n\nWant a permanent library? "
            f"Create an account with this email address at {_site()}/register and confirm it: "
            "your purchases will appear there." + _signature(),
        )
    if template == "guest_access":
        return (
            f"Your {brand} purchases",
            f"Hello {name},\n\nHere is a private link to the purchases made with this email "
            f"address:\n\n{context['access_link']}\n\nIt works for {context['hours']} hours and "
            "replaces any earlier link. If you didn't ask for this, you can ignore this email."
            + _signature(),
        )
    if template == "download_instructions":
        products = "\n".join(f"- {t}" for t in context.get("products", []))
        return (
            "Your downloads are ready",
            f"Hello {name},\n\nThese resources are now in your library:\n{products}\n\n"
            f"Sign in and open your library to download them at any time:\n"
            f"{_site()}/account/library\n\nDownload links are created when you click "
            "Download and expire after a few minutes, so please download from your library "
            "rather than sharing links." + _signature(),
        )
    if template == "refund_confirmation":
        return (
            f"Refund processed for order {order.number}",
            f"Hello {name},\n\nA refund of {format_money(context['amount_minor'], order.currency)} "
            f"for order {order.number} has been processed by our payment provider. It can take "
            "several business days to appear, depending on your bank or mobile money "
            "provider."
            + ("\n\nAccess to the refunded downloads has ended." if context.get("revoked") else "")
            + _signature(),
        )
    raise KeyError(template)


TEMPLATES = (
    "verify_email",
    "password_reset",
    "order_confirmation",
    "payment_received",
    "payment_failed",
    "download_instructions",
    "guest_access",
    "refund_confirmation",
)


def send(
    template: str,
    to: str,
    context: dict[str, Any],
    *,
    customer: Customer | None = None,
    order: Order | None = None,
) -> str:
    """Send a template and record the real outcome. Never raises for delivery problems."""
    subject, text = render(template, context)
    try:
        method = mail.send(mail.EmailMessage(to=to, subject=subject, text=text))
        status = STATUS_BY_BACKEND.get(method, "sent")
    except mail.MailNotConfiguredError:
        status = "not_configured"
    except mail.MailDeliveryError:
        status = "failed"
    db.session.add(
        EmailDelivery(
            template=template,
            recipient=to,
            customer_id=customer.id if customer else None,
            order_id=order.id if order else None,
            status=status,
        )
    )
    return status
