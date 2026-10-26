"""Customer sessions (separate from administrator JWT sessions).

- Session: a random 256-bit token in an HttpOnly cookie (``tpa_customer``),
  scoped to ``/api/v1/``; only its SHA-256 hash is stored (``customer_sessions``).
- CSRF: a second random token in a readable cookie (``tpa_customer_csrf``); state-
  changing requests must echo it in ``X-Customer-CSRF``. Its hash is stored on the
  session, so a token from another session never validates.
- The admin API never reads these cookies, and customer endpoints never accept
  administrator tokens: the two account types cannot be confused.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from functools import wraps

from flask import current_app, g, request
from sqlalchemy import select, update

from ..extensions import db
from ..models import Customer, CustomerSession
from ..utils.errors import APIError, ForbiddenError

SESSION_COOKIE = "tpa_customer"
CSRF_COOKIE = "tpa_customer_csrf"
CSRF_HEADER = "X-Customer-CSRF"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
TOUCH_EVERY = timedelta(minutes=10)


class CustomerAuthRequired(APIError):
    status_code = 401
    code = "customer_auth_required"
    message = "Please sign in to your account."


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _cookie_args(max_age: int | None) -> dict:
    cfg = current_app.config
    return {
        "max_age": max_age,
        "secure": bool(cfg.get("CUSTOMER_COOKIE_SECURE")),
        "samesite": "Lax",
        "domain": cfg.get("JWT_COOKIE_DOMAIN") or None,
    }


def start_session(customer: Customer, response, *, remember: bool = True) -> CustomerSession:
    """Start a session. ``remember`` keeps a persistent cookie for CUSTOMER_SESSION_DAYS;
    otherwise the cookie ends with the browser session and the server-side session expires
    after CUSTOMER_SHORT_SESSION_HOURS, whichever comes first."""
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    cfg = current_app.config
    lifetime = (
        timedelta(days=cfg["CUSTOMER_SESSION_DAYS"])
        if remember
        else timedelta(hours=cfg["CUSTOMER_SHORT_SESSION_HOURS"])
    )
    session = CustomerSession(
        customer_id=customer.id,
        token_hash=_hash(token),
        csrf_hash=_hash(csrf),
        expires_at=_now() + lifetime,
        ip_address=request.remote_addr,
        user_agent=(request.user_agent.string or "")[:200],
    )
    db.session.add(session)
    max_age = int(lifetime.total_seconds()) if remember else None
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, path="/api/v1/", **_cookie_args(max_age)
    )
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, path="/", **_cookie_args(max_age))
    return session


def clear_cookies(response) -> None:
    for name, path in ((SESSION_COOKIE, "/api/v1/"), (CSRF_COOKIE, "/")):
        response.delete_cookie(
            name,
            path=path,
            domain=current_app.config.get("JWT_COOKIE_DOMAIN") or None,
            secure=bool(current_app.config.get("CUSTOMER_COOKIE_SECURE")),
            samesite="Lax",
        )


def revoke_all(customer: Customer, *, except_id: int | None = None) -> None:
    stmt = update(CustomerSession).where(
        CustomerSession.customer_id == customer.id, CustomerSession.revoked_at.is_(None)
    )
    if except_id is not None:
        stmt = stmt.where(CustomerSession.id != except_id)
    db.session.execute(stmt.values(revoked_at=_now()))


def current_session() -> CustomerSession | None:
    if "customer_session" in g:
        return g.customer_session
    token = request.cookies.get(SESSION_COOKIE)
    found = None
    if token and len(token) < 200:
        session = db.session.scalar(
            select(CustomerSession).where(CustomerSession.token_hash == _hash(token))
        )
        now = _now()
        if (
            session is not None
            and session.revoked_at is None
            and session.expires_at > now
            and session.customer.is_active
        ):
            found = session
            if now - session.last_seen_at > TOUCH_EVERY:
                session.last_seen_at = now
    g.customer_session = found
    return found


def current_customer() -> Customer | None:
    session = current_session()
    return session.customer if session else None


def check_csrf(session: CustomerSession) -> None:
    if request.method in SAFE_METHODS:
        return
    header = request.headers.get(CSRF_HEADER, "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    if not header or not cookie or not hmac.compare_digest(header, cookie):
        raise ForbiddenError("Missing or invalid security token. Refresh the page and try again.")
    if not hmac.compare_digest(_hash(header), session.csrf_hash):
        raise ForbiddenError("Missing or invalid security token. Refresh the page and try again.")


def require_customer(fn):
    """Require a signed-in, active customer; mutations also need the CSRF token."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        session = current_session()
        if session is None:
            raise CustomerAuthRequired()
        check_csrf(session)
        return fn(*args, **kwargs)

    return wrapper
