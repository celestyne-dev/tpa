"""Administrator accounts and role assignment (super administrators only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select

from ...auth.decorators import user_permissions
from ...auth.passwords import hash_password, password_problems
from ...auth.permissions import (
    PERMISSION_DESCRIPTIONS,
    ROLE_DEFINITIONS,
    RoleName,
    can_grant_roles,
)
from ...auth.roles import active_super_admin_count, get_roles, set_user_roles
from ...auth.session import revoke_all_sessions
from ...extensions import db
from ...models import AuditLog, Role, User, UserRole
from ...utils.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from ...utils.validation import is_email
from .. import audit_service
from .account_tokens import pending_for_user, revoke_user_tokens
from .auth_service import normalise_email, user_payload


def list_users(args: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    args = args or {}
    stmt = select(User).order_by(User.email)
    if args.get("q"):
        like = f"%{args['q'].strip().lower()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.display_name.ilike(like)))
    if args.get("status"):
        stmt = stmt.where(User.status == args["status"])
    if args.get("role"):
        stmt = stmt.where(
            User.id.in_(
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name == args["role"])
            )
        )
    return [user_payload(u) for u in db.session.scalars(stmt)]


def user_detail(user: User) -> dict[str, Any]:
    from .dashboard import audit_entry

    activity = db.session.scalars(
        select(AuditLog)
        .where(
            or_(
                AuditLog.actor_id == user.id,
                (AuditLog.resource_type == "user") & (AuditLog.resource_id == str(user.id)),
            )
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(15)
    ).all()
    return {
        **user_payload(user),
        "is_last_super_admin": RoleName.SUPER_ADMIN.value in user.role_names
        and user.is_active
        and active_super_admin_count(user.id) == 0,
        "account_links": pending_for_user(user),
        "recent_activity": [audit_entry(e) for e in activity],
    }


def list_roles() -> list[dict[str, Any]]:
    roles = db.session.scalars(select(Role).order_by(Role.id)).all()
    out = []
    for r in roles:
        try:
            definition = ROLE_DEFINITIONS[RoleName(r.name)]
        except ValueError:
            continue
        out.append(
            {
                "name": r.name,
                "label": definition.label,
                "description": definition.description,
                "permissions": sorted(p.value for p in definition.permissions),
            }
        )
    return out


def list_permissions() -> list[dict[str, str]]:
    return [{"name": p.value, "description": d} for p, d in PERMISSION_DESCRIPTIONS.items()]


def _check_grant(actor: User | None, roles: list[str]) -> None:
    get_roles(sorted(set(roles)))
    if actor is not None and not can_grant_roles(user_permissions(actor), roles):
        raise ForbiddenError("You cannot grant one or more of these roles.")


def create_user(data: dict[str, Any], actor: User | None) -> User:
    email = normalise_email(data["email"])
    errors: dict[str, list[str]] = {}
    if not is_email(email):
        errors["email"] = ["Enter a valid email address."]
    if problems := password_problems(data["password"], email=email):
        errors["password"] = problems
    if not data.get("roles"):
        errors["roles"] = ["Assign at least one role."]
    if errors:
        raise ValidationError(details=errors)
    _check_grant(actor, data["roles"])
    if db.session.scalar(select(User.id).where(User.email == email)):
        raise ConflictError(details={"email": ["An account with this email already exists."]})
    user = User(
        email=email,
        display_name=data["display_name"].strip(),
        password_hash=hash_password(data["password"]),
        status="active",
    )
    db.session.add(user)
    db.session.flush()
    set_user_roles(user, data["roles"], assigned_by=actor)
    audit_service.record(
        "user.created",
        "user",
        user.id,
        actor=actor,
        details={"email": email, "roles": sorted(data["roles"])},
    )
    return user


def update_user(user: User, data: dict[str, Any], actor: User) -> User:
    details: dict[str, Any] = {}
    if "display_name" in data and data["display_name"].strip() != user.display_name:
        details["display_name"] = {"from": user.display_name, "to": data["display_name"].strip()}
        user.display_name = data["display_name"].strip()
    if "roles" in data:
        if not data["roles"]:
            raise ValidationError(details={"roles": ["Assign at least one role."]})
        before = user.role_names
        if sorted(set(data["roles"])) != before:
            # Changing roles requires holding every permission involved (no escalation).
            _check_grant(actor, sorted(set(data["roles"]) | set(before)))
            set_user_roles(user, data["roles"], assigned_by=actor)
            db.session.flush()
            details["roles"] = {"from": before, "to": user.role_names}
    if "status" in data and data["status"] != user.status:
        if data["status"] == "disabled":
            if user.id == actor.id:
                raise ConflictError("You cannot disable your own account.")
            if (
                RoleName.SUPER_ADMIN.value in user.role_names
                and active_super_admin_count(user.id) == 0
            ):
                raise ConflictError("The last active super administrator cannot be disabled.")
            revoke_all_sessions(user)
            revoke_user_tokens(user)
        details["status"] = {"from": user.status, "to": data["status"]}
        user.status = data["status"]
    if details:
        action = "user.updated"
        if set(details) == {"status"}:
            action = "user.disabled" if data["status"] == "disabled" else "user.reactivated"
        audit_service.record(action, "user", user.id, actor=actor, details=details)
    return user


def reset_password(user: User, new_password: str, actor: User) -> None:
    if problems := password_problems(new_password, email=user.email):
        raise ValidationError(details={"password": problems})
    user.password_hash = hash_password(new_password)
    revoke_all_sessions(user)
    audit_service.record("user.password_reset", "user", user.id, actor=actor)


def get_user(user_id: int) -> User:
    user = db.session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return user
