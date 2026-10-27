"""Resource access for modules that don't sell through the shop (future memberships and
text-based courses).

Every way of reaching a premium resource ends in an ``Entitlement`` row, so downloads go
through the same short-lived, logged authorisation (``downloads.authorize``) whatever
granted them, and revocation or expiry blocks them at once. A future module only needs:

- ``grant(customer, product, source="membership", reference="membership:42", expires_at=…)``
  when a member joins or renews (call again to extend: the same reference updates the
  existing entitlement instead of creating a second one);
- ``revoke(source, reference, reason)`` when the membership or enrolment ends;
- ``can_download(customer, product)`` to show "Download" instead of "Buy".

Memberships may only unlock resources marked ``membership_eligible``. Course enrolments
can unlock any resource that a course lists as reading material. Nothing here involves
video: courses are text lessons, exercises, quizzes and written downloads.
"""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select

from ...extensions import db
from ...models import Customer, Entitlement, EntitlementEvent, Product
from ...utils.errors import ConflictError, ValidationError
from .. import audit_service
from . import catalogue
from . import entitlements as ent_service

EXTERNAL_SOURCES = ("membership", "course")
_REFERENCE = re.compile(r"^[a-z0-9][a-z0-9:_-]{0,79}$")


def _key(source: str, reference: str, product: Product) -> str:
    return f"{source}:{reference}:product:{product.id}"


def _check(source: str, reference: str) -> None:
    if source not in EXTERNAL_SOURCES:
        raise ValidationError(details={"source": [f"Use one of: {', '.join(EXTERNAL_SOURCES)}."]})
    if not isinstance(reference, str) or not _REFERENCE.match(reference):
        raise ValidationError(details={"reference": ["Use a short lowercase reference."]})


def grant(
    customer: Customer,
    product: Product,
    *,
    source: str,
    reference: str,
    expires_at: datetime | None = None,
    reason: str = "",
) -> Entitlement:
    """Give (or extend) access to a resource through a membership or course enrolment."""
    _check(source, reference)
    if source == "membership" and not product.membership_eligible:
        raise ConflictError("This resource is not included in memberships.")
    if product.is_bundle:
        raise ValidationError(details={"product": ["Grant the bundle's resources one by one."]})
    entitlement, created = ent_service._grant(
        customer=customer,
        product=product,
        source=source,
        grant_key=_key(source, reference, product),
        reason=reason or f"{source.capitalize()} {reference}",
        download_limit=catalogue.effective_download_limit(product),
        expires_at=expires_at,
    )
    if not created:
        if entitlement.status == "revoked":
            entitlement.status = "active"
            entitlement.revoked_at = None
            entitlement.revoked_reason = ""
        entitlement.expires_at = expires_at
        db.session.add(
            EntitlementEvent(entitlement_id=entitlement.id, action="renewed", reason=reason[:300])
        )
    audit_service.record(
        f"entitlement.{source}_granted",
        "entitlement",
        entitlement.id,
        details={"reference": reference, "product_id": product.id, "created": created},
    )
    return entitlement


def revoke(source: str, reference: str, reason: str) -> int:
    """End every entitlement a membership or enrolment granted. Returns how many."""
    _check(source, reference)
    prefix = f"{source}:{reference}:product:"
    count = 0
    for entitlement in db.session.scalars(
        select(Entitlement).where(Entitlement.grant_key.startswith(prefix))
    ):
        count += ent_service.revoke(entitlement, reason or f"{source} ended", None)
    return count


def can_download(customer: Customer, product: Product) -> bool:
    """Whether the customer holds a usable entitlement to this resource (any source)."""
    rows = db.session.scalars(
        select(Entitlement).where(
            ent_service.account_scope(customer),
            Entitlement.product_id == product.id,
            Entitlement.status == "active",
            ent_service.not_expired(),
        )
    )
    return next(iter(rows), None) is not None
