"""Secure download authorisation and delivery.

1. A signed-in customer asks for a specific file version from their library
   (``POST /api/v1/account/library/<entitlement>/downloads``). The server checks
   the entitlement (active, owned by this customer, file/version allowed by the
   version policy, deliverable, download limit) and creates a ``DownloadGrant``:
   a random 256-bit token (only its hash is stored) valid for a few minutes.
   Creating a link does **not** use the purchase's download allowance.
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

What counts (Batch 15)
----------------------
Browsers do not fetch a download in one request: they retry after a network error,
resume an interrupted download with ``Range: bytes=N-``, and some split a large file into
several ranged requests (Chrome's parallel downloading, iOS Safari, download managers).
Five such requests used to exhaust a link within seconds, and the allowance had already
been used when the link was created. Now:

* A link can **start** a download (no ``Range`` header, or a range from byte 0) up to
  ``DOWNLOAD_LINK_MAX_USES`` times; requests that resume or split it (a range from a later
  byte) are capped separately at ``DOWNLOAD_LINK_MAX_RANGE_REQUESTS``. Both stop when the
  link expires (``DOWNLOAD_LINK_TTL_SECONDS``).
* The purchase's download allowance (``Entitlement.download_limit``) is used when a file
  version is first **delivered** (the server hands over a response for an existing file),
  never for creating a link and never for a refused request. Further deliveries of the
  same version within ``DOWNLOAD_RETRY_WINDOW_MINUTES`` (retries, resumed or failed
  downloads, new links) are free; after that window a new download uses the allowance
  again. The allowance is checked and used in one conditional update, so it can never be
  exceeded, and the entitlement row is locked (PostgreSQL) so parallel requests count once.

Limits of delivery confirmation: with X-Accel-Redirect, Nginx sends the bytes after the
application has answered, and even when Flask streams the file the server cannot know
whether the browser saved all of it (the connection may drop after the last byte is
written to a buffer). The application can only verify that the request was authorised
and that the file exists in private storage, so that is what "delivered" means here;
the retry window is what keeps an undetectable failure from costing the customer a
download. ``served`` events record ``counted``, ``retry`` or ``range`` in their reason.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from flask import Response, current_app, request, send_file
from sqlalchemy import func, select, update

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


class LinkUsedUpError(APIError):
    status_code = 410
    code = "download_link_used_up"
    message = (
        "This download link has been used too many times. Start the download again from "
        "your library: a new link within the hour does not use another download."
    )


class FileUnavailableError(APIError):
    status_code = 503
    code = "download_file_unavailable"
    message = (
        "This file is temporarily unavailable, and no download was used. Please try again "
        "later or contact us."
    )


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


def _retry_window_start() -> datetime:
    return _now() - timedelta(minutes=current_app.config["DOWNLOAD_RETRY_WINDOW_MINUTES"])


def _recently_counted(entitlement_id: int, version_id: int) -> bool:
    """Whether this file version was delivered (and counted) within the retry window."""
    return (
        db.session.scalar(
            select(DownloadEvent.id)
            .where(
                DownloadEvent.entitlement_id == entitlement_id,
                DownloadEvent.file_version_id == version_id,
                DownloadEvent.status == "served",
                DownloadEvent.reason == "counted",
                DownloadEvent.created_at >= _retry_window_start(),
            )
            .limit(1)
        )
        is not None
    )


def _limit_reached(entitlement: Entitlement, version_id: int) -> bool:
    return (
        entitlement.download_limit is not None
        and entitlement.download_count >= entitlement.download_limit
        and not _recently_counted(entitlement.id, version_id)
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
    if not ent_service.is_usable(entitlement):
        _event("denied", "entitlement_expired", **ids)
        db.session.commit()
        raise NotEntitledError("Your access period for this item has ended.")
    allowed = {v.id: v for f in ent_service.accessible_files(entitlement) for _, v in f["versions"]}
    version = allowed.get(version_id)
    if version is None:
        _event("denied", "version_not_allowed", **ids)
        db.session.commit()
        raise NotEntitledError()
    if _limit_reached(entitlement, version.id):
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
    # The allowance is used when the file is delivered (serve), not here.
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


def file_available(version: ProductFileVersion) -> bool:
    """Whether the version's file is in private storage (checked before anything counts).

    The application writes these files itself, so it can see them in both delivery modes
    (with X-Accel-Redirect, Nginx reads the same folder)."""
    try:
        return get_private_storage().path(version.storage_key).is_file()
    except (OSError, ValueError):
        return False


def file_response(version: ProductFileVersion, stem: str) -> Response:
    storage = get_private_storage()
    filename = download_filename(version, stem)
    prefix = current_app.config.get("PRODUCT_FILES_ACCEL_REDIRECT_PREFIX")
    if prefix:
        # Nginx answers ranges and conditional requests from the file itself.
        response = Response(status=200, mimetype=version.mime_type)
        response.headers["X-Accel-Redirect"] = f"{prefix.rstrip('/')}/{version.storage_key}"
        response.headers["X-Accel-Buffering"] = "no"
    else:
        path = storage.path(version.storage_key)
        if not path.is_file():
            current_app.logger.error("Product file version %s is missing from storage", version.id)
            raise FileUnavailableError()
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
    if entitlement is None or entitlement.status != "active":
        _event("denied", "entitlement_revoked", **ids)
        db.session.commit()
        raise NotEntitledError("Access to this item has ended.")
    if not ent_service.is_usable(entitlement):
        _event("denied", "entitlement_expired", **ids)
        db.session.commit()
        raise NotEntitledError("Your access period for this item has ended.")
    allowed = {v.id for f in ent_service.accessible_files(entitlement) for _, v in f["versions"]}
    version = db.session.get(ProductFileVersion, grant.file_version_id)
    if version is None or version.id not in allowed:
        _event("denied", "version_not_allowed", **ids)
        db.session.commit()
        raise NotEntitledError()
    if not file_available(version):
        current_app.logger.error("Product file version %s is missing from storage", version.id)
        _event("denied", "file_missing", **ids)
        db.session.commit()
        raise FileUnavailableError()

    # Use of the link: starting the download, or resuming / splitting it.
    resuming = _is_continuation(request.headers.get("Range"))
    if resuming:
        # Lock the grant row (PostgreSQL) so the cap holds under parallel requests.
        db.session.execute(
            select(DownloadGrant.id).where(DownloadGrant.id == grant.id).with_for_update()
        )
        ranged = db.session.scalar(
            select(func.count(DownloadEvent.id)).where(
                DownloadEvent.grant_id == grant.id,
                DownloadEvent.status == "served",
                DownloadEvent.reason == "range",
            )
        )
        if ranged >= current_app.config["DOWNLOAD_LINK_MAX_RANGE_REQUESTS"]:
            _event("denied", "link_used_up", **ids)
            db.session.commit()
            raise LinkUsedUpError()
    else:
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
            raise LinkUsedUpError()

    # The purchase allowance: used once per delivery, not per request (see module doc).
    reason = _use_allowance(entitlement, version.id)
    if reason is None:
        _event("denied", "limit_reached", **ids)
        db.session.commit()
        raise DownloadLimitReached()
    product = entitlement.product
    stem = f"{product.slug}-{version.file.title}"[:120]
    stem = "".join(c if c.isalnum() or c in "-_ " else "-" for c in stem).strip().replace(" ", "-")
    stem = re.sub(r"-{2,}", "-", stem).strip("-") or "download"
    try:
        response = file_response(version, f"{stem}-v{version.version}")
    except APIError:
        # Nothing was delivered: undo the use of the link and of the allowance.
        db.session.rollback()
        _event("denied", "file_missing", **ids)
        db.session.commit()
        raise
    _event("served", "range" if resuming and reason == "retry" else reason, **ids)
    db.session.commit()
    return response


_RANGE = re.compile(r"^\s*bytes\s*=\s*(\d*)\s*-")


def _is_continuation(header: str | None) -> bool:
    """A request that resumes or splits a download: a byte range not starting at 0.

    No Range header, or a range from the first byte, starts the download. A suffix range
    ("bytes=-500") or anything unparsable is treated as a continuation, which has the
    larger but still finite cap."""
    if not header:
        return False
    match = _RANGE.match(header)
    if not match:
        return True
    return match.group(1) != "0"


def _use_allowance(entitlement: Entitlement, version_id: int) -> str | None:
    """Count a delivery against the allowance. Returns "counted", "retry" (delivered within
    the retry window: not counted again) or None when the allowance is used up."""
    # Serialise deliveries of this entitlement (PostgreSQL row lock; SQLite serialises
    # writers itself) so parallel first requests count once.
    db.session.execute(
        select(Entitlement.id).where(Entitlement.id == entitlement.id).with_for_update()
    )
    if _recently_counted(entitlement.id, version_id):
        return "retry"
    conditions = [Entitlement.id == entitlement.id]
    if entitlement.download_limit is not None:
        conditions.append(Entitlement.download_count < Entitlement.download_limit)
    counted = db.session.execute(
        update(Entitlement)
        .where(*conditions)
        .values(download_count=Entitlement.download_count + 1)
        .execution_options(synchronize_session=False)
    )
    if counted.rowcount != 1:
        return None
    db.session.expire(entitlement, ["download_count"])
    return "counted"


def browser_error_page(err: APIError, *, guest: bool) -> Response:
    """The answer to a refused download the browser navigated to (the customer pressed
    Download and the page went to the link): a short, readable page instead of JSON."""
    from html import escape

    if guest:
        back = (
            "<p>Go back to your purchase page and press Download again, or open the link in "
            "your purchase email.</p>"
        )
    else:
        back = '<p><a href="/account/library">Back to your library</a></p>'
    titles = {
        "download_link_expired": "This download link has expired",
        "download_link_used_up": "This download link has been used up",
        "download_limit_reached": "Download limit reached",
        "download_file_unavailable": "This file is temporarily unavailable",
    }
    title = titles.get(err.code, "This download could not start")
    body = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="robots" content="noindex">'
        f"<title>{escape(title)} · Think Positive Always</title>"
        "<style>body{font:17px/1.6 system-ui,sans-serif;max-width:36rem;margin:12vh auto;"
        "padding:0 1.25rem;color:#2b2b2b;background:#faf6ef}h1{font-size:1.6rem;"
        "line-height:1.25}a{color:#3f5a3c}</style></head><body>"
        f"<h1>{escape(title)}</h1><p>{escape(err.message)}</p>{back}"
        f"<p><small>Reference: {escape(err.code)}</small></p></body></html>"
    )
    response = Response(body, status=err.status_code, mimetype="text/html")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    return response


def wants_page() -> bool:
    """A top-level browser navigation (not the website's own API calls)."""
    if request.headers.get("Sec-Fetch-Mode") == "navigate":
        return True
    accept = request.accept_mimetypes
    return accept.best_match(["application/json", "text/html"]) == "text/html" and (
        accept["text/html"] > accept["application/json"]
    )


def grant_is_guest(token: str) -> bool:
    if not token or len(token) > 100:
        return False
    return bool(
        db.session.scalar(
            select(DownloadGrant.guest).where(DownloadGrant.token_hash == _hash(token))
        )
    )
