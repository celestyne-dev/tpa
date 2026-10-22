"""Administrator accounts and role assignment (super administrators only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ...auth.passwords import hash_password, password_problems
from ...auth.permissions import ROLE_PERMISSIONS, RoleName
from ...auth.roles import active_super_admin_count, set_user_roles
from ...auth.session import revoke_all_sessions
from ...extensions import db
from ...models import Role, User
from ...utils.errors import ConflictError, ValidationError
from ...utils.validation import is_email
from .. import audit_service
from .auth_service import normalise_email, user_payload


def list_users() -> list[dict[str, Any]]:
    return [user_payload(u) for u in db.session.scalars(select(User).order_by(User.email))]


def list_roles() -> list[dict[str, Any]]:
    roles = db.session.scalars(select(Role).order_by(Role.id)).all()
    return [
        {
            "name": r.name,
            "description": r.description,
            "permissions": sorted(p.value for p in ROLE_PERMISSIONS.get(RoleName(r.name), set())),
        }
        for r in roles
        if r.name in RoleName._value2member_map_
    ]


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
        set_user_roles(user, data["roles"], assigned_by=actor)
        db.session.flush()
        if before != user.role_names:
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
        details["status"] = {"from": user.status, "to": data["status"]}
        user.status = data["status"]
    if details:
        audit_service.record("user.updated", "user", user.id, actor=actor, details=details)
    return user


def reset_password(user: User, new_password: str, actor: User) -> None:
    if problems := password_problems(new_password, email=user.email):
        raise ValidationError(details={"password": problems})
    user.password_hash = hash_password(new_password)
    revoke_all_sessions(user)
    audit_service.record("user.password_reset", "user", user.id, actor=actor)
