"""Secure download authorisation and delivery.

1. A signed-in customer asks for a specific file version from their library
   (``POST /api/v1/account/library/<entitlement>/downloads``). The server checks
   the entitlement (active, owned by this customer, file/version allowed by the
   version policy, deliverable, download limit) and creates a ``DownloadGrant``:
   a random 256-bit token (only its hash is stored) valid for a few minutes and a
   few uses (so interrupted or ranged downloads still work).
2. The browser follows ``/api/v1/downloads/<token>``. The token is checked again,
   *and* the request must carry the same customer's session cookie, and the
   entitlement is re-checked (a revocation blocks downloads immediately).
   Grants made for guest checkout (through a guest access link or the buyer's order
   token) are marked ``guest`` and skip the session check, nothing else.
3. The file is streamed by Flask, or handed to Nginx through an ``internal``
   location via X-Accel-Redirect, with ``Content-Disposition: attachment``, a
   sanitised file name, ``Cache-Control: private, no-store`` and ``noindex``.

Storage paths and keys are never sent to the client. Every authorisation and
every served or refused download is recorded in ``download_events``.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from flask import Response, current_app, request, send_file
from sqlalchemy import select, update

from ...extensions import db
from ...models import Customer, DownloadEvent, DownloadGrant, Entitlement, ProductFileVersion
from ...storage.private_files import get_private_storage
from ...utils.errors import APIError, NotFoundError
from . import entitlements as ent_service
from .entitlements import NotEntitledError


class DownloadLimitReached(APIError):
    status_code = 403
    code = "download_limit_reached"
    message = "You've reached the download limit for this file. Contact us if you need help."


class LinkExpiredError(APIError):
    status_code = 410
    code = "download_link_expired"
    message = "This download link has expired. Start the download again from your library."


def _now() -> datetime:
    return datetime.now(UTC)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _event(status: str, reason: str = "", **ids) -> None:
    db.session.add(
        DownloadEvent(
            status=status,
            reason=reason[:120],
            ip_address=request.remote_addr,
            user_agent=(request.user_agent.string or "")[:200],
            **ids,
        )
    )


def authorize(customer: Customer, entitlement_id: int, version_id: int) -> dict:
    return _authorize(customer, entitlement_id, version_id, ent_service.account_scope(customer))


def authorize_guest(customer: Customer, entitlement_id: int, version_id: int) -> dict:
    """A download for a guest-checkout purchase, through a guest access link or order token.

    There is no session to match when the file is served, so the grant is marked
    ``guest``; it is still short-lived, limited to a few uses and re-checked on use.
    """
    return _authorize(
        customer, entitlement_id, version_id, ent_service.guest_scope(customer), guest=True
    )


def _authorize(
    customer: Customer, entitlement_id: int, version_id: int, scope, *, guest: bool = False
) -> dict:
    entitlement = db.session.scalar(
        select(Entitlement).where(Entitlement.id == entitlement_id, scope)
    )
    if entitlement is None:
        # Same answer whether it doesn't exist or belongs to someone else.
        raise NotFoundError("This item is not in your library.")
    ids = {
        "customer_id": customer.id,
        "entitlement_id": entitlement.id,
        "product_id": entitlement.product_id,
    }
    if entitlement.status != "active":
        _event("denied", "entitlement_revoked", **ids)
        db.session.commit()
        raise NotEntitledError("Access to this item has ended.")
    allowed = {v.id: v for f in ent_service.accessible_files(entitlement) for _, v in f["versions"]}
    version = allowed.get(version_id)
    if version is None:
        _event("denied", "version_not_allowed", **ids)
        db.session.commit()
        raise NotEntitledError()
    if (
        entitlement.download_limit is not None
        and entitlement.download_count >= entitlement.download_limit
    ):
        _event("denied", "limit_reached", file_version_id=version.id, **ids)
        db.session.commit()
        raise DownloadLimitReached()
    token = secrets.token_urlsafe(32)
    ttl = current_app.config["DOWNLOAD_LINK_TTL_SECONDS"]
    grant = DownloadGrant(
        token_hash=_hash(token),
        entitlement_id=entitlement.id,
        customer_id=customer.id,
        file_version_id=version.id,
        expires_at=_now() + timedelta(seconds=ttl),
        guest=guest,
    )
    db.session.add(grant)
    # Each authorised download counts once against an optional limit.
    db.session.execute(
        update(Entitlement)
        .where(Entitlement.id == entitlement.id)
        .values(download_count=Entitlement.download_count + 1)
    )
    db.session.flush()
    _event("authorized", file_version_id=version.id, grant_id=grant.id, **ids)
    return {"url": f"/api/v1/downloads/{token}", "expires_in": ttl}


def download_filename(version: ProductFileVersion, stem: str) -> str:
    return f"{stem}.{version.file_format}"


def _content_disposition(filename: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    ascii_name = "".join(c if c.isalnum() or c in "-_." else "-" for c in ascii_name)
    ascii_name = re.sub(r"-{2,}", "-", ascii_name).strip("-") or "download"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def file_response(version: ProductFileVersion, stem: str) -> Response:
    storage = get_private_storage()
    filename = download_filename(version, stem)
    prefix = current_app.config.get("PRODUCT_FILES_ACCEL_REDIRECT_PREFIX")
    if prefix:
        response = Response(status=200, mimetype=version.mime_type)
        response.headers["X-Accel-Redirect"] = f"{prefix.rstrip('/')}/{version.storage_key}"
        response.headers["X-Accel-Buffering"] = "no"
    else:
        path = storage.path(version.storage_key)
        if not path.is_file():
            current_app.logger.error("Product file version %s is missing from storage", version.id)
            raise NotFoundError("This file is temporarily unavailable. Please contact us.")
        response = send_file(
            path,
            mimetype=version.mime_type,
            as_attachment=True,
            download_name=filename,
            conditional=True,
            max_age=0,
        )
    response.headers["Content-Disposition"] = _content_disposition(filename)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


def serve(token: str, customer: Customer | None) -> Response:
    if not token or len(token) > 100:
        raise NotFoundError()
    grant = db.session.scalar(select(DownloadGrant).where(DownloadGrant.token_hash == _hash(token)))
    if grant is None:
        raise NotFoundError("This download link is not valid.")
    ids = {
        "customer_id": grant.customer_id,
        "entitlement_id": grant.entitlement_id,
        "file_version_id": grant.file_version_id,
        "grant_id": grant.id,
    }
    entitlement = db.session.get(Entitlement, grant.entitlement_id)
    ids["product_id"] = entitlement.product_id if entitlement else None
    if not grant.guest and (customer is None or customer.id != grant.customer_id):
        _event("denied", "session_mismatch", **ids)
        db.session.commit()
        raise NotEntitledError("Sign in to the account that owns this download.")
    if grant.expires_at <= _now():
        _event("denied", "link_expired", **ids)
        db.session.commit()
        raise LinkExpiredError()
    used = db.session.execute(
        update(DownloadGrant)
        .where(
            DownloadGrant.id == grant.id,
            DownloadGrant.use_count < current_app.config["DOWNLOAD_LINK_MAX_USES"],
        )
        .values(use_count=DownloadGrant.use_count + 1)
    )
    if used.rowcount != 1:
        _event("denied", "link_used_up", **ids)
        db.session.commit()
        raise LinkExpiredError()
    if entitlement is None or entitlement.status != "active":
        _event("denied", "entitlement_revoked", **ids)
        db.session.commit()
        raise NotEntitledError("Access to this item has ended.")
    allowed = {v.id for f in ent_service.accessible_files(entitlement) for _, v in f["versions"]}
    version = db.session.get(ProductFileVersion, grant.file_version_id)
    if version is None or version.id not in allowed:
        _event("denied", "version_not_allowed", **ids)
        db.session.commit()
        raise NotEntitledError()
    product = entitlement.product
    stem = f"{product.slug}-{version.file.title}"[:120]
    stem = "".join(c if c.isalnum() or c in "-_ " else "-" for c in stem).strip().replace(" ", "-")
    _event("served", **ids)
    db.session.commit()
    return file_response(version, f"{stem}-v{version.version}")
