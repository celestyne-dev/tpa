"""Role management: custom roles, templates and their permissions.

Rules enforced here (the admin UI only mirrors them):
- System roles (Super Admin, Editor, Moderator, Analyst) are read-only.
- A role may only be granted permissions that exist, are available (their
  module is implemented) and are not sensitive. Sensitive permissions stay
  with Super Admin.
- Nobody can grant a permission they do not hold themselves.
- A role still held by users or pending invitations cannot be deleted; it can
  be deactivated instead (its permissions then stop applying immediately).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from ...auth.permissions import CATALOGUE, CATALOGUE_BY_KEY, ROLE_SPECS, SYSTEM_ROLES
from ...auth.rbac import effective_permissions, permission_map, role_grant_set
from ...extensions import db
from ...models import AccountToken, Role, User, UserRole
from ...utils.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from .. import audit_service
from ..serializers import iso


def _now() -> datetime:
    return datetime.now(UTC)


# ---- serialisation -------------------------------------------------------------------


def permission_catalogue() -> list[dict[str, Any]]:
    """The catalogue grouped for display, with availability and sensitivity flags."""
    stored = permission_map()
    groups: dict[str, list[dict[str, Any]]] = {}
    for d in CATALOGUE:
        record = stored.get(d.key.value)
        groups.setdefault(d.group, []).append(
            {
                "key": d.key.value,
                "label": d.label,
                "description": d.description,
                "module": d.module,
                "available": bool(record.is_available) if record else d.available,
                "sensitive": bool(record.is_sensitive) if record else d.sensitive,
            }
        )
    return [{"name": name, "permissions": items} for name, items in groups.items()]


def _user_counts() -> dict[int, int]:
    rows = db.session.execute(
        select(UserRole.role_id, func.count(UserRole.user_id)).group_by(UserRole.role_id)
    )
    return {role_id: n for role_id, n in rows}


def _pending_invitations(role: Role) -> int:
    now = _now()
    invites = db.session.scalars(
        select(AccountToken).where(
            AccountToken.purpose == "invitation",
            AccountToken.used_at.is_(None),
            AccountToken.revoked_at.is_(None),
        )
    )
    return sum(1 for i in invites if role.name in (i.roles or []) and _aware(i.expires_at) > now)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def role_summary(role: Role, user_count: int | None = None) -> dict[str, Any]:
    spec = ROLE_SPECS.get(role.name)
    return {
        "id": role.id,
        "name": role.name,
        "label": role.label or role.name,
        "description": role.description,
        "kind": role.kind,
        "is_active": role.is_active,
        "is_protected": role.is_protected,
        "grants_all": role.grants_all,
        "permissions": sorted(role_grant_set(role))
        if role.grants_all
        else sorted(role.permission_keys),
        "planned_permissions": sorted(spec.planned) if spec else [],
        "user_count": user_count if user_count is not None else _user_counts().get(role.id, 0),
        "updated_at": iso(role.updated_at),
    }


def role_detail(role: Role) -> dict[str, Any]:
    users = db.session.scalars(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .where(UserRole.role_id == role.id)
        .order_by(User.email)
    ).all()
    return {
        **role_summary(role, len(users)),
        "users": [
            {"id": u.id, "email": u.email, "display_name": u.display_name, "status": u.status}
            for u in users
        ],
        "pending_invitations": _pending_invitations(role),
    }


def list_roles(include_inactive: bool = True) -> list[dict[str, Any]]:
    order = {"system": 0, "template": 1, "custom": 2}
    roles = db.session.scalars(select(Role)).all()
    counts = _user_counts()
    builtin = {spec.key: i for i, spec in enumerate(SYSTEM_ROLES)}
    roles = sorted(
        roles,
        key=lambda r: (order.get(r.kind, 3), builtin.get(r.name, 99), (r.label or r.name).lower()),
    )
    return [role_summary(r, counts.get(r.id, 0)) for r in roles if include_inactive or r.is_active]


def get_role(role_id: int) -> Role:
    role = db.session.get(Role, role_id)
    if role is None:
        raise NotFoundError("Role not found.")
    return role


# ---- validation -------------------------------------------------------------------


def _clean_permissions(keys: list[str], actor: User) -> list[Any]:
    keys = sorted(set(keys))
    stored = permission_map()
    errors = []
    for key in keys:
        record = stored.get(key)
        if record is None or key not in CATALOGUE_BY_KEY:
            errors.append(f"Unknown permission: {key}")
        elif record.is_sensitive:
            errors.append(f"{record.label} is protected and cannot be granted to a role.")
        elif not record.is_available:
            errors.append(f"{record.label} belongs to a module that is not available yet.")
    if errors:
        raise ValidationError(details={"permissions": errors})
    # No privilege escalation: you can only hand out what you hold.
    missing = set(keys) - effective_permissions(actor)
    if missing:
        raise ForbiddenError("You cannot grant permissions you do not hold.")
    return [stored[k] for k in keys]


def _clean_label(label: str, exclude_id: int | None = None) -> str:
    label = (label or "").strip()
    if not label:
        raise ValidationError(details={"label": ["Enter a role name."]})
    clash = db.session.scalar(
        select(Role.id).where(func.lower(Role.label) == label.lower(), Role.id != (exclude_id or 0))
    )
    if clash:
        raise ConflictError(details={"label": ["A role with this name already exists."]})
    return label


def _machine_name(label: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:40] or "role"
    name, n = base, 2
    while db.session.scalar(select(Role.id).where(Role.name == name)) or name in ROLE_SPECS:
        name = f"{base}_{n}"
        n += 1
    return name


def _ensure_editable(role: Role) -> None:
    if role.is_protected:
        raise ForbiddenError("Built-in roles cannot be changed.")


# ---- mutations ---------------------------------------------------------------------


def create_role(data: dict[str, Any], actor: User) -> Role:
    label = _clean_label(data["label"])
    permissions = _clean_permissions(data.get("permissions") or [], actor)
    role = Role(
        name=_machine_name(label),
        label=label,
        description=(data.get("description") or "").strip(),
        kind="custom",
        is_active=True,
        grants_all=False,
    )
    role.permissions = permissions
    db.session.add(role)
    db.session.flush()
    audit_service.record(
        "role.created",
        "role",
        role.id,
        actor=actor,
        details={"label": label, "permissions": sorted(p.key for p in permissions)},
    )
    return role


def update_role(role: Role, data: dict[str, Any], actor: User) -> Role:
    _ensure_editable(role)
    details: dict[str, Any] = {}
    if "label" in data:
        label = _clean_label(data["label"], exclude_id=role.id)
        if label != role.label:
            details["label"] = {"from": role.label, "to": label}
            role.label = label
    if "description" in data:
        description = (data["description"] or "").strip()
        if description != role.description:
            details["description"] = {"from": role.description, "to": description}
            role.description = description
    if "permissions" in data:
        before = role.permission_keys
        # Editing a role's permissions also requires holding what it currently grants,
        # so nobody can quietly strip or reshape a role above their level.
        if not role_grant_set(role) <= effective_permissions(actor):
            raise ForbiddenError("You cannot change a role that grants permissions you lack.")
        permissions = _clean_permissions(data["permissions"], actor)
        after = {p.key for p in permissions}
        if after != before:
            role.permissions = permissions
            details["permissions"] = {
                "added": sorted(after - before),
                "removed": sorted(before - after),
            }
    if "is_active" in data and data["is_active"] != role.is_active:
        details["is_active"] = {"from": role.is_active, "to": data["is_active"]}
        role.is_active = data["is_active"]
    if details:
        action = "role.updated"
        if set(details) == {"is_active"}:
            action = "role.activated" if role.is_active else "role.deactivated"
        audit_service.record(action, "role", role.id, actor=actor, details=details)
    return role


def delete_role(role: Role, actor: User) -> None:
    _ensure_editable(role)
    users = _user_counts().get(role.id, 0)
    invites = _pending_invitations(role)
    if users or invites:
        raise ConflictError(
            f"This role is assigned to {users} user(s) and {invites} pending invitation(s). "
            "Remove it from them or deactivate the role instead."
        )
    audit_service.record(
        "role.deleted",
        "role",
        role.id,
        actor=actor,
        details={"label": role.label, "permissions": sorted(role.permission_keys)},
    )
    db.session.delete(role)
