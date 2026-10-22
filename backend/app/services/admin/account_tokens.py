"""Invitations and password resets with single-use, time-limited tokens.

- Tokens are 256-bit random values (secrets.token_urlsafe); only their SHA-256
  hash is stored, so a database leak does not reveal usable links.
- Links carry the token in the URL fragment (#token=...), which browsers never
  send to servers or in Referer headers.
- Redemption is atomic (UPDATE ... WHERE used_at IS NULL AND revoked_at IS NULL
  AND expires_at > now), so a token can be used exactly once.
- Tokens are never returned by the API; they are delivered by the mail backend.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import select, update

from ...auth.decorators import user_permissions
from ...auth.passwords import hash_password, password_problems
from ...auth.permissions import can_grant_roles
from ...auth.roles import get_roles, set_user_roles
from ...auth.session import revoke_all_sessions
from ...extensions import db
from ...models import AccountToken, User
from ...utils.errors import (
    APIError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from ...utils.validation import is_email, plain_text_problem
from .. import audit_service, mail
from ..serializers import iso
from .auth_service import normalise_email

INVITATION = "invitation"
PASSWORD_RESET = "password_reset"


class InvalidLinkError(APIError):
    status_code = 400
    code = "link_invalid"
    message = "This link is invalid, has already been used, or has expired."


def _now() -> datetime:
    return datetime.now(UTC)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def token_dict(t: AccountToken) -> dict[str, Any]:
    """Administrative view of a token record. Never includes the token or its hash."""
    return {
        "id": t.id,
        "purpose": t.purpose,
        "email": t.email,
        "display_name": t.display_name,
        "roles": list(t.roles or []),
        "status": t.status(),
        "created_at": iso(t.created_at),
        "expires_at": iso(t.expires_at),
        "used_at": iso(t.used_at),
        "revoked_at": iso(t.revoked_at),
        "delivery": t.delivery,
        "created_by": {"id": t.created_by.id, "display_name": t.created_by.display_name}
        if t.created_by
        else None,
    }


def _link(path: str, token: str) -> str:
    return f"{current_app.config['ADMIN_BASE_URL']}{path}#token={token}"


def _check_grant(actor: User, roles: list[str]) -> None:
    get_roles(sorted(set(roles)))  # validates names
    if not can_grant_roles(user_permissions(actor), roles):
        raise ForbiddenError("You cannot grant one or more of these roles.")


# ---- invitations ----------------------------------------------------------------


def _send_invitation(invite: AccountToken, token: str, actor: User) -> None:
    hours = current_app.config["INVITATION_TTL_HOURS"]
    invite.delivery = mail.send(
        mail.EmailMessage(
            to=invite.email,
            subject="You're invited to the Think Positive Always admin",
            text=(
                f"Hello {invite.display_name or ''},\n\n"
                f"{actor.display_name} has invited you to administer Think Positive Always "
                f"({', '.join(r.replace('_', ' ') for r in invite.roles)}).\n\n"
                "Activate your account and choose your own password here:\n"
                f"{_link('/admin/activate', token)}\n\n"
                f"This link can be used once and expires in {hours} hours. "
                "If you were not expecting this email, you can ignore it."
            ),
        )
    )


def create_invitation(data: dict[str, Any], actor: User) -> AccountToken:
    email = normalise_email(data["email"])
    roles = sorted(set(data.get("roles") or []))
    errors: dict[str, list[str]] = {}
    if not is_email(email):
        errors["email"] = ["Enter a valid email address."]
    if not roles:
        errors["roles"] = ["Assign at least one role."]
    name = (data.get("display_name") or "").strip()
    if name and (problem := plain_text_problem(name)):
        errors["display_name"] = [problem]
    if errors:
        raise ValidationError(details=errors)
    _check_grant(actor, roles)
    if db.session.scalar(select(User.id).where(User.email == email)):
        raise ConflictError(details={"email": ["An account with this email already exists."]})

    # A new invitation replaces any outstanding one for the same address.
    db.session.execute(
        update(AccountToken)
        .where(
            AccountToken.purpose == INVITATION,
            AccountToken.email == email,
            AccountToken.used_at.is_(None),
            AccountToken.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )
    token, digest = _new_token()
    invite = AccountToken(
        purpose=INVITATION,
        token_hash=digest,
        email=email,
        display_name=name or None,
        roles=roles,
        created_by_id=actor.id,
        expires_at=_now() + timedelta(hours=current_app.config["INVITATION_TTL_HOURS"]),
    )
    db.session.add(invite)
    db.session.flush()
    _send_invitation(invite, token, actor)
    audit_service.record(
        "invitation.created",
        "invitation",
        invite.id,
        actor=actor,
        details={"email": email, "roles": roles, "delivery": invite.delivery},
    )
    return invite


def resend_invitation(invite: AccountToken, actor: User) -> AccountToken:
    if invite.purpose != INVITATION or invite.status() not in ("pending", "expired"):
        raise ConflictError("Only pending or expired invitations can be resent.")
    _check_grant(actor, invite.roles)
    if db.session.scalar(select(User.id).where(User.email == invite.email)):
        raise ConflictError("An account with this email already exists.")
    token, digest = _new_token()
    invite.token_hash = digest  # the previous link stops working immediately
    invite.expires_at = _now() + timedelta(hours=current_app.config["INVITATION_TTL_HOURS"])
    db.session.flush()
    _send_invitation(invite, token, actor)
    audit_service.record(
        "invitation.resent",
        "invitation",
        invite.id,
        actor=actor,
        details={"email": invite.email, "delivery": invite.delivery},
    )
    return invite


def revoke_invitation(invite: AccountToken, actor: User) -> AccountToken:
    if invite.purpose != INVITATION or invite.status() != "pending":
        raise ConflictError("Only pending invitations can be revoked.")
    invite.revoked_at = _now()
    audit_service.record(
        "invitation.revoked", "invitation", invite.id, actor=actor, details={"email": invite.email}
    )
    return invite


def list_invitations(status: str | None = None) -> list[dict[str, Any]]:
    rows = db.session.scalars(
        select(AccountToken)
        .where(AccountToken.purpose == INVITATION)
        .order_by(AccountToken.created_at.desc(), AccountToken.id.desc())
        .limit(200)
    ).all()
    items = [token_dict(t) for t in rows]
    return [i for i in items if i["status"] == status] if status else items


def get_invitation(invite_id: int) -> AccountToken:
    invite = db.session.get(AccountToken, invite_id)
    if invite is None or invite.purpose != INVITATION:
        raise NotFoundError("Invitation not found.")
    return invite


# ---- redemption (unauthenticated, token-based) ----------------------------------------


def _lookup(token: str, purpose: str) -> AccountToken:
    if not isinstance(token, str) or not 20 <= len(token) <= 200:
        raise InvalidLinkError()
    record = db.session.scalar(
        select(AccountToken).where(
            AccountToken.token_hash == hash_token(token), AccountToken.purpose == purpose
        )
    )
    if record is None or record.status() != "pending":
        raise InvalidLinkError()
    if purpose == PASSWORD_RESET:
        user = db.session.get(User, record.user_id) if record.user_id else None
        if user is None or not user.is_active:
            raise InvalidLinkError()
    return record


def _consume(record: AccountToken) -> None:
    result = db.session.execute(
        update(AccountToken)
        .where(
            AccountToken.id == record.id,
            AccountToken.used_at.is_(None),
            AccountToken.revoked_at.is_(None),
            AccountToken.expires_at > _now(),
        )
        .values(used_at=_now())
    )
    if result.rowcount != 1:
        raise InvalidLinkError()


def describe(token: str, purpose: str) -> dict[str, Any]:
    record = _lookup(token, purpose)
    data = {"email": record.email, "expires_at": iso(record.expires_at)}
    if purpose == INVITATION:
        data.update(display_name=record.display_name, roles=list(record.roles or []))
    return data


def accept_invitation(token: str, password: str, display_name: str | None) -> User:
    record = _lookup(token, INVITATION)
    name = (display_name or record.display_name or "").strip()
    errors: dict[str, list[str]] = {}
    if not name or len(name) > 120:
        errors["display_name"] = ["Enter your name (up to 120 characters)."]
    elif problem := plain_text_problem(name):
        errors["display_name"] = [problem]
    if problems := password_problems(password or "", email=record.email):
        errors["password"] = problems
    if errors:
        raise ValidationError(details=errors)
    if db.session.scalar(select(User.id).where(User.email == record.email)):
        raise InvalidLinkError()
    _consume(record)
    inviter = db.session.get(User, record.created_by_id) if record.created_by_id else None
    user = User(
        email=record.email,
        display_name=name,
        password_hash=hash_password(password),
        status="active",
        email_verified_at=_now(),
        last_login_at=_now(),
    )
    db.session.add(user)
    db.session.flush()
    set_user_roles(user, list(record.roles), assigned_by=inviter)
    record.user_id = user.id
    audit_service.record(
        "invitation.accepted",
        "user",
        user.id,
        actor=user,
        details={"invitation_id": record.id, "roles": list(record.roles)},
    )
    return user


# ---- password resets ---------------------------------------------------------------------


def request_password_reset(user: User, actor: User) -> AccountToken:
    if not user.is_active:
        raise ConflictError("Reactivate the account before resetting its password.")
    db.session.execute(
        update(AccountToken)
        .where(
            AccountToken.purpose == PASSWORD_RESET,
            AccountToken.user_id == user.id,
            AccountToken.used_at.is_(None),
            AccountToken.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )
    token, digest = _new_token()
    minutes = current_app.config["PASSWORD_RESET_TTL_MINUTES"]
    record = AccountToken(
        purpose=PASSWORD_RESET,
        token_hash=digest,
        email=user.email,
        user_id=user.id,
        created_by_id=actor.id,
        expires_at=_now() + timedelta(minutes=minutes),
    )
    db.session.add(record)
    db.session.flush()
    record.delivery = mail.send(
        mail.EmailMessage(
            to=user.email,
            subject="Reset your Think Positive Always admin password",
            text=(
                f"Hello {user.display_name},\n\nA password reset was requested for your admin "
                f"account. Choose a new password here:\n{_link('/admin/reset-password', token)}\n\n"
                f"This link can be used once and expires in {minutes} minutes. If you did not "
                "expect this, contact a super administrator."
            ),
        )
    )
    audit_service.record(
        "user.password_reset_requested",
        "user",
        user.id,
        actor=actor,
        details={"delivery": record.delivery},
    )
    return record


def complete_password_reset(token: str, password: str) -> User:
    record = _lookup(token, PASSWORD_RESET)
    user = db.session.get(User, record.user_id)
    if problems := password_problems(password or "", email=user.email):
        raise ValidationError(details={"password": problems})
    _consume(record)
    user.password_hash = hash_password(password)
    revoke_all_sessions(user)
    audit_service.record("auth.password_reset_completed", "user", user.id, actor=user)
    return user


def revoke_user_tokens(user: User) -> None:
    """Called when an account is disabled: outstanding reset links stop working."""
    db.session.execute(
        update(AccountToken)
        .where(
            AccountToken.user_id == user.id,
            AccountToken.used_at.is_(None),
            AccountToken.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )


def pending_for_user(user: User) -> list[dict[str, Any]]:
    rows = db.session.scalars(
        select(AccountToken)
        .where(AccountToken.user_id == user.id)
        .order_by(AccountToken.created_at.desc())
        .limit(10)
    ).all()
    return [token_dict(t) for t in rows]
