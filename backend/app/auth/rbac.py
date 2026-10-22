"""Database-backed role and permission resolution.

Effective permissions = union of the permissions of the user's *active* roles.
Super Admin (grants_all) resolves to the whole catalogue. Only permissions
marked available are effective for other roles.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select

from ..extensions import db
from ..models import PermissionDefinition, Role, User
from .permissions import (
    ALL_PERMISSIONS,
    CATALOGUE,
    SYSTEM_ROLES,
    TEMPLATE_ROLES,
    Permission,
)


def role_grant_set(role: Role) -> set[str]:
    """What a role effectively grants (ignores whether it is active)."""
    if role.grants_all:
        return set(ALL_PERMISSIONS)
    return {p.key for p in role.permissions if p.is_available and not p.is_sensitive}


def effective_permissions(user: User) -> set[str]:
    granted: set[str] = set()
    for link in user.role_links:
        role = link.role
        if role is None or not role.is_active:
            continue
        if role.grants_all:
            return set(ALL_PERMISSIONS)
        granted |= role_grant_set(role)
    return granted


def has_permissions(user: User, *perms: str | Permission) -> bool:
    granted = effective_permissions(user)
    return all(str(p) in granted for p in perms)


def can_grant_roles(actor: User, roles: Iterable[Role]) -> bool:
    """Assigning roles requires roles.assign and every permission those roles grant."""
    actor_perms = effective_permissions(actor)
    if Permission.ROLES_ASSIGN.value not in actor_perms:
        return False
    return all(role_grant_set(role) <= actor_perms for role in roles)


def can_manage_user(actor: User, target: User) -> bool:
    """Accounts can only be managed by someone holding every permission the target holds."""
    return effective_permissions(target) <= effective_permissions(actor)


def permission_map() -> dict[str, PermissionDefinition]:
    return {p.key: p for p in db.session.scalars(select(PermissionDefinition))}


def sync_rbac() -> dict[str, int]:
    """Synchronise the catalogue, system roles and role templates. Idempotent.

    - Permissions: inserted/updated from the code catalogue (never deleted;
      keys removed from code are marked unavailable).
    - System roles: created, and their label, description and permissions are
      reset to the definitions in code (they cannot be edited in the admin).
    - Templates: created when missing; existing templates keep admin edits.
    - Safety: non-system roles lose any sensitive or unavailable permission.
    """
    counts = {
        "permissions_created": 0,
        "permissions_updated": 0,
        "roles_created": 0,
        "system_roles_reset": 0,
        "unsafe_grants_removed": 0,
    }
    existing = permission_map()
    known = set()
    for order, d in enumerate(CATALOGUE):
        known.add(d.key.value)
        values = {
            "label": d.label,
            "description": d.description,
            "group": d.group,
            "module": d.module,
            "is_available": d.available,
            "is_sensitive": d.sensitive,
            "sort_order": order,
        }
        record = existing.get(d.key.value)
        if record is None:
            db.session.add(PermissionDefinition(key=d.key.value, **values))
            counts["permissions_created"] += 1
        elif any(getattr(record, k) != v for k, v in values.items()):
            for k, v in values.items():
                setattr(record, k, v)
            counts["permissions_updated"] += 1
    for key, record in existing.items():
        if key not in known and record.is_available:
            record.is_available = False
            counts["permissions_updated"] += 1
    db.session.flush()
    perms = permission_map()

    roles = {r.name: r for r in db.session.scalars(select(Role))}
    for spec in SYSTEM_ROLES + TEMPLATE_ROLES:
        role = roles.get(spec.key)
        if role is None:
            role = Role(
                name=spec.key,
                label=spec.label,
                description=spec.description,
                kind=spec.kind,
                is_active=True,
                grants_all=spec.grants_all,
                permissions=[perms[k] for k in sorted(spec.permissions)],
            )
            db.session.add(role)
            roles[spec.key] = role
            counts["roles_created"] += 1
        elif spec.kind == "system":
            wanted = [perms[k] for k in sorted(spec.permissions)]
            if (role.label, role.description, role.kind, role.grants_all, role.is_active) != (
                spec.label,
                spec.description,
                "system",
                spec.grants_all,
                True,
            ) or role.permission_keys != spec.permissions:
                role.label, role.description, role.kind = spec.label, spec.description, "system"
                role.grants_all, role.is_active = spec.grants_all, True
                role.permissions = wanted
                counts["system_roles_reset"] += 1
    for role in roles.values():
        if role.kind == "system":
            continue
        if role.grants_all:
            role.grants_all = False  # only the built-in Super Admin may grant everything
        unsafe = [p for p in role.permissions if p.is_sensitive or not p.is_available]
        if unsafe:
            role.permissions = [p for p in role.permissions if p not in unsafe]
            counts["unsafe_grants_removed"] += len(unsafe)
    db.session.flush()
    return counts
